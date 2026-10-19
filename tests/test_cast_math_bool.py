import pytest
from cvisualizer.engine import Engine
from cvisualizer.errors import CError

def run(source, detail=False):
    engine=Engine(source); events=[]
    while engine.peek(): events.append(engine.step(expand_calls=detail))
    return engine,events

def test_cast_math_bool_long_long():
    e,events=run('#include <cmath>\nlong long n=9000000000LL; bool b=true; int x=(int)-3.8; double y=static_cast<double>(n)/2; double z=sqrt(9)+round(-2.5); printf("%lld %d",n,b+1);')
    v=e.runtime.snapshot()
    assert v['n']['type']=='long long' and v['n']['value']==9000000000
    assert v['b']['value'] is True and v['x']['value']==-3 and v['z']['value']==0
    assert e.runtime.output=='9000000000 2'
    assert any(event.booleans for event in events)

def test_const_cast_protects_object():
    run('int x=1; const int *p=&x; int *q=const_cast<int*>(p); *q=3;')
    with pytest.raises(CError,match='只读|const'):
        run('const int x=1; const int *p=&x; int *q=const_cast<int*>(p); *q=3;')

def test_boolean_short_circuit_and_detail():
    _,ev=run('int f(int x){bool b=x>1; return !b;} int main(void){int a=0; bool b=0 && ++a; int c=f(2);}',True)
    assert ev[-1].variables['a']['value']==0
    assert any(e.function and e.booleans for e in ev)
    assert not ev[-1].booleans

@pytest.mark.parametrize('expression',['sqrt(-1)','pow(1e300,2)','sin(1,2)','(int*)3','reinterpret_cast<int>(2)'])
def test_explicit_errors(expression):
    with pytest.raises(CError): run('double x='+expression+';')

def test_ll_limits_scanf_promotion():
    e=Engine('long long n=0; scanf("%lld", &n); long long m=-9223372036854775807LL-1; long long x=n+1LL; printf("%lld",x);')
    e.runtime.input_provider=lambda _: '9223372036854775806'
    while e.peek(): e.step()
    assert e.runtime.output=='9223372036854775807'
    assert e.runtime.snapshot()['m']['value']==-9223372036854775808
    with pytest.raises(CError,match='溢出'): run('long long n=9223372036854775807LL+1LL;')

def test_bool_casts_and_const_cast_destination():
    e,_=run('int x=2; bool a=(bool)x; _Bool b=static_cast<bool>(0); const int *p=const_cast<const int*>(&x);')
    assert e.runtime.snapshot()['a']['value'] is True
    assert e.runtime.snapshot()['b']['value'] is False
    with pytest.raises(CError): run('int x=2; const int *p=&x; int *q=(const volatile int*)p;')
    with pytest.raises(CError): run('int x=2; int *p=static_cast<int*>(&x);')

def test_quick_calls_hide_internal_booleans_and_detail_isolates():
    code='int f(int x){bool a=x>1; return !a;} int main(void){int v=f(2);}'
    _,quick=run(code)
    assert not quick[-1].booleans
    _,detail=run(code,True)
    assert any(e.function and e.booleans for e in detail)
    assert not detail[-1].booleans

@pytest.mark.parametrize('name,arguments,expected',[
    ('sqrt','9',3),('pow','2,3',8),('fabs','-3',3),('floor','-2.1',-3),
    ('ceil','-2.1',-2),('round','-2.5',-3),('round','4503599627370497.0',4503599627370497),
    ('trunc','-2.9',-2),('sin','0',0),('cos','0',1),('tan','0',0),
    ('asin','0',0),('acos','1',0),('atan','0',0),('atan2','0,1',0),
    ('exp','0',1),('log','1',0),('log10','100',2),('log2','8',3),('hypot','3,4',5),('fmod','-7,3',-1)])
def test_math_functions(name,arguments,expected):
    e,_=run('#include <math.h>\ndouble x='+name+'('+arguments+');')
    assert e.runtime.snapshot()['x']['value']==pytest.approx(expected)
    with pytest.raises(CError): run('double x='+name+'();')

@pytest.mark.parametrize('expr',['log(0)','log2(-1)','log10(-2)','asin(2)','acos(-2)','fmod(2,0)','exp(10000)','pow(-2,0.5)'])
def test_math_domain_and_rollback(expr):
    e=Engine('int x=1; double y='+expr+';')
    e.step(); before=e.runtime.snapshot()
    with pytest.raises(CError): e.step()
    assert e.runtime.snapshot()==before

def test_short_circuit_boolean_records_and_cap():
    e,events=run('int a=0; bool x=0 && ++a; bool y=1 || ++a; int z=!a; if(a==0) a=2;')
    assert e.runtime.snapshot()['a']['value']==2
    assert all('++a' not in b['expression'] or b['expression'].startswith(('0','1')) for ev in events for b in ev.booleans)
    assert any('operands' in b for ev in events for b in ev.booleans)
    _,ev=run('bool a[500]={0};')
    assert len(ev[0].booleans)<=16


def test_bool_printf_and_promotion():
    e,_=run('bool b=true; int a=b+b; printf("%d %d",b,a);')
    assert e.runtime.output=='1 2'

def test_boolean_comparison_is_not_recorded_twice():
    _,ev=run('int a=1; if(a>0) a=2;')
    records=next(e.booleans for e in ev if e.kind=='condition')
    assert len(records)==1 and records[0]['operands']==(1,0)


def test_macro_cast_kinds_do_not_collide():
    with pytest.raises(CError,match='指针转换'):
        run('#define BOTH(p) (const_cast<int*>(p), (int*)p)\nint x=1; const int *p=&x; int *q=BOTH(p);')
    e,_=run('#define CAST(p) const_cast<int*>(p)\nint x=1; const int *p=&x; int *q=CAST(p); *q=3;')
    assert e.runtime.snapshot()['x']['value']==3

@pytest.mark.parametrize('expr',['static_cast<int>(x)++','++static_cast<int>(x)','static_cast<int>(x)=3','const_cast<int*>(p)++'])
def test_named_cast_result_is_not_lvalue(expr):
    e=Engine('int x=1; const int *p=&x; '+expr+';')
    e.step(); e.step()
    with pytest.raises(CError): e.step()
    assert e.runtime.snapshot()['x']['value']==1

def test_nested_named_casts_preserve_precedence():
    e,_=run('int x=3; int a=static_cast<int>(static_cast<double>(x)+0.9)*2;')
    assert e.runtime.snapshot()['a']['value']==6


def test_distinct_equal_boolean_expressions_are_both_animated():
    _, events = run('int a=1; bool x=(a<2)&&(a<2);')
    comparisons = [record for record in events[-1].booleans
                   if record['expression'] == 'a < 2']
    assert len(comparisons) == 2


def test_extreme_named_cast_nesting_reports_a_c_error():
    source = 'int n=' + 'static_cast<int>(' * 1100 + '1' + ')' * 1100 + ';'
    with pytest.raises(CError, match='嵌套|语法'):
        Engine(source)
