from cvisualizer.structures import Binding, describe


def test_queue_wraparound_logical_order_and_markers():
    variables = {'q': {'value': [50, 20, 30, 40]}, 'f': {'value': 2}, 'r': {'value': 1}}
    model = describe(Binding('q', 'queue', front='f', rear='r'), variables)
    assert model.active == [2, 3, 0]
    assert model.logical == [30, 40, 50]
    assert model.markers == {2: ['front'], 1: ['rear']}
    assert model.error == ''


def test_stack_empty_and_list_length():
    variables = {'a': {'value': [1, 2, None]}, 'n': {'value': 2}, 't': {'value': -1}}
    assert describe(Binding('a', 'list', length='n'), variables).active == [0, 1]
    assert describe(Binding('a', 'stack', top='t'), variables).active == []


def test_invalid_binding_keeps_raw_array_visible():
    variables = {'a': {'value': [1, 2]}, 'top': {'value': 2}}
    model = describe(Binding('a', 'stack', top='top'), variables)
    assert model.error
    assert model.values == [1, 2]


def test_binding_to_uninitialized_or_missing_variable_is_explicit():
    model = describe(Binding('a', 'list', length='n'), {'a': {'value': [None]}})
    assert 'n' in model.error
