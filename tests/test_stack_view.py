from types import SimpleNamespace
from PySide6.QtCore import QPointF
from cvisualizer.pointers import Pointer
from cvisualizer.views import MemoryView


def snapshot(count, popped=None, root=1, name='s'):
    storage = root*100
    return {
        name: dict(value=object(), type='Stack', identity=root, is_struct=True,
                   stack_node=dict(base='bottom', top='cursor', capacity='limit'), stack_popped=popped),
        name+'.bottom': dict(value=Pointer(storage, 0, 'int', 'buffer'), type='int*', identity=storage+1),
        name+'.cursor': dict(value=Pointer(storage, count, 'int', 'buffer'), type='int*', identity=storage+2),
        name+'.limit': dict(value=40, type='int', identity=storage+3),
        'buffer'+str(root): dict(value=list(range(40)), type='int[40]', identity=storage),
    }


def event(before, after, calls=()):
    return SimpleNamespace(before=before, variables=after, function='', text='advance(s)',
                           writes=[], reads=[], calls=list(calls), transfers=[], expanded=False)


def make_view(app, width=700, height=460):
    view = MemoryView(); view.resize(width, height); view.show(); app.processEvents()
    return view


def test_stack_adjacent_single_row_fold_and_storage_suppression(app):
    view = make_view(app, 340)
    cells = snapshot(25, dict(value=25, index=25, serial=1))
    view.render(cells, [], animate=False)
    row = view.stack_layer.rows[1]
    assert list(row.cells) == [24, 23, 22, 21, 20, 'fold', 3, 2, 1, 0]
    assert row.fold_count == 16
    rects = [card.mapRectToScene(card.rect()) for card in row.cells.values()]
    assert len({rect.top() for rect in rects}) == 1
    assert all(abs(a.right()-b.left()) < .01 for a, b in zip(rects, rects[1:]))
    assert all(rect.height() > rect.width() for rect in rects)
    clip = view._sections['array'][0].rect()
    assert all(clip.contains(rect) for rect in rects)
    assert clip.contains(row.ghost.mapRectToScene(row.ghost.rect()))
    assert row.cells[24].value_label.toPlainText() == '24'
    assert row.top_marker.toolTip() == 's.cursor'
    assert row.base_marker.toolTip() == 's.bottom'
    assert not any(key[0] in ('s.bottom', 's.cursor') for key in view.boxes)
    assert len([key for key in view.boxes if key[0] == 'buffer1']) == 10
    assert ('address', 101) not in view.motion.pointers
    assert ('address', 102) not in view.motion.pointers
    assert row.cells[0].pen().color().name() == '#dc2626'
    assert row.bracket.pen().color().name() == '#2563eb'
    view.close()


def test_push_pop_shared_clock_fixed_bottom_and_persistent_last_pop(app):
    view = make_view(app)
    before = snapshot(4)
    after = snapshot(3, dict(value=3, index=3, serial=1))
    view.render(before, [], animate=False)
    bottom = view.stack_layer.rows[1].cells[0].pos()
    view.render(after, [], event(before, after), duration=10000)
    view.motion.pause(); view.motion.frame(0)
    row = view.stack_layer.rows[1]
    start = QPointF(row.ghost.pos())
    view.motion.frame(.5)
    middle = QPointF(row.ghost.pos())
    view.motion.finish()
    assert start.x() > middle.x() > row.ghost.x()
    assert row.cells[0].pos() == bottom
    pushed = snapshot(4, after['s']['stack_popped'])
    view.render(pushed, [], event(after, pushed), duration=10000)
    view.motion.pause(); view.motion.frame(0)
    row = view.stack_layer.rows[1]
    start = QPointF(row.cells[3].pos())
    assert row.ghost.value_label.toPlainText() == '3'
    view.motion.frame(.5)
    assert row.cells[3].x() > start.x()
    view.motion.finish()
    assert row.ghost.isVisible()
    assert row.cells[0].pos() == bottom
    view.render({}, [], animate=False)
    assert not view.stack_layer.rows and not view.motion.busy
    view.close()


def test_stack_quick_call_phase_dark_theme_and_multi_stack_scroll(app):
    view = make_view(app, 500, 300)
    before, after = snapshot(2), snapshot(3)
    view.render(before, [], animate=False)
    step = event(before, after, [dict(name='append', inputs=[], **{'return': None})])
    view.render(after, [], step, duration=10000)
    view.motion.pause(); view.motion.frame(.4)
    card = view.stack_layer.rows[1].cells[2]
    start = QPointF(card.pos())
    view.motion.frame(.84)
    assert card.pos() != start
    view.motion.finish(); view.set_dark_mode(True)
    assert card.pen().color().name() == '#dc2626'
    assert card.value_label.defaultTextColor().name() == '#991b1b'
    cells = {}
    for root in range(1, 31):
        cells.update(snapshot(12, root=root, name='s'+str(root)))
    view.render(cells, [], animate=False)
    assert view.array_scroll.maximum() > 0
    assert len(view.stack_layer.rows) < 10
    view.array_scroll.setValue(view.array_scroll.maximum()); app.processEvents()
    assert 30 in view.stack_layer.rows
    assert len(view.scene().items()) < 500
    view.close()


def test_push_path_does_not_cover_retained_popped_value(app):
    view = make_view(app)
    before = snapshot(3, dict(value=99, index=3, serial=1))
    after = snapshot(4, before['s']['stack_popped'])
    view.render(before, [], animate=False)
    view.render(after, [], event(before, after), duration=10000)
    view.motion.pause()
    row = view.stack_layer.rows[1]
    for frame in (.25, .5, .75):
        view.motion.frame(frame)
        card = row.cells[3].mapRectToScene(row.cells[3].rect())
        retained = row.ghost.mapRectToScene(row.ghost.rect())
        assert row.cells[3].opacity() == 0 or not card.intersects(retained)
    view.close()
