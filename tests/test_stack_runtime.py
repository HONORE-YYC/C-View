import pytest
from cvisualizer.engine import Engine
from cvisualizer.language import Program, CError
from cvisualizer.stack_state import models


PREFIX = 'typedef int Item; typedef struct Renamed {Item *start;Item *cursor;int limit;} Stack;'
INIT = 'Stack s; s.start=new Item[4];s.cursor=s.start;s.limit=4;'


def run(source, detail=False):
    engine = Engine(source)
    events = []
    while engine.peek():
        events.append(engine.step(expand_calls=detail))
    return engine, events


def test_recognition_uses_types_and_member_order():
    engine, _ = run(PREFIX + 'int main(){' + INIT + '}')
    assert engine.program.stack_types == {'struct Renamed': dict(base='start', top='cursor', capacity='limit')}
    model = next(iter(models(engine.runtime.snapshot()).values()))
    assert model['valid'] and model['count'] == 0 and model['capacity'] == 4


@pytest.mark.parametrize('fields', ['int *a;double *b;int n;', 'int *a;int n;int *b;',
                                    'int *a;int *b;long n;', 'int *a;int *b;int n;int x;'])
def test_nonstandard_struct_fallback(fields):
    assert Program('struct X{' + fields + '};int main(){struct X s;}').stack_types == {}


@pytest.mark.parametrize('typename,value', [('int','7'), ('double','2.5'), ('long long','123'), ('char','65')])
def test_numeric_new_array_and_delete(typename, value):
    engine, events = run('int main(){int n=3;' + typename + ' *p=new ' + typename + '[n]();'
                        'p[2]=' + value + ';' + typename + ' result=p[2];delete[] p;}')
    assert engine.runtime.snapshot()['result']['value'] == float(value)
    assert not engine.runtime.heap
    assert any('new ' in event.text and '[n]' in event.text for event in events)
    assert any('delete[] p' == event.text for event in events)
    assert not any('sizeof' in event.text or '__cv_delete' in event.text for event in events)


@pytest.mark.parametrize('body,match', [
    ('int *p=new int[2];delete p;', 'delete'),
    ('struct X *p=new struct X();delete[] p;', 'delete'),
    ('int *p=new int[2];delete[] (p+1);', 'delete'),
    ('int *p=new int[2];delete[] p;delete[] p;', '释放'),
    ('int *p=new int[2];delete[] p;int x=*p;', '悬空'),
    ('int a[2];delete[] a;', 'delete'),
    ('int *p=new int[0];', '容量'),
])
def test_array_allocation_safeguards(body, match):
    with pytest.raises(CError, match=match):
        run('struct X{int x;};int main(){' + body + '}')


@pytest.mark.parametrize('detail', [False, True])
def test_arbitrary_function_multiple_operations_retain_last_pop(detail):
    source = PREFIX + '''void change(Stack &q){
        *q.cursor++=11;*q.cursor++=22;int first=*--q.cursor;
        *q.cursor++=33;int second=*--q.cursor;*q.cursor++=44;
    }int main(){''' + INIT + 'change(s);}'
    engine, events = run(source, detail)
    model = next(iter(models(engine.runtime.snapshot()).values()))
    assert model['count'] == 2 and model['values'][1] == 44
    assert model['popped']['value'] == 33 and model['popped']['serial'] == 2
    if detail:
        pops = [m['popped']['value'] for e in events for m in models(e.variables).values() if m['popped']]
        assert 22 in pops and 33 in pops


def test_static_storage_and_pointer_to_stack_work():
    engine, _ = run(PREFIX + 'void strange(Stack *q){*q->cursor++=9;q->cursor--;}'
                    'int main(){int a[3];Stack s={a,a,3};strange(&s);}')
    model = next(iter(models(engine.runtime.snapshot()).values()))
    assert model['valid'] and model['count'] == 0 and model['popped']['value'] == 9


@pytest.mark.parametrize('shadow', ['', 'int a=2;'])
def test_detailed_pointer_parameter_keeps_reachable_stack_storage(shadow):
    _, events = run(PREFIX + 'void change(Stack *q){' + shadow +
                    '*q->cursor++=9;q->cursor--;}'
                    'int main(){int a[3];Stack s={a,a,3};change(&s);}', True)
    detail = [event for event in events if event.function == 'change']
    assert detail
    states = [model for event in detail for model in models(event.variables).values()]
    assert states and all(model['valid'] for model in states)
    assert any(model['count'] == 1 for model in states)
    assert any(model['popped'] and model['popped']['value'] == 9 for model in states)


