import pytest
from cvisualizer.engine import Engine
from cvisualizer.language import CError


def run(source, expand=False):
    engine = Engine(source)
    events=[]
    while engine.peek(): events.append(engine.step(expand_calls=expand))
    return engine,events


def test_members_initialization_copy_and_stable_addresses():
    e,_=run('struct P{int x;int data[3];}; int main(){struct P p={2,{3}},q;int *a=&q.x;q=p;q.x++;int n=*a+p.data[1];}')
    s=e.runtime.snapshot()
    assert s['p']['is_struct']
    assert s['p.x']['value']==2 and s['q.x']['value']==3
    assert s['p.data']['value']==[3,0,0] and s['n']['value']==3
    assert s['p.x']['identity']!=s['q.x']['identity']
    assert s['p.x']['struct_owner']=='P' and s['p.x']['struct_root']=='p'


def test_nested_pointer_and_byvalue_function():
    e,_=run('struct P{int x;};struct Q{struct P p;int y;};struct P inc(struct P p){p.x++;return p;}void set(struct Q *q){q->p.x=7;}int main(){struct Q q={{2},3};set(&q);struct P p=inc(q.p);int n=q.p.x+p.x;}')
    assert e.runtime.snapshot()['n']['value']==15


def test_const_and_dangling_members():
    with pytest.raises(CError,match='const'):
        run('struct P{int x;};int main(){const struct P p={2};p.x=3;}')
    with pytest.raises(CError,match='悬空'):
        run('struct P{int x;};int main(){int *p;{struct P q={2};p=&q.x;}int x=*p;}')


def test_sparse_struct_array_and_pointer_arithmetic():
    e,_=run('struct P{int x;};int main(){struct P a[1000000]={{1},{2}};struct P *p=a;p++;p->x+=3;a[999999].x=7;int n=a[1].x+a[999999].x;}')
    s=e.runtime.snapshot()
    assert s['n']['value']==12
    assert len(e.runtime.cell('a',None).value.elements)==3
    assert s['a[1].x']['struct_root']=='a'


def test_member_strings_scanf_and_function_detail_visibility():
    e=Engine('struct P{char text[8];int x;};void f(struct P *p){p->x++;}int main(){struct P p={"ok",1};scanf("%d %s",&p.x,p.text);f(&p);printf("%s %d",p.text,p.x);}')
    e.runtime.input_text='4 yes'
    events=[]
    while e.peek():events.append(e.step(expand_calls=True))
    assert e.runtime.output=='yes 5'
    assert any(event.function=='f' and any(name.endswith('.x') for name in event.variables) for event in events)


def test_matrix_member_nested_initialization():
    e,_=run('struct G{int a[2][3];};int main(){struct G g={{{1,2},{3}}};int n=g.a[1][0]+g.a[0][2];}')
    assert e.runtime.snapshot()['n']['value']==3


def test_shadowing_hides_outer_members_and_copy_transfers_match_fields():
    e=Engine('struct P{int x;int y;};int main(){struct P p={1,2};struct P q;p=q;{int p=3;p++;}}')
    events=[]
    while e.peek():events.append(e.step())
    copy=next(event for event in events if event.transfers)
    assert all(source[0].rsplit('.',1)[-1]==target[0].rsplit('.',1)[-1] for source,target in copy.transfers)
    shadow=next(event for event in events if event.variables.get('p',{}).get('value')==3)
    assert 'p.x' not in shadow.variables


def test_failed_member_write_rolls_back_and_const_pointer_protects_nested_field():
    e=Engine('struct P{int x;};int main(){struct P p={3};p.x=1/0;}')
    while 'p.x' not in e.runtime.snapshot():e.step()
    before=e.runtime.snapshot()
    with pytest.raises(CError,match='除零'):e.step()
    assert e.runtime.snapshot()==before
    with pytest.raises(CError,match='const'):
        run('struct P{int a[2];};int main(){struct P p={{1,2}};const struct P *q=&p;q->a[0]=9;}')


def test_addresses_of_structure_array_members():
    e,_=run('struct P{int x;};int main(){struct P a[2]={{1},{2}};int *p=&a[0].x;struct P *q=a+1;int *r=&q->x;*p=4;int n=*p+*r;}')
    assert e.runtime.snapshot()['n']['value']==6


def test_nested_aggregate_allocation_obeys_execution_budget():
    definitions=['struct A0{int x;};']
    for level in range(1,24):
        definitions.append(f'struct A{level}'+'{'+f'struct A{level-1} a,b;'+'};')
    engine=Engine(''.join(definitions)+'int main(){struct A23 value;}',max_steps=80)
    with pytest.raises(CError,match='步数'):
        while engine.peek():engine.step()


def test_returned_structure_members_evaluate_function_once():
    e,_=run('int calls=0;struct P{int x;};struct Q{struct P p;};struct Q f(){calls++;struct Q q={{3}};return q;}int main(){int n=f().p.x;}')
    assert e.runtime.snapshot()['n']['value']==3
    assert e.runtime.snapshot()['calls']['value']==1
    with pytest.raises(CError):
        run('struct P{int x;};struct P f(){struct P p={3};return p;}int main(){f().x=4;}')
    with pytest.raises(CError,match='临时结构体的数组成员'):
        run('struct P{int a[2];};struct P f(){struct P p={{3}};return p;}int main(){int x=f().a[0];}')


def test_const_member_and_self_pointer():
    e,_=run('struct N{int x;struct N *next;};int main(){struct N n={3,0};n.next=&n;int x=n.next->x;}')
    assert e.runtime.snapshot()['x']['value']==3
    with pytest.raises(CError,match='const'):
        run('struct P{const int x;};int main(){struct P p={1},q={2};p=q;}')
