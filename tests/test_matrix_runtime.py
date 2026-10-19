from copy import deepcopy
import pytest
from cvisualizer.arrays import Array, Matrix
from cvisualizer.engine import Engine
from cvisualizer.errors import CError


def run(code):
    engine = Engine(code)
    events = []
    while engine.peek():
        events.append(engine.step(expand_calls=True))
    return engine, events


def test_sparse_matrix_snapshot():
    a = Matrix(1000000000, 1000000000, 0)
    old = deepcopy(a)
    a[999999999, 999999999] = 3
    assert old[999999999, 999999999] == 0
    assert a[999999999, 999999999] == 3
    assert isinstance(a[0], Array)


def test_initialization_and_tuple_activity():
    e, events = run('int a[][3]={{1},{2,3}};a[1][2]=a[0][0]+4;int x=a[1][2];')
    a = e.runtime.snapshot()['a']['value']
    assert a == [[1,0,0],[2,3,5]]
    assert any(('a', (1,2)) in event.writes for event in events)
    assert events[0].variables['a']['value'][1,2] == 0


def test_flat_initialization_and_runtime_dimensions():
    e, _ = run('int a[][2]={1,2,3};int n=2;int m=3;int b[n++][m++];b[1][2]=7;')
    v = e.runtime.snapshot()
    assert v['a']['value'] == [[1,2],[3,0]]
    assert (len(v['b']['value']), v['b']['value'].columns) == (2,3)
    assert (v['n']['value'], v['m']['value']) == (3,4)


def test_parameters_row_pointers_and_const():
    e, _ = run('int f(int a[][3]){a++;a[0][1]+=4;return a[0][1];}int main(){int a[2][3]={{1},{2,3}};int *p=a[0];p[2]=8;int x=f(a);int y=*(*(a+1)+1);}')
    v = e.runtime.snapshot()
    assert v['x']['value'] == v['y']['value'] == 7
    assert v['a']['value'][0,2] == 8


def test_variable_column_parameter_and_forwarding():
    e, _ = run('int f(int n,int a[][n]){return a[1][n-1];}int g(int a[][3]){return f(3,a);}int main(){int a[2][3]={1,2,3,4,5,6};int x=g(a);}')
    assert e.runtime.snapshot()['x']['value'] == 6


def test_character_rows_and_string_library():
    e, _ = run('char a[2][6]={"ab","cd"};strcpy(a[1],a[0]);strcat(a[1],"x");printf("%s %s",a[0],a[1]);')
    assert e.runtime.output == 'ab abx'


def test_scanf_scalar_and_character_row():
    e = Engine('int a[2][3]={{0}};char s[2][5];scanf("%d %4s",&a[1][2],s[1]);printf("%d %s",a[1][2],s[1]);')
    e.runtime.input_provider = lambda request: '42 hey'
    while e.peek():
        e.step()
    assert e.runtime.output == '42 hey'


def test_large_matrix_engine_snapshots_and_transfers():
    e, events = run('int a[1000000000][1000000000]={{0}};a[999999999][999999999]=3;int x=a[999999999][999999999];')
    assert events[0].variables['a']['value'][999999999,999999999] == 0
    assert e.runtime.snapshot()['x']['value'] == 3
    assert any(source[1] == (999999999,999999999) for event in events for source, target in event.transfers)


@pytest.mark.parametrize('expand', [False, True])
def test_function_effects_const_reads_and_scalar_transfers(expand):
    e = Engine('int read(const int a[][3]){return a[0][1];}void set(int a[][3],int x){a[1][2]=x;}int main(){int a[2][3]={{1,7},{0}};int x=read(a);set(a,x);}')
    events = []
    while e.peek():
        events.append(e.step(expand_calls=expand))
    assert e.runtime.snapshot()['a']['value'][1,2] == 7
    assert any(('a', (1,2)) in event.writes for event in events)
    assert any(event.variables.get('a', {}).get('value', None) is not None for event in events)


def test_mixed_complete_rows_and_flat_remainder():
    e, _ = run('int a[][3]={{1,2},3,4};int b[][2]={1,2,{3}};')
    v = e.runtime.snapshot()
    assert v['a']['value'] == [[1,2,0],[3,4,0]]
    assert v['b']['value'] == [[1,2],[3,0]]


@pytest.mark.parametrize('code', [
    'int a[2][3];a[2][0]=1;', 'int a[2][3];a[0][3]=1;',
    'int a[2][0];', 'int a[1][2][3];', 'int a[1][2]={{1,2,3}};',
    'void f(int a[][2]){}int main(){int a[2][3];f(a);}',
    'void f(const int a[][2]){a[0][0]=1;}int main(){int a[2][2];f(a);}',
    'const int a[1][2]={{1}};int *p=a[0];',
    'int a[2][3]={{0}};int *p=a[0]+3;int x=*p;',
    'int a[2][3]={{0}};int *p=a[0];p+=4;',
    'int a[2][3];a[0]=a[1];',
    'int a[2][3];int x=a[0][0];',
    'int a[2][]={{1}};',
    'int n=2;int a[2][n]={{0}};',
    'int a[2][3]={{0}};int x=a[1]-a[0];',
    'int a[2][3]={1,{2}};',
    'char a[2][3]={"a","b"};strcpy(a[0],"long");',
])
def test_invalid_matrices_are_c_errors(code):
    with pytest.raises(CError):
        run(code)


def test_const_matrix_forwarding_and_row_const_alias():
    e, _ = run('int f(const int a[][2]){const int *p=a[1];return p[1];}int g(const int a[][2]){return f(a);}int main(){const int a[2][2]={{1,2},{3,4}};int x=g(a);}')
    assert e.runtime.snapshot()['x']['value'] == 4


@pytest.mark.parametrize('code', [
    'void f(int a[][2]){}int main(){const int a[2][2]={{0}};f(a);}',
    'void f(const int a[][2]){int *p=a[0];}int main(){int a[2][2]={{0}};f(a);}',
    'void f(const int a[][2]){const int *p=a[0];p[0]=1;}int main(){int a[2][2]={{0}};f(a);}',
    'char a[2][3]={"abc","def"};int x=strlen(a[0]);',
    'char a[2][3]={{0}};scanf("%3s",a[0]);',
])
def test_const_aliases_and_character_row_boundaries(code):
    e = Engine(code)
    e.runtime.input_provider = lambda request: 'abc'
    with pytest.raises(CError):
        while e.peek():
            e.step(expand_calls=True)


@pytest.mark.parametrize('expand', [False, True])
def test_function_tuple_effects_and_saved_snapshots(expand):
    e = Engine('void copy(int a[][2]){a[1][1]=a[0][1];}int main(){int a[2][2]={{0,9},{0}};copy(a);}')
    events = []
    while e.peek():
        events.append(e.step(expand_calls=expand))
    before = next(event.variables['a']['value'] for event in events if 'a' in event.variables)
    assert before[1,1] == 0
    assert e.runtime.snapshot()['a']['value'][1,1] == 9
    assert any(('a', (0,1)) in event.reads for event in events)
    assert any(source[:2] == ('a', (0,1)) and target[:2] == ('a', (1,1))
               for event in events for source, target in event.transfers)