@pytest.mark.parametrize('detail', [False, True])
def test_pop_and_delete_rollback_after_failed_call(detail):
    engine = Engine(PREFIX + 'void bad(Stack &q){q.cursor--;delete[] q.start;int x=1/0;}'
                    'int main(){' + INIT + '*s.cursor++=7;bad(s);}')
    while not engine.peek().location.text.startswith('bad('):
        engine.step()
    before = engine.runtime.snapshot()
    with pytest.raises(CError):
        engine.step(expand_calls=detail)
    assert engine.runtime.snapshot() == before
    assert not engine.runtime.stack_popped and not engine.has_detail


@pytest.mark.parametrize('detail', [False, True])
def test_exit_stops_only_teaching_program(detail):
    engine, events = run('void finish(){printf("done");exit(-2);printf("bad");}'
                         'int main(){int x=1;finish();x=2;}', detail)
    assert engine.runtime.output == 'done'
    assert engine.runtime.snapshot()['x']['value'] == 1
    assert engine.runtime.exit_status == -2 and engine.finished
    assert 'exit(-2)' in events[-1].message


def test_textbook_initialization_sample():
    source = '''#define MAXSIZE 100
#define OK 1
#define OVERFLOW -2
typedef int SElemType;typedef int Status;
typedef struct {SElemType *base;SElemType *top;int stacksize;} SqStack;
Status InitStack(SqStack &S){S.base=new SElemType[MAXSIZE];
if(!S.base)exit(OVERFLOW);S.top=S.base;S.stacksize=MAXSIZE;return OK;}
int main(){SqStack S;int result=InitStack(S);}'''
    engine, _ = run(source, True)
    model = next(iter(models(engine.runtime.snapshot()).values()))
    assert model['valid'] and model['capacity'] == 100
    assert engine.runtime.snapshot()['result']['value'] == 1


def test_dynamic_array_capacity_runs_once_and_null_delete_is_safe():
    engine, _ = run('int main(){int n=2;int *p=new int[n++]();int zero=p[1];'
                    'delete[] p;p=0;delete[] p;}')
    snapshot = engine.runtime.snapshot()
    assert snapshot['n']['value'] == 3 and snapshot['zero']['value'] == 0
    assert not engine.runtime.heap


@pytest.mark.parametrize('expression', ['new int[2][3]', 'new struct X[2]', 'new int', 'sizeof(int)', '__cv_delete_array(0)'])
def test_unsupported_allocations_and_private_lowering_are_rejected(expression):
    with pytest.raises(CError):
        Program('struct X{int x;};int main(){' + expression + ';}')


@pytest.mark.parametrize('detail', [False, True])
def test_cancelled_pop_restores_previous_ghost_and_retry(detail):
    from cvisualizer.formatted_io import InputCancelled
    engine = Engine(PREFIX + 'void read(Stack &q){q.cursor--;int x;scanf("%d",&x);}'
                    'int main(){' + INIT + '*s.cursor++=11;*s.cursor++=22;s.cursor--;'
                    '*s.cursor++=33;read(s);}')
    while not engine.peek().location.text.startswith('read('):
        engine.step()
    before = engine.runtime.snapshot()
    with pytest.raises(InputCancelled):
        engine.step(expand_calls=detail)
    assert engine.runtime.snapshot() == before
    assert next(iter(models(before).values()))['popped']['value'] == 22
    engine.runtime.input_provider = lambda request: '8'
    while engine.peek():
        engine.step(expand_calls=detail)
    popped = next(iter(models(engine.runtime.snapshot()).values()))['popped']
    assert popped['value'] == 33 and popped['serial'] == 2


def test_multiple_stacks_keep_independent_pop_records_and_snapshot_history():
    engine, events = run(PREFIX + 'int main(){int a[2],b[2];Stack x={a,a,2},y={b,b,2};'
                        '*x.cursor++=10;*y.cursor++=20;x.cursor--;y.cursor--;*x.cursor++=30;}')
    by_name = {m['name']: m for m in models(engine.runtime.snapshot()).values()}
    assert by_name['x']['popped']['value'] == 10
    assert by_name['y']['popped']['value'] == 20
    historical = [m for event in events for m in models(event.variables).values()
                  if m['name'] == 'x' and m['popped']]
    assert historical[0]['values'][0] == 10


@pytest.mark.parametrize('expr', ['exit()', 'exit(1,2)', 'exit(1.5)'])
def test_exit_requires_one_integer_status(expr):
    with pytest.raises(CError):
        run('int main(){' + expr + ';}')


def test_failed_capacity_evaluation_rolls_back_side_effects():
    engine = Engine('int main(){int n=0;int *p=new int[n++];}')
    engine.step()
    before = engine.runtime.snapshot()
    with pytest.raises(CError, match='容量'):
        engine.step()
    assert engine.runtime.snapshot() == before and not engine.runtime.heap


def test_delete_prefix_in_identifier_is_not_an_operator():
    engine, _ = run('int delete_count=0;void delete_values(){delete_count++;}'
                    'int main(){delete_values();}')
    assert engine.runtime.snapshot()['delete_count']['value'] == 1
