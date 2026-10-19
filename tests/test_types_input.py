import pytest

from cvisualizer.engine import Engine
from cvisualizer.language import CError


def run(source, lines=(), expand=False):
    engine = Engine(source)
    supplied = iter(lines)
    calls = []
    def provide(prompt):
        calls.append(prompt)
        return next(supplied)
    engine.runtime.input_provider = provide
    events = []
    while engine.peek():
        events.append(engine.step(expand_calls=expand))
    return engine, events, calls


def test_long_arithmetic_parameters_and_return():
    e, _, _ = run('long int twice(long x){return x*2;} int main(){long n=3000000000L; long a[2]={n,twice(n)}; long *p=a; p[0]+=2; printf("%ld %ld",a[0],a[1]);}')
    assert e.runtime.output == '3000000002 6000000000'
    assert e.runtime.snapshot()['n']['type'] == 'long'


def test_chars_strings_arithmetic_and_output():
    e, _, _ = run(r'''char c='A'; char next=c+1; char a[5]="Hi"; char *p=a; p[1]='o'; printf("%c %d %s",next,c,a);''')
    assert e.runtime.output == 'B 65 Ho'
    assert e.runtime.snapshot()['a']['value'] == [72,111,0,0,0]


def test_scanf_all_types_and_existing_double():
    e, events, calls = run('int a;long b;float c;double d;char ch;char s[6];int n=scanf("%d %ld %f %lf %c %5s",&a,&b,&c,&d,&ch,s);printf("%d %ld %f %lf %c %s",a,b,c,d,ch,s);', ['12 3000000000 1.25 2.5 Z hello'])
    assert e.runtime.snapshot()['n']['value'] == 6
    assert e.runtime.output == '12 3000000000 1.250000 2.500000 Z hello'
    assert len(calls) == 1
    assert ('a', None) in next(x for x in events if x.text.startswith('int n')).writes


@pytest.mark.parametrize('expand', [False, True])
def test_function_input_not_repeated_in_replay(expand):
    e, _, calls = run('void read(double *p){scanf("%lf",p);}int main(){double x;read(&x);}', ['3.25'], expand)
    assert e.runtime.snapshot()['x']['value'] == 3.25
    assert len(calls) == 1


def test_buffer_and_char_whitespace_rules():
    e, _, calls = run('int a;int b;char c;char d;scanf("%d",&a);scanf("%d",&b);scanf("%c",&c);scanf(" %c",&d);', ['1 2', 'Z'])
    v = e.runtime.snapshot()
    assert [v[k]['value'] for k in ('a','b','c','d')] == [1,2,10,90]
    assert len(calls) == 2


def test_matching_failure_returns_count_and_preserves_unassigned():
    e, _, _ = run('int a=0;int b=9;int n=scanf("%d %d",&a,&b);', ['3 nope'])
    assert [e.runtime.snapshot()[k]['value'] for k in ('a','b','n')] == [3,9,1]


@pytest.mark.parametrize('source,line,message', [
    ('int a;scanf("%lf",&a);','2','类型'),
    ('char a[3];scanf("%s",a);','hello','容量'),
    ('int *p=0;scanf("%d",p);','1','空指针'),
    ('long a=9223372036854775807L;a++;','','溢出'),
])
def test_input_and_type_errors(source,line,message):
    with pytest.raises(CError, match=message):
        run(source,[line])


def test_cancel_inside_function_rolls_back_and_reuses_input_on_retry():
    from cvisualizer.controller import Controller
    responses = iter(['4', None, '8'])
    prompts = []
    def provider(prompt):
        prompts.append(prompt)
        return next(responses)
    c = Controller('void f(int *p){scanf("%d",p);scanf("%d",p);}int main(){int x=1;f(&x);}', input_provider=provider)
    c.step()
    c.step(expand_calls=True)
    assert c.state == 'paused'
    assert c.error is None
    assert c.engine.runtime.snapshot()['x']['value'] == 1
    c.step(expand_calls=True)
    while c.engine.peek():
        c.step(expand_calls=True)
    assert c.engine.runtime.snapshot()['x']['value'] == 8
    assert len(prompts) == 3
    c.reset()
    assert c.engine.runtime.input_provider is provider
    assert c.engine.runtime.input_text == ''


def test_character_display_and_long_promotion():
    from cvisualizer.views import display
    e, _, _ = run("char c='A';long x=2L;long n=x+2147483647;int i=c+1;")
    assert display(e.runtime.snapshot()['c']['value']) == "'A'"
    assert e.runtime.snapshot()['n']['value'] == 2147483649
    assert e.runtime.snapshot()['i']['value'] == 66


def test_scanf_width_literal_percent_and_array_loop():
    e, _, _ = run('char s[4];int a[3];scanf("%3s",s);for(int i=0;i<3;i++){scanf("%d",&a[i]);}int n;scanf(" %%%d",&n);', ['abc 4 5 6 %7'])
    v = e.runtime.snapshot()
    assert v['s']['value'] == [97,98,99,0]
    assert v['a']['value'] == [4,5,6]
    assert v['n']['value'] == 7


def test_long_minimum_char_escapes_and_promotion():
    e, _, _ = run(r'''long min=-9223372036854775808L;long x=5L;long y=-x;char c='\n';char z='\0';int n=c+z;''')
    assert e.runtime.snapshot()['min']['value'] == -(2**63)
    assert e.runtime.snapshot()['y']['value'] == -5
    assert e.runtime.snapshot()['n']['value'] == 10


def test_long_constant_array_size_and_char_function_return():
    e, _, _ = run("char next(char c){return c+1;}int main(){long a[3L]={1L,2L,3L};char c=next('A');}")
    assert e.runtime.snapshot()['a']['value'] == [1,2,3]
    assert e.runtime.snapshot()['c']['value'] == 66


def test_large_negative_literal_keeps_long_during_expression():
    e, _, _ = run('long x=-2147483648 / -1;int minimum=-2147483648;')
    assert e.runtime.snapshot()['x']['value'] == 2147483648
    assert e.runtime.snapshot()['minimum']['value'] == -2147483648


def test_input_dialog_stops_timer_and_cancel_can_retry(app):
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QInputDialog
    from cvisualizer.window import MainWindow
    w = MainWindow()
    w.load_code('char c;scanf(" %c",&c);printf("%c",c);', [])
    w.step()
    w.play()
    seen = []
    def respond(accept):
        dialog = next(x for x in app.topLevelWidgets() if isinstance(x, QInputDialog))
        seen.append(w.timer.isActive())
        dialog.setTextValue('Z')
        dialog.accept() if accept else dialog.reject()
    QTimer.singleShot(0, lambda: respond(False))
    w.on_tick()
    assert w.controller.state == 'paused'
    assert w.controller.engine.runtime.snapshot()['c']['value'] is None
    QTimer.singleShot(0, lambda: respond(True))
    w.step()
    assert w.controller.engine.runtime.snapshot()['c']['value'] == 90
    assert next(box for key, box in w.visuals.boxes.items() if key[0] == 'c').brush().color().name() == '#dcfce7'
    assert seen == [False, False]
    w.stop()
    w.close()
