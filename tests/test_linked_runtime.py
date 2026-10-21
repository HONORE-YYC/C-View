import pytest
from cvisualizer.engine import Engine
from cvisualizer.language import Program, CError


def run(source, detail=False):
    e=Engine(source)
    events=[]
    while e.peek(): events.append(e.step(expand_calls=detail))
    return e,events


def test_structural_linked_type_recognition_and_fallback():
    p=Program('typedef double Number; typedef struct Renamed { struct Renamed *following; Number item; } Node; struct Other{int x;int y;};int main(){Node n;}')
    assert p.linked_types == {'struct Renamed': {'data':'item','next':'following'}}
    e,_=run(p.source)
    assert e.runtime.snapshot()['n']['linked_node']=={'data':'item','next':'following'}


def test_new_reference_parameter_delete_and_heap_identity():
    source='typedef struct N{int value;struct N *link;}N,*List; int InitList(List &head){head=new N;head->link=0;return 1;}int main(){List first=0;InitList(first);first->value=7;List second=new N();second->link=first;first=0;delete second;}'
    e,events=run(source,True)
    s=e.runtime.snapshot()
    heaps=[(n,c) for n,c in s.items() if c.get('linked_node')]
    assert len(heaps)==1
    name,cell=heaps[0]
    assert s[name+'.value']['value']==7
    identities={c['identity'] for event in events for c in event.variables.values() if c.get('linked_node')}
    assert len(identities)==2
    with pytest.raises(CError,match='悬空|释放'):
        run('struct N{int x;struct N *next;};int main(){struct N *p=new struct N();delete p;p->x=1;}')


def test_heap_rolls_back_with_failed_function_call():
    e=Engine('struct N{int x;struct N *next;};void bad(){struct N *p=new struct N();int a=1/0;}int main(){bad();}')
    with pytest.raises(CError):
        while e.peek():e.step()
    assert not e.runtime.heap

def test_bare_structure_tag_allocation():
    e,_=run('struct Node{int x;struct Node *next;};int main(){struct Node *p=new Node();int n=p->x;}')
    assert e.runtime.snapshot()['n']['value']==0


def test_source_coordinates_and_input_retry_restore_heap_and_reference():
    from cvisualizer.formatted_io import InputCancelled
    source='typedef struct N{int x;struct N *next;}N,*List;\nvoid init(List &p){\n  p=new N();\n  scanf("%d",&p->x);\n}\nint main(){\n  List p=0;\n  init(p);\n}'
    e=Engine(source)
    e.step()
    while e.peek().line != 8:e.step()
    before=e.runtime.snapshot()
    with pytest.raises(InputCancelled):e.step(expand_calls=True)
    assert e.runtime.snapshot()==before and not e.runtime.heap
    e.runtime.input_provider=lambda request:'42'
    events=[]
    while e.peek():events.append(e.step(expand_calls=True))
    heap=next(n for n,c in e.runtime.snapshot().items() if c.get('linked_node'))
    assert e.runtime.snapshot()[heap+'.x']['value']==42
    assert any(event.line==3 and event.column==3 for event in events)


@pytest.mark.parametrize('fields', ['int x;int y;struct N *p;', 'int x[2];struct N *p;', 'struct N *p;struct N *q;', 'struct N value;int x;'])
def test_nonmatching_shapes_are_not_linked(fields):
    if 'struct N value' in fields:
        with pytest.raises(CError):Program('struct N{'+fields+'};int main(){}')
    else:
        assert Program('struct N{'+fields+'};int main(){}').linked_types=={}


def test_user_initlist_sample():
    # Verbatim relevant declarations/body from the attached 2链表的初始化.cpp.
    sample = """#include<stdio.h>
#define MAXSIZE 100
#include<cstdlib>
#define OK 1
#define OVERFLOW -2
#define ERROR -1
typedef int ElemType;
typedef struct LNode{
    ElemType data;
    struct LNode *next;
}LNode,*LinkList;
LinkList L;
typedef int Status;
Status InitList(LinkList &L){
    L=new LNode;
    L->next=NULL;
    return OK;
}
"""
    e,_=run(sample+'\nint main(){InitList(L);L->data=9;}')
    assert e.program.linked_types=={'struct LNode':{'data':'data','next':'next'}}
    assert len(e.runtime.heap)==1

