from cvisualizer.engine import Engine


def run(code):
    engine = Engine(code)
    while engine.peek():
        engine.step()
    return engine


def test_member_array_loop_and_member_counter_markers():
    engine = run('struct Stack{int data[4];int top;};struct Stack s={{0},1};int i=2;s.data[i]=7;s.data[s.top]=3;')
    markers = engine.index_markers()
    assert any(key[0]=='s.data' and key[2]=='i' and value==2 for key,value in markers.items())
    assert any(key[0]=='s.data' and key[2]=='s.top' and value==1 for key,value in markers.items())


def test_pointer_member_matrix_markers():
    engine = run('struct Grid{int a[2][3];};struct Grid s={{{0}}};struct Grid *p=&s;int i=1;int j=2;p->a[i][j]=7;')
    markers = engine.index_markers()
    assert any(key[0]=='s.a' and key[2]=='i' and value==1 for key,value in markers.items())
    assert any(key[0]=='s.a' and key[2]=='j[列]' and value==(1,2) for key,value in markers.items())
