from cvisualizer.pointers import Pointer
from cvisualizer.stack_state import models


def snapshot(count=3, capacity=12, first=0):
    return {
        's': dict(type='struct S', identity=1, value=object(), is_struct=True,
                  stack_node=dict(base='bottom', top='cursor', capacity='limit')),
        's.bottom': dict(type='int*', identity=2, value=Pointer(5, first, 'int', 'store')),
        's.cursor': dict(type='int*', identity=3, value=Pointer(5, first+count, 'int', 'store')),
        's.limit': dict(type='int', identity=4, value=capacity),
        'store': dict(type='int', identity=5, value=list(range(20))),
    }


def test_stack_model_resolves_custom_names_and_offset_storage():
    model = models(snapshot(first=2))[1]
    assert model['valid'] and model['count'] == 3
    assert model['base'] == 2 and model['top'] == 5
    assert model['base_name'] == 's.bottom' and model['top_name'] == 's.cursor'
    assert model['storage_name'] == 'store'


def test_stack_model_rejects_different_storage_and_bad_range():
    cells = snapshot()
    cells['s.cursor']['value'] = Pointer(99, 2, 'int', 'elsewhere')
    assert not models(cells)[1]['valid']
    assert not models(snapshot(capacity=21))[1]['valid']
    assert not models(snapshot(count=-1))[1]['valid']
    assert models(snapshot(count=0))[1]['valid']


def test_stack_model_copies_retained_pop_value():
    cells = snapshot()
    cells['s']['stack_popped'] = dict(value=17, index=3, serial=2)
    model = models(cells)[1]
    assert model['popped']['value'] == 17
    model['popped']['value'] = 99
    assert cells['s']['stack_popped']['value'] == 17


def test_changing_storage_does_not_show_old_popped_element():
    cells = snapshot()
    cells['s']['stack_popped'] = dict(value=17, index=3, serial=2, storage_identity=888)
    assert models(cells)[1]['popped'] is None


def test_allocated_storage_is_claimed_before_top_is_initialized():
    cells = snapshot()
    cells['s.cursor']['value'] = None
    cells['s.limit']['value'] = None
    model = models(cells)[1]
    assert not model['valid']
    assert model['storage_identity'] == 5
