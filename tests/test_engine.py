import pytest

from cvisualizer.engine import Engine
from cvisualizer.language import CError


def execute(code, limit=100000):
    engine = Engine(code, max_steps=limit)
    events = []
    while engine.peek() is not None:
        events.append(engine.step())
    return engine, events


def values(event):
    return {name: cell['value'] for name, cell in event.variables.items()}


def test_mixed_loop_and_array():
    engine, events = execute('''int sum=0; int data[5]={0};
for(int i=0;i<5;i++){ if(i==2) continue; data[i]=i*2; sum+=data[i]; }
int answer=sum;''')
    assert values(events[-1]) == {'sum': 16, 'data': [0, 2, 0, 6, 8], 'answer': 16}
    assert any(e.kind == 'condition' for e in events)
    assert any(e.writes == [('data', 3)] for e in events)


def test_c_integer_division_remainder_and_short_circuit():
    _, events = execute('int a=-7/3; int b=-7%3; int c=0; int d=0 && ++c; int e=1 || (1/0);')
    assert values(events[-1]) == {'a': -2, 'b': -1, 'c': 0, 'd': 0, 'e': 1}


def test_shadowing_nested_break_continue_and_increment():
    _, events = execute('''int i=0; int s=0;
while(i<4){ i++; if(i==2)continue; for(int j=0;j<4;j++){if(j==2)break; s+=i;} }
{int s=99; s++;} int p=i++; int q=++i; int result=s;''')
    v = values(events[-1])
    assert (v['s'], v['i'], v['p'], v['q'], v['result']) == (16, 6, 4, 6, 16)


def test_main_printf_comments_and_original_line_numbers():
    _, events = execute('''#include <stdio.h>
int main(void) {
  // 中文注释
  int a[3]={2};
  double x=5.0/2;
  printf("结果=%d, %f\\n", a[0], x);
  return 0;
}''')
    assert events[0].line == 4
    assert events[-1].output == '结果=2, 2.500000\n'
    assert values(events[-1])['a'] == [2, 0, 0]


def test_peek_is_before_execution_and_snapshots_are_independent():
    engine = Engine('int x=1; x=2;')
    assert engine.peek().column == 5
    first = engine.step()
    assert values(first)['x'] == 1
    assert engine.peek().column == 10
    engine.step()
    assert values(first)['x'] == 1


@pytest.mark.parametrize('code,match', [
    ('int x; int y=x;', '未初始化'),
    ('int a[2]; a[2]=1;', '越界'),
    ('int a[2]; int x=a[0];', '未初始化'),
    ('int x=1/0;', '除零'),
    ('int x=2147483647; x++;', '溢出'),
    ('int x=y;', '未声明'),
    ('int a[2]={1,2,3};', '初始化'),
    ('int x=1; int x=2;', '重复'),
    ('double x=2.0%1.0;', '整数'),
])
def test_runtime_errors(code, match):
    with pytest.raises(CError, match=match):
        execute(code)


@pytest.mark.parametrize('code', [
    'int **p;', 'struct A {int x;};', 'int a[2][2];',
    '#include <unknown.h>\nint x=1;',
    'int x=0; unknown_input("%d", &x);', 'break;', 'int a=1; a <<= 2;',
])
def test_unsupported_code_rejected_before_execution(code):
    with pytest.raises(CError):
        Engine(code)


def test_endless_loop_has_a_limit_even_without_body():
    with pytest.raises(CError, match='步数'):
        execute('while(1){}', limit=10)


def test_failed_statement_keeps_last_good_state():
    engine = Engine('int x=1; int y=0; x=4/y;')
    engine.step()
    before = engine.step()
    with pytest.raises(CError):
        engine.step()
    assert values(engine.last) == values(before)


def test_main_text_inside_string_is_not_a_function_definition():
    _, events = execute('printf("main(");')
    assert events[-1].output == 'main('


@pytest.mark.parametrize('code', [
    'double x=0x1p2;', 'int x=' + '9' * 400 + ';', 'int x=' + '9' * 5000 + ';',
], ids=['hex-float', 'large-integer', 'huge-integer'])
def test_extreme_literals_are_controlled_errors(code):
    with pytest.raises(CError):
        execute(code)


def test_signed_minimum_and_float_approximation_are_explicit():
    _, events = execute('int x=-2147483648; double y=1.5; float z=2.5f;')
    assert values(events[-1]) == {'x': -2147483648, 'y': 1.5, 'z': 2.5}


@pytest.mark.parametrize('source', ['struct A {int x;} main(void){return 0;}',
                                   'enum A {X} main(void){return X;}'])
def test_non_numeric_main_return_type_is_rejected(source):
    with pytest.raises(CError):
        Engine(source)


def test_deep_expression_error_does_not_recurse_while_formatting():
    with pytest.raises(CError, match='嵌套'):
        Engine('int x=' + '+'.join(['1'] * 400) + ';')