def test_delete_rollback_restores_existing_heap_and_alias_identity():
    e=Engine('struct N{int x;struct N *next;};void bad(struct N *p){delete p;int a=1/0;}int main(){struct N *p=new struct N();bad(p);}')
    while not e.peek().location.text.startswith('bad('):e.step()
    before=e.runtime.snapshot()
    with pytest.raises(CError):e.step()
    assert e.runtime.snapshot()==before
    assert e.runtime.find_identity(before['p']['value'].identity)


def test_freed_heap_cannot_be_resurrected_by_reference_parameter():
    source='typedef struct N{int x;struct N *next;}N;void bad(N &ref,N *p){delete p;p->x=1;}int main(){N *p=new N();bad(*p,p);}'
    with pytest.raises(CError,match='悬空|释放'):run(source)

def test_new_preserves_named_cast_metadata_on_same_and_following_lines():
    source='struct N{int x;struct N *next;};int main(){const int a=2;const int *p=&a;struct N *n=new struct N();int *q=const_cast<int*>(p);\nint *r=const_cast<int*>(p);delete n;int *s=const_cast<int*>(p);int b=static_cast<int>(2.9);}'
    e,_=run(source)
    assert e.runtime.snapshot()['b']['value']==2


def test_unsupported_const_reference_is_rejected_and_hidden_delete_is_private():
    with pytest.raises(CError,match='引用'):
        Program('void bad(const int &x){x=2;}int main(){int a=1;bad(a);}')
    with pytest.raises(CError):
        Program('int main(){__cv_delete(0);}')


def test_deleted_heap_reference_alias_disappears_from_detail_snapshot():
    e,events=run('typedef struct N{int x;struct N *next;}N;void destroy(N &ref,N *p){delete p;}int main(){N *p=new N();destroy(*p,p);}',True)
    deletion=next(event for event in events if event.function=='destroy' and 'delete p' == event.text)
    assert not any(cell.get('linked_node') for cell in deletion.variables.values())

def test_locations_show_user_new_delete_and_reference_spellings():
    e,events=run('typedef struct N{int x;struct N *next;}N;void clear(N * &p){delete p;p=0;}int main(){N *p=new N();clear(p);}',True)
    texts=[event.text for event in events]
    assert any('new N()' in text for text in texts)
    assert 'delete p' in texts
    assert any('&p' in text for text in texts if 'clear(' in text)
    assert not any('sizeof' in text or '__cv_delete' in text for text in texts)

def test_reference_marker_is_scoped_by_exact_parameter_coordinates():
    e,_=run('void f(int &x){x=2;}void g(int x){x=9;}int main(){int x=1;f(x);g(x);}')
    assert e.runtime.snapshot()['x']['value']==2

@pytest.mark.parametrize('result', ['N *', 'struct N *', 'N * const', 'const N *'])
def test_pointer_returns_compose_with_reference_parameters(result):
    source='typedef struct N{int x;struct N *next;}N; '+result+' init(N *&p){p=new N();return p;} int main(){N *p=0;init(p);p->x=7;}'
    e,_=run(source)
    assert len(e.runtime.heap)==1
    identity=e.runtime.snapshot()['p']['value'].identity
    assert e.runtime.find_identity(identity)[1].value.fields['x'].value==7


@pytest.mark.parametrize('result,expr', [('long long', '7'), ('const long long', '7'), ('double','7.0'), ('N', '*p')])
def test_multiline_return_headers_compose_with_reference_parameters(result,expr):
    source='typedef struct N{int x;struct N *next;}N;\n'+result+'\n init(\nN *\n &p\n){p=new N();return '+expr+';}\nint main(){N *p=0;init(p);}'
    e,events=run(source,True)
    assert len(e.runtime.heap)==1
    assert any('init(' in event.text and '&p' in event.text for event in events)
