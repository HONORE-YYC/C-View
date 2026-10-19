import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from types import SimpleNamespace
from cvisualizer.arrays import Matrix
from cvisualizer.views import MemoryView


def render_matrix(app, columns=3, active=False, transfer=False):
    matrix = Matrix(2, columns)
    matrix[0, 1] = 7
    variables = {'a': {'value': matrix, 'identity': 1, 'type': 'int', 'declaration': ('a', 1, 1)}}
    event = SimpleNamespace(variables=variables, reads=[('a', (0, 1))] if active else [],
        writes=[('a', (1, 0))] if active else [], transfers=[], calls=[], expanded=False,
        booleans=[], before={}, function='', text='a[1][0] = a[0][1];')
    view = MemoryView()
    view.resize(900, 600)
    if transfer:
        view.render(variables, [], None, animate=False)
        event.transfers = [(('a', (0, 1), 1), ('a', (1, 0), 1))]
    view.render(variables, [], event)
    return view


def test_matrix_front_headers_and_exact_small_rear_count(app):
    view = render_matrix(app)
    assert ('a', 0, 1) in view.boxes
    assert view.boxes['a', 0, 1].value_label.toPlainText() == 'a[0]'
    assert len(view.matrix_stacks['a', 0, 1]) == 3
    assert view.boxes['a', 0, 1].brush().color().name() == '#dcfce7'
    assert view.boxes['a', 1, 1].brush().color().name() == '#e5e7eb'
    view.close()


def test_matrix_copy_arrows_connect_exposed_elements(app):
    view = render_matrix(app, active=True, transfer=True)
    assert len(view.motion.arrows) == 1
    arrow = view.motion.arrows[0]
    view.motion.frame(.1)
    assert arrow.opacity() == 0
    view.motion.frame(.4)
    assert arrow.opacity() > 0
    assert arrow.route.pointAtPercent(0).y() > view.boxes['a', 0, 1].rect().bottom()
    view.close()


def test_matrix_resize_clears_reveals_without_destroyed_item_access(app):
    view = render_matrix(app, active=True)
    view.motion.frame(.4)
    view.render(*view._data, animate=False, force=True)
    assert not view.motion.busy
    assert not view.motion.matrix_reveals
    view.motion.clear()
    view.close()


def test_matrix_large_second_dimension_is_bounded(app):
    view = render_matrix(app, 100000)
    assert len(view.matrix_stacks['a', 0, 1]) == 3
    assert len(view.scene().items()) < 150
    assert any('100000' in item.toPlainText() for item in view.scene().items() if hasattr(item, 'toPlainText'))
    view.close()


def test_matrix_distinct_read_write_reveal_and_return_on_shared_clock(app):
    view = render_matrix(app, active=True)
    source = view.boxes['a', (0, 1), 1]
    target = view.boxes['a', (1, 0), 1]
    closed = source.pos()
    view.motion.frame(.4)
    assert source.pos() != closed
    assert source.value_label.isVisible()
    assert '7' in source.value_label.toPlainText()
    assert target.pos() != target.matrix_origin
    view.motion.pause()
    assert view.motion.busy
    view.motion.finish()
    assert source.pos() == closed
    view.close()


def test_initializer_does_not_extract_element_cards(app):
    view = render_matrix(app, 100000)
    variables, bindings, event, *_ = view._data
    event.writes = [('a', None)] + [('a', (0, col)) for col in range(10000)]
    event.transfers = [(('a', (0, col), 1), ('a', (1, col), 1)) for col in range(10000)]
    view.render(variables, bindings, event, force=True)
    assert not view.matrix_reveals
    assert len(view.scene().items()) < 150
    view.close()


def test_many_accesses_extract_at_most_four_per_row_with_count(app):
    view = render_matrix(app, 100000)
    variables, bindings, event, *_ = view._data
    event.reads = [('a', (0, col)) for col in range(10000)]
    view.render(variables, bindings, event, force=True)
    assert len(view.matrix_reveals) == 4
    assert any('9996' in item.toPlainText() for item in view.scene().items() if hasattr(item, 'toPlainText'))
    assert len(view.scene().items()) < 180
    view.close()


def test_row_positions_stay_stable_across_access_counts(app):
    view = render_matrix(app)
    initial = view.boxes['a', 1, 1].scenePos()
    variables, bindings, event, *_ = view._data
    event.reads = [('a', (0, col)) for col in range(3)]
    view.render(variables, bindings, event, force=True)
    assert view.boxes['a', 1, 1].scenePos() == initial
    view.close()


def test_rear_cards_sample_initialized_and_empty_values(app):
    view = render_matrix(app)
    colors = {item.brush().color().name() for item in view.matrix_stacks['a', 0, 1]}
    assert colors == {'#dcfce7', '#e5e7eb'}
    assert all(not item.value_label.isVisible() for item in view.matrix_stacks['a', 0, 1])
    view.close()


