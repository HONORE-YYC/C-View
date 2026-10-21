import pytest
from cvisualizer.engine import Engine
from cvisualizer.language import CError
from cvisualizer.formatted_io import InputCancelled

HEADER = '#include <iostream>\nusing namespace std;\n'


def run(code, lines=(), detail=False):
    engine = Engine(HEADER + code)
    supplied = iter(lines)
    prompts = []
    def provide(prompt):
        prompts.append(prompt)
        return next(supplied)
    engine.runtime.input_provider = provide
    events = []
    while engine.peek():
        events.append(engine.step(expand_calls=detail))
    return engine, events, prompts


def test_output_chain_types_literals_and_expressions():
    e, _, _ = run(r'''int main(){char ch='B';bool ok=true;double d=1.23456789;
        cout << "结果：" << 2+3 << ' ' << ch << ' ' << ok << ' ' << d << endl;}''')
    assert e.runtime.output == '结果：5 B 1 1.23457\n'


def test_string_literal_stops_at_nul_like_character_array():
    e, _, _ = run(r'''int main(){char s[4]="a\0b";cout<<"a\0b"<<s;}''')
    assert e.runtime.output == 'aa'


def test_character_expression_retains_cpp_character_type():
    e, _, _ = run("int main(){cout<<(0,'A')<<' '<<('A'+0)<<' '<<static_cast<int>('A');}")
    assert e.runtime.output == 'A 65 65'


def test_qualified_streams_preserve_literals_and_source_lines():
    e = Engine('#include<iostream>\nint main(){\nstd::cout << "std::cin using namespace std;" << std::endl;\n}')
    event = e.step()
    assert event.line == 3 and event.column == 1
    assert e.runtime.output == 'std::cin using namespace std;\n'


def test_input_all_types_shared_line_and_output():
    e, events, prompts = run('int main(){int a;long b;long long c;double d;float f;char ch;bool yes;char s[6];cin>>a>>b>>c>>d>>f>>ch>>yes>>s;cout<<a<<" "<<b<<" "<<c<<" "<<d<<" "<<f<<" "<<ch<<" "<<yes<<" "<<s;}', ['2 3000000000 8000000000 2.5 1.25 A 1 hello'])
    assert e.runtime.output == '2 3000000000 8000000000 2.5 1.25 A 1 hello'
    assert len(prompts) == 1 and prompts[0]['kind'] == 'cin'
    assert len(next(ev for ev in events if ev.text.startswith('cin')).writes) >= 8


def test_array_targets_evaluated_once_in_order():
    e, _, _ = run('int main(){int a[2];int i=0;cin>>a[i++]>>a[i++];cout<<a[0]<<a[1]<<i;}', ['3 4'])
    assert e.runtime.output == '342'


@pytest.mark.parametrize('detail', [False, True])
def test_linked_node_input_in_custom_function(detail):
    e, events, _ = run('typedef struct N{int data;struct N *next;}N,*Link;void read(Link &p){p=new N();cin>>p->data;}int main(){Link head;read(head);cout<<head->data;}', ['42'], detail)
    assert e.runtime.output == '42'
    assert any(name.endswith('.data') and cell['value'] == 42 for name, cell in e.runtime.snapshot().items())
    if detail:
        assert any(name.endswith('.data') for ev in events for name, _ in ev.writes)


def test_input_cancel_rolls_back_whole_chain_and_retries_buffer():
    e = Engine(HEADER+'int main(){int a=7;int b=8;cin>>a>>b;}')
    e.step(); e.step()
    lines = iter(['3', None])
    e.runtime.input_provider = lambda prompt: next(lines)
    with pytest.raises(InputCancelled):
        e.step()
    assert e.runtime.snapshot()['a']['value'] == 7
    assert e.runtime.snapshot()['b']['value'] == 8
    e.runtime.input_provider = lambda prompt: '4'
    e.step()
    assert e.runtime.snapshot()['a']['value'] == 3
    assert e.runtime.snapshot()['b']['value'] == 4


