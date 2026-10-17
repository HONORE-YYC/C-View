import pytest

from cvisualizer.engine import Engine
from cvisualizer.language import CError


def run(source, expand=False):
    engine = Engine(source)
    events = []
    while engine.peek():
        events.append(engine.step(expand_calls=expand))
    return engine.runtime.snapshot(), events


@pytest.mark.parametrize('expand', [False, True])
def test_pointer_parameter_return_and_identity(expand):
    values, events = run('int *inc(int *x){*x+=2;return x;} int main(){int x=3;int hidden=8;int *p=inc(&x);*p=9;}', expand)
    assert values['x']['value'] == 9
    assert values['p']['value'].identity == values['x']['identity']
    assert values['p']['type'] == 'int*'
    for event in events:
        if event.function:
            assert 'hidden' not in event.variables
            for cell in event.variables.values():
                value = cell['value']
                if cell['type'].endswith('*') and value is not None and value.identity is not None:
                    assert any(c['identity'] == value.identity for c in event.variables.values())


def test_pointer_array_arithmetic_and_alias_writes():
    values, events = run('int main(){int a[3]={2,4,6};int *p=a;p++;p[1]=9;int *q=&a[3];int d=q-p;int yes=p<q;p-=1;int b=*p;}', True)
    assert values['a']['value'] == [2,4,9]
    assert values['d']['value'] == 2
    assert values['yes']['value'] == 1
    assert values['b']['value'] == 2
    assert ('a', 2) in next(e for e in events if 'p[1] = 9' in e.text).writes


@pytest.mark.parametrize('source, message', [
    ('#include <stddef.h>\nint main(){int *p=NULL;int a=*p;}', '空指针'),
    ('int main(){int *p;int a=*p;}', '未初始化'),
    ('int main(){int *p;{int x=1;p=&x;}{int x=2;int a=*p;}}', '悬空'),
    ('int *bad(){int x=1;return &x;}int main(){int *p=bad();int a=*p;}', '悬空'),
    ('int main(){int a[2]={1,2};int *p=a+2;int b=*p;}', '越界'),
    ('int main(){int a[2];int *p=a+3;}', '越界'),
    ('int main(){int x=1;double *p=&x;}', '类型'),
    ('int main(){int x=1;int y=2;int d=&x-&y;}', '同一'),
])
def test_invalid_pointer_operations(source, message):
    with pytest.raises(CError, match=message):
        run(source)


def test_null_and_floating_pointers_and_scalar_pass_by_value():
    values, _ = run('void f(double *p){*p=2.5;p=0;}int main(){double x=1;double *p=&x;f(p);double y=*p;float z=3;float *q=&z;*q=4;int *n=0;int b=!n;}')
    assert values['y']['value'] == 2.5
    assert values['z']['value'] == 4.0
    assert values['b']['value'] == 1


@pytest.mark.parametrize('expand', [False, True])
def test_nested_pointer_calls_array_parameters_and_shadowed_objects(expand):
    values, _ = run('''void add(int *p){*p+=1;}
void twice(int a[]){add(&a[0]);add(a);}
int main(){int x=2;int *p=&x;{int x=99;*p+=3;}
int a[3]={1,2,3};twice(a+1);int *q=a+3;int size=q-a;int copied=*p;}''', expand)
    assert values['x']['value'] == values['copied']['value'] == 5
    assert values['a']['value'] == [1,4,3]
    assert values['size']['value'] == 3


def test_pointer_function_failure_rolls_back_pointee_and_keeps_alias_identity():
    engine = Engine('void fail(int *p){*p=99;int *q=0;*q=3;} int main(){int x=2;int *p=&x;fail(p);}')
    engine.step(); engine.step()
    with pytest.raises(CError, match='空指针'):
        engine.step(expand_calls=True)
    values = engine.runtime.snapshot()
    assert values['x']['value'] == 2
    assert values['p']['value'].identity == values['x']['identity']
    assert not engine.runtime.callers


def test_scalar_one_past_address_is_preserved_and_cannot_be_read():
    values, _ = run('int x=1;int *p=&x;int *q=&p[1];int n=q-p;')
    assert values['n']['value'] == 1
    with pytest.raises(CError, match='越界'):
        run('int x=1;int *p=&x;int *q=&p[1];int y=*q;')


@pytest.mark.parametrize('expand', [False, True])
def test_array_parameter_is_a_local_pointer_that_can_advance(expand):
    values, _ = run('void f(int a[]){a++;*a=9;} int main(){int a[3]={1,2,3};f(a);}', expand)
    assert values['a']['value'] == [1,9,3]
