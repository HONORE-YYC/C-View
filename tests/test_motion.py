from cvisualizer.engine import Engine


def execute(source):
    e = Engine(source)
    events = []
    while e.peek():
        events.append(e.step())
    return e, events


def endpoints(event):
    return [(source[:2], target[:2]) for source, target in event.transfers]


def test_scalar_copy_and_literal_assignment():
    _, events = execute('int a=3; int b; b=a; b=5;')
    assert endpoints(events[2]) == [(('a', None), ('b', None))]
    assert endpoints(events[3]) == []


def test_array_copy_excludes_index_reads_from_value_sources():
    _, events = execute('int a[2]={1,2}; int b[2]; int i=0; int j=1; b[i]=a[j];')
    assert endpoints(events[-1]) == [(('a', 1), ('b', 0))]


def test_expression_sources_nested_assignment_and_initializer():
    _, events = execute('int a=2; int b=3; int c=a+b; a=b=c;')
    assert endpoints(events[2]) == [(('a', None), ('c', None)), (('b', None), ('c', None))]
    assert endpoints(events[3]) == [(('c', None), ('b', None)), (('b', None), ('a', None))]


def test_loop_pointer_exists_before_first_access_and_moves():
    e = Engine('int a[2]; for(int i=0;i<2;i++){a[i]=i;}')
    e.step()
    e.step()
    assert list(e.index_markers().values()) == [0]
    while e.peek() and e.peek().location.kind != 'update':
        e.step()
    e.step()
    assert list(e.index_markers().values()) == [1]
    while e.peek():
        e.step()
    assert e.index_markers() == {}


def test_shadowed_index_is_not_mistaken_for_bound_loop_variable():
    e = Engine('int a[2]; int i=0; a[i]=1; {int i=1; i++;} i++;')
    e.step(); e.step(); e.step(); e.step()
    assert e.index_markers() == {}
    e.step(); e.step()
    assert list(e.index_markers().values()) == [1]


def test_two_indices_same_array_and_outside_bounds_are_preserved():
    e, _ = execute('int a[2]={0}; int i=0; int j=1; a[i]=a[j]; i=2; j=-1;')
    assert sorted(e.index_markers().values()) == [-1, 2]


def test_compound_assignment_has_only_external_source_arrow():
    _, events = execute('int a=1; int b=2; a+=b; a++;')
    assert endpoints(events[2]) == [(('b', None), ('a', None))]
    assert endpoints(events[3]) == []


def test_comma_expression_only_copies_its_last_result():
    _, events = execute('int a=1; int b=2; int x; x=(a,5); x=(a,b);')
    assert endpoints(events[3]) == []
    assert endpoints(events[4]) == [(('b', None), ('x', None))]