def test_scanf_and_cin_share_input_buffer():
    e, _, prompts = run('int main(){int a;char c;int b;scanf("%d",&a);cin>>c>>b;cout<<a<<c<<b;}', ['3 X 7'])
    assert e.runtime.output == '3X7' and len(prompts) == 1


@pytest.mark.parametrize('code,line,match', [
    ('const int x=0;cin>>x;', '1', 'const'),
    ('char s[3];cin>>s;', 'hello', '容量'),
    ('int x;cin>>x;', 'oops', '输入'),
    ('bool x;cin>>x;', '2', '0.*1'),
    ('int *p=0;cin>>*p;', '1', '空指针'),
    ('cin>>3;', '1', '目标'),
    ("cout<<'中';", '', '0–255'),
])
def test_bad_input_reports_error_without_writing(code, line, match):
    with pytest.raises(CError, match=match):
        run('int main(){'+code+'}', [line])


def test_stream_macros_and_multiline_chain():
    e, _, _ = run('#define OUT cout\nint main(){OUT\n<< "ok"\n<< endl;}')
    assert e.runtime.output == 'ok\n'


def test_ordinary_shift_does_not_become_stream_io():
    with pytest.raises(CError, match='运算符'):
        run('int main(){int x=1<<2;}')


def test_const_struct_character_array_cannot_be_written():
    with pytest.raises(CError, match='const'):
        run('struct S{char s[4];};int main(){struct S a={"old"};const struct S *p=&a;cin>>p->s;}', ['new'])


def test_char_pointer_and_matrix_row_input():
    e, _, _ = run('int main(){char s[5];char *const p=s;char rows[2][4];cin>>p>>rows[1];cout<<p<<rows[1];}', ['word xyz'])
    assert e.runtime.output == 'wordxyz'


@pytest.mark.parametrize('detail', [False, True])
def test_loop_creates_linked_list_from_input(detail):
    e, _, prompts = run('''typedef int ElemType;typedef struct LNode{ElemType data;struct LNode *next;}LNode,*LinkList;
        void CreateList_H(LinkList &L,int n){L=new LNode;L->next=NULL;
        for(int i=0;i<n;i++){LinkList p=new LNode;cin>>p->data;p->next=L->next;L->next=p;}}
        int main(){LinkList L;CreateList_H(L,3);LinkList p=L->next;
        while(p!=NULL){cout<<p->data<<" ";p=p->next;}cout<<endl;}''', ['1 2 3'], detail)
    assert e.runtime.output == '3 2 1 \n' and len(prompts) == 1


def test_cin_dialog_pause_retry_and_green_variable(app):
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QInputDialog
    from cvisualizer.window import MainWindow
    window = MainWindow()
    window.load_code(HEADER+'int main(){int x;cin>>x;cout<<x<<endl;}', [])
    window.step()
    seen = []
    def respond(accept):
        dialog = next(w for w in app.topLevelWidgets() if isinstance(w, QInputDialog) and w.isVisible())
        seen.append((dialog.windowTitle(), window.timer.isActive()))
        dialog.setTextValue('42')
        dialog.accept() if accept else dialog.reject()
    QTimer.singleShot(0, lambda: respond(False))
    window.step()
    assert window.controller.state == 'paused'
    assert window.controller.engine.runtime.snapshot()['x']['value'] is None
    QTimer.singleShot(0, lambda: respond(True))
    window.step()
    window.visuals.motion.finish()
    assert window.controller.engine.runtime.snapshot()['x']['value'] == 42
    assert next(box for key, box in window.visuals.boxes.items() if key[0] == 'x').brush().color().name() == '#dcfce7'
    window.step()
    assert window.output.toPlainText() == '42\n'
    assert seen == [('cin 输入', False), ('cin 输入', False)]
    window.stop(); window.close()
