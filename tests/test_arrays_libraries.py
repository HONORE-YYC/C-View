import pytest
from cvisualizer.engine import Engine
from cvisualizer.language import CError, Program


def run(code, expand=False):
    e = Engine(code)
    events = []
    while e.peek():
        events.append(e.step(expand_calls=expand))
    return e, events


def test_inferred_arrays_and_variable_capacity_evaluated_once():
    e, _ = run('int a[]={1,2,3};char s[]="hi";int n=4;int b[n++];b[3]=8;n=2;')
    v = e.runtime.snapshot()
    assert v['a']['value'] == [1,2,3]
    assert v['s']['value'] == [104,105,0]
    assert len(v['b']['value']) == 4
    assert v['b']['value'][3] == 8


def test_large_array_snapshots_do_not_allocate_by_capacity():
    import tracemalloc
    tracemalloc.start()
    try:
        e, events = run('int a[1000000000]={0};a[999999999]=7;int *p=a+999999999;*p=8;')
        assert tracemalloc.get_traced_memory()[1] < 20_000_000
    finally:
        tracemalloc.stop()
    assert len(e.runtime.snapshot()['a']['value']) == 1000000000
    assert events[0].variables['a']['value'][999999999] == 0
    assert events[1].variables['a']['value'][999999999] == 7
    assert e.runtime.snapshot()['a']['value'][999999999] == 8


@pytest.mark.parametrize('expand', [False, True])
def test_qualified_parameters_and_const_pointer_can_read(expand):
    e, _ = run('int sum(const int a[],const int n);int sum(const int *restrict a,int n){volatile int s=0;for(int i=0;i<n;i++){s+=a[i];}return s;}int main(){int a[]={3,4};int x=sum(a,2);}', expand)
    assert e.runtime.snapshot()['x']['value'] == 7


@pytest.mark.parametrize('code', [
    'void f(const int *p){*p=9;}int main(){int x=1;f(&x);}',
    'void f(int *const p){p++;}int main(){int a[2];f(a);}',
    'void f(const int x){x=2;}int main(){f(1);}',
    'void f(const int *p){int *q=p;*q=9;}int main(){int x=1;f(&x);}',
    'void f(const char *p){scanf("%c",p);}int main(){char c=65;f(&c);}',
])
def test_const_writes_and_dropping_const_fail(code):
    with pytest.raises(CError, match='const|只读'):
        run(code)


def test_string_library_and_numeric_conversions():
    e, _ = run('''#include <string.h>
#include <stdlib.h>
int main(){char s[20]="ab";strcat(s,"cd");int n=strlen(s);char copy[20];strcpy(copy,s);strncat(copy,"XYZ",2);int same=strcmp(s,"abcd");int prefix=strncmp(copy,s,4);long value=atol("  -3000000000x");int i=atoi("42x");double d=atof("1.25e2tail");long positive=labs(value);printf("%s %s %d %ld %lf",s,copy,i,positive,d);}''')
    assert e.runtime.output == 'abcd abcdXY 42 3000000000 125.000000'
    v = e.runtime.snapshot()
    assert [v[k]['value'] for k in ('n','same','prefix')] == [4,0,0]


def test_strncpy_padding_and_string_search():
    e, _ = run('''#include <cstring>
int main(){char a[6];strncpy(a,"hi",6);char s[]="abcabc";char *p=strchr(s,'b');char *q=strstr(s,"cab");char *r=strrchr(s,'b');int x=p-s;int y=q-s;int z=r-s;}''')
    v=e.runtime.snapshot()
    assert v['a']['value'] == [104,105,0,0,0,0]
    assert [v[k]['value'] for k in ('x','y','z')] == [1,2,4]


@pytest.mark.parametrize('code,message', [
    ('int a[];', '容量'),
    ('int n=0;int a[n];', '正整数'),
    ('int n=2;int a[n]={1};', '初始化'),
    ('char a[3];strcpy(a,"long");', '越界|容量'),
    ('const char *s="hi";strcpy(s,"no");', 'const|只读'),
])
def test_invalid_arrays_and_library_targets(code,message):
    with pytest.raises(CError, match=message):
        run(code)


