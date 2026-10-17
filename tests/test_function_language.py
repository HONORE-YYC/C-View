import pytest
from pycparser import c_ast as ast

from cvisualizer.language import CError, Program


def test_function_metadata_preserves_main_and_globals():
    program = Program('''int total=0;
double mean(int x, float y) { return (x+y)/2; }
int main(void) { return mean(2, 4.0); }''')
    function = program.functions['mean']
    assert function.name == 'mean'
    assert isinstance(function.node, ast.FuncDef)
    assert function.return_type == 'double'
    assert [param.name for param in function.params] == ['x', 'y']
    assert 'main' not in program.functions
    assert isinstance(program.main, ast.Compound)
    assert [decl.name for decl in program.globals] == ['total']


def test_void_and_array_parameters_and_matching_prototypes():
    program = Program('''void fill(int [], int);
void fill(int data[3], int value) { data[0]=value; return; }
float number(void) { return 1.5f; }
double twice(double value) { return value*2; }
int main() { int values[3]; fill(values, twice(number())); return 0; }''')
    assert isinstance(program.functions['fill'].params[0].type, ast.ArrayDecl)
    assert program.functions['fill'].return_type == 'void'
    assert program.functions['number'].params == []


def test_function_locations_and_body_statements_are_seek_targets():
    program = Program('''#include <stdio.h>
int inc(int x) {
  return x+1;
}
int main(void) {
  int value=inc(1);
  return value;
}''')
    targets = program.targets()
    assert [(t.line, t.kind) for t in targets] == [
        (2, 'function'), (3, 'statement'),
        (6, 'statement'), (7, 'statement')]


@pytest.mark.parametrize('source,match', [
    ('int f(int x){return x;} int main(){return f();}', '参数'),
    ('int f(void){return 1;} int main(){return f(2);}', '参数'),
    ('int f(){return f();} int main(){return f();}', '递归'),
    ('int f(){return g();} int g(){return f();} int main(){return 0;}', '递归'),
    ('void f(){return 1;} int main(){f(); return 0;}', 'return'),
    ('int f(){return;} int main(){return f();}', 'return'),
    ('int main(){return;}', 'return'),
    ('int main(){return main();}', 'main'),
    ('int f(){return 1;} int f(){return 2;} int main(){return 0;}', '重复'),
    ('int abs(int x){return x;} int main(){return 0;}', '保留'),
    ('int f(int); double f(int x){return x;} int main(){return 0;}', '声明'),
    ('int f(int); int main(){return f(1);}', '定义'),
    ('int f(void x){return 0;} int main(){return 0;}', 'void'),
    ('int f(int **x){return 0;} int main(){return 0;}', '指针'),
    ('int f(int a[2][2]){return 0;} int main(){return 0;}', '一维'),
    ('int f(int n, int a[n]){return 0;} int main(){return 0;}', '常量'),
    ('int f(int x,int x){return x;} int main(){return 0;}', '重复'),
    ('int f(){return 1;} int value=f(); int main(){return value;}', '全局'),
    ('int value=rand(); int main(){return value;}', '全局'),
    ('int f(){return 1;} int main(){int x=f; return x;}', '函数'),
    ('int f(){return 1;} int main(){f=2; return 0;}', '函数'),
    ('int f(){return 1;} int f; int main(){return 0;}', '重复'),
    ('int f(){return 1;} int main(){int f=2; return f();}', '函数'),
    ('int main(){return missing();}', '函数'),
    ('void main(){return;}', 'main'),
    ('int main(int x){return x;}', 'main'),
])
def test_invalid_function_programs_fail_before_execution(source, match):
    with pytest.raises(CError, match=match):
        Program(source)


def test_existing_builtins_and_wrapped_statements_still_parse():
    program = Program('int value=abs(-2); srand(1); printf("%d", rand());')
    assert program.functions == {}


def test_seek_targets_record_owning_function_without_changing_locations():
    program = Program('''int global=1;
int helper(int x) {
  while(x<2) { x++; }
  return x;
}
int main() { return helper(global); }''')
    targets = program.targets()
    assert len(program.target_functions) == len(targets)
    assert {program.target_functions[t] for t in targets if t.line == 1} == {''}
    assert {program.target_functions[t] for t in targets if 2 <= t.line <= 4} == {'helper'}
    assert {program.target_functions[t] for t in targets if t.line == 6} == {''}
    assert program.target_functions[next(t for t in targets if t.kind == 'function')] == 'helper'


def test_call_reaches_includes_direct_and_transitive_function_targets():
    program = Program('''int leaf(){return 1;}
int middle(){return leaf();}
int outer(){return middle();}
int unrelated(){return 2;}
int main(){return outer()+unrelated();}''')
    assert program.call_reaches(['leaf'], 'leaf')
    assert program.call_reaches(['outer'], 'leaf')
    assert program.call_reaches(['unrelated', 'middle'], 'leaf')
    assert not program.call_reaches(['unrelated'], 'leaf')
    assert not program.call_reaches(['leaf'], 'outer')
    assert not program.call_reaches(['outer'], '')
    assert not program.call_reaches([], 'leaf')
    assert not program.call_reaches(['printf'], 'leaf')