def test_index_marker_tracks_extracted_element(app):
    view = render_matrix(app, active=True)
    variables, bindings, event, *_ = view._data
    event = SimpleNamespace(**vars(event))
    key = ('a', 1, 'i', 0)
    view.render(variables, bindings, event, pointers={key: (0, 1)}, force=True)
    view.motion.frame(.4)
    box = view.boxes['a', (0, 1), 1]
    marker = view.motion.pointers[key]
    assert marker.scenePos().y() == box.mapRectToScene(box.rect()).top()-4
    view.motion.frame(1.)
    assert marker.scenePos().y() == box.mapRectToScene(box.rect()).top()-4
    view.close()


def test_scalar_matrix_pointer_protects_row_from_folding(app):
    from cvisualizer.pointers import Pointer
    from cvisualizer.structures import Structure
    from cvisualizer.array_folding import Fold
    matrix = Matrix(40, 100)
    cell = {'value': matrix, 'identity': 1}
    variables = {'a': cell, 'p': {'value': Pointer(1, 70, 'int', 'a', row=20), 'identity': 2}}
    view = MemoryView()
    model = Structure('a', 'array', matrix)
    layout = view.array_layout('a', cell, variables, model, None)
    assert any(isinstance(layout[pos], int) and layout[pos] == 20 for pos in range(len(layout)))
    view.close()


def test_red_marker_tracks_extracted_matrix_element(app):
    from cvisualizer.pointers import Pointer
    view = render_matrix(app, active=True)
    variables, bindings, event, *_ = view._data
    variables = dict(variables, p={'value': Pointer(1, 1, 'int', 'a', row=0), 'identity': 2, 'type': 'int *'})
    event = SimpleNamespace(**vars(event))
    event.variables = variables
    view.render(variables, bindings, event, force=True)
    view.motion.frame(.4)
    box = view.boxes['a', (0, 1), 1]
    assert box.pos() != box.matrix_origin
    assert view.motion.pointers['address', 2].scenePos().y() == box.mapRectToScene(box.rect()).top()-4
    view.close()


def test_quick_call_drawers_hold_after_summary_disappears(app):
    view = render_matrix(app, active=True)
    variables, bindings, event, *_ = view._data
    event = SimpleNamespace(**vars(event))
    event.calls = [{'name': 'f', 'inputs': [], 'return': 7}]
    view.render(variables, bindings, event, force=True)
    view.motion.frame(.8)
    assert view.motion.summary.root.opacity() == 0
    assert all(item.value_label.isVisible() for item in view.matrix_reveals)
    assert all(item.pos() == item.matrix_origin+item.matrix_delta for item in view.matrix_reveals)
    view.close()


def test_theme_toggle_preserves_live_function_result_pulse(app):
    view = render_matrix(app, active=True)
    variables, bindings, event, *_ = view._data
    event = SimpleNamespace(**vars(event))
    event.calls = [{'name': 'f', 'inputs': [], 'return': 7}]
    view.render(variables, bindings, event, force=True)
    view.motion.pause()
    view.motion.frame(.8)
    box = view.boxes['a', (1, 0), 1]
    color = box.brush().color()
    assert color.name() == '#e9d5ff'
    for dark in (False, True, False):
        view.set_dark_mode(dark)
        assert box.brush().color() == color
    view.close()


def test_change_caption_uses_nested_matrix_indices(app):
    view = render_matrix(app, active=True)
    assert any('a[1][0]' in item.toPlainText() for item in view.scene().items() if hasattr(item, 'toPlainText'))
    assert not any('a[(1, 0)]' in item.toPlainText() for item in view.scene().items() if hasattr(item, 'toPlainText'))
    view.close()


def test_matrix_spacing_is_fixed_by_column_count(app):
    view = render_matrix(app, columns=3)
    variables, bindings, event, *_ = view._data
    variables['a']['value'] = Matrix(8, 3)
    view.render(variables, bindings, event, force=True)
    tops = sorted({box.mapRectToScene(box.rect()).top() for key, box in view.boxes.items()
                   if key[0] == 'a' and isinstance(key[1], int)})
    assert len(tops) > 1
    assert tops[1]-tops[0] == 280
    view.close()


def test_every_folded_matrix_card_keeps_ellipsis_after_theme_toggle(app):
    from cvisualizer.array_folding import Fold
    view = render_matrix(app, columns=8)
    variables, bindings, event, *_ = view._data
    matrix = Matrix(1000000000, 8, 0)
    matrix[12, 7] = 3
    variables['a']['value'] = matrix
    event.reads = []
    event.writes = [('a', (12, 7))]
    view.render(variables, bindings, event, force=True)
    for dark in (False, True, False):
        view.set_dark_mode(dark)
        labels = [item for item in view.scene().items()
                  if hasattr(item, 'toPlainText') and item.toPlainText() == '...']
        assert len(labels) == 2
        assert all(label.isVisible() and label.opacity() == 1 for label in labels)
    view.close()


def test_many_reads_keep_high_column_write_result_exposed(app):
    view = render_matrix(app, columns=8)
    variables, bindings, event, *_ = view._data
    event.reads = [('a', (0, col)) for col in range(5)]
    event.writes = [('a', (0, 7))]
    view.render(variables, bindings, event, force=True)
    assert ('a', (0, 7), 1) in view.boxes
    assert len(view.matrix_reveals) == 4
    assert any('2' in item.toPlainText() and '4' in item.toolTip()
               for item in view.scene().items() if hasattr(item, 'toPlainText'))
    view.close()