@pytest.mark.parametrize('size', [1000000, 1000000000])
def test_large_array_scroll_reaches_last_element_without_many_items(app, size):
    from cvisualizer.views import MemoryView
    e, _ = run(f'int a[{size}];a[{size-1}]=7;int *p=&a[{size-1}];')
    view = MemoryView()
    view.resize(650,600)
    view.show()
    view.render(e.runtime.snapshot(), [], e.last, animate=False)
    app.processEvents()
    assert len(view.scene().items()) < 400
    view.array_scroll.setValue(view.array_scroll.maximum())
    app.processEvents()
    box = next(b for (name,i,_),b in view.boxes.items() if i == size-1)
    assert '7' in box.toolTip()
    assert len(view.scene().items()) < 400
    assert any(marker.isVisible() and key[0] == 'address' for key, marker in view.motion.pointers.items())
    view.close()


def test_large_stack_and_queue_models_are_lazy():
    from cvisualizer.structures import Binding, describe
    e, _ = run('int a[1000000000]={0};int front=999999999;int rear=2;int top=999999999;')
    v = e.runtime.snapshot()
    queue = describe(Binding('a','queue',front='front',rear='rear'),v)
    assert queue.active == [999999999,0,1]
    assert queue.logical == [0,0,0]
    stack = describe(Binding('a','stack',top='top'),v)
    assert len(stack.active) == 1000000000
    assert stack.logical[:3] == [0,0,0]


def test_string_literals_are_reused_in_loops():
    e, _ = run('int n=0;for(int i=0;i<200;i++){n+=strlen("abc");}')
    assert e.runtime.snapshot()['n']['value'] == 600
    assert len(e.runtime.literals) == 1


@pytest.mark.parametrize('expand',[False,True])
def test_const_pointer_return_and_array_changes_in_function(expand):
    e, _ = run('const char *f(const char *p){return p+1;}void g(int a[]){a[99999]=7;}int main(){const char *s=f("abc");int a[100000];g(a);printf("%s",s);}', expand)
    assert e.runtime.output == 'bc'
    assert e.runtime.snapshot()['a']['value'][99999] == 7


def test_readonly_escapes_and_partial_string_copy_fail_safely():
    e = Engine('char a[3]="ab";strcat(a,"cd");')
    e.step()
    with pytest.raises(CError, match='越界'):
        e.step()
    assert e.runtime.snapshot()['a']['value'] == [97,98,0]
    for code in ('const int x=1;int *p=&x;',
                 'const int a[]={1};int *p=a;',
                 'void f(const int *p){int *q=&*p;}int main(){int a=1;f(&a);}'):
        with pytest.raises(CError, match='const'):
            run(code)


def test_bounded_string_functions_do_not_require_source_terminator():
    e, _ = run("char a[2]={'a','b'};char b[2];strncpy(b,a,2);int same=strncmp(a,b,2);char s[5]=\"X\";strncat(s,a,2);")
    v=e.runtime.snapshot()
    assert v['b']['value'] == [97,98]
    assert v['same']['value'] == 0
    assert v['s']['value'] == [88,97,98,0,0]


def test_empty_string_inference_and_no_arbitrary_string_length_limit():
    e, _ = run('char empty[]="";char text[5002]={0};for(int i=0;i<5001;i++){text[i]=65;}long n=strlen(text);')
    assert e.runtime.snapshot()['empty']['value'] == [0]
    assert e.runtime.snapshot()['n']['value'] == 5001


@pytest.mark.parametrize('expand', [False, True])
def test_array_parameter_dimension_evaluates_in_callee_once(expand):
    e, _ = run('void f(int n,int a[n++]){printf("%d",n);a[n-1]=7;}int main(){int a[3];f(2,a);}', expand)
    assert e.runtime.output == '3'
    assert e.runtime.snapshot()['a']['value'][2] == 7


def test_extreme_array_fine_scroll_and_last_element_are_visible(app):
    from cvisualizer.views import MemoryView
    from PySide6.QtGui import QWheelEvent
    from PySide6.QtCore import QPoint, QPointF, Qt
    for size in (1000000000000, 9223372036854775807):
        e, _ = run(f'int a[{size}L];int *p=&a[{size-1}L];')
        v = MemoryView()
        v.resize(650,600)
        v.show()
        v.render(e.runtime.snapshot(), [], e.last, animate=False)
        # Pixel scrolling must work even when one native scrollbar unit spans many rows.
        for _ in range(50):
            event = QWheelEvent(QPointF(50,200), QPointF(50,200), QPoint(0,-112), QPoint(),
                                Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier,
                                Qt.ScrollPhase.ScrollUpdate, False)
            v.wheelEvent(event)
        assert any(index == 100 for name,index,identity in v.boxes)
        v.array_scroll.setValue(v.array_scroll.maximum())
        key = next(k for k in v.boxes if k[1] == size-1)
        assert v._visible_box(key)
        v.close()
