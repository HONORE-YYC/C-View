from PySide6.QtGui import QColor

from cvisualizer.engine import Engine
from cvisualizer.views import MemoryView


def step(view, engine):
    event = engine.step()
    view.render(engine.display_snapshot(), [], event, pointers=engine.index_markers(),
                index_lanes=engine.index_lanes)
    return event


def test_red_pointer_moves_with_array_and_coexists_with_blue_index(app):
    engine = Engine('int a[4]={1,2,3,4};int i=0;int *p=a;a[i]=*p;p++;')
    view = MemoryView()
    view.resize(700, 700)
    view.show()
    app.processEvents()
    for _ in range(4):
        step(view, engine)
        view.motion.finish()
    red_key = ('address', engine.runtime.snapshot()['p']['identity'])
    assert len(view.motion.pointers) == 2
    red = view.motion.pointers[red_key]
    assert any(child.pen().color() == QColor('#dc2626') for child in red.childItems() if hasattr(child, 'pen'))
    blue = next(item for key, item in view.motion.pointers.items() if key != red_key)
    assert any(child.pen().color() == QColor('#2563eb') for child in blue.childItems() if hasattr(child, 'pen'))
    old = red.pos()
    step(view, engine)
    view.motion.animation.setCurrentTime(200)
    assert old != view.motion.pointers[red_key].pos() != view.motion.destinations[red_key]
    view.motion.finish()
    target = next(box for (name, index, _), box in view.boxes.items() if name == 'a' and index == 1)
    assert view.motion.pointers[red_key].pos().y() == target.mapRectToScene(target.rect()).top()-4
    view.close()


def test_scalar_pointer_scroll_does_not_follow_array_scroll_and_hides_offscreen(app):
    engine = Engine('int a[40]={0};' + ''.join(f'int x{i}={i};' for i in range(20)) + 'int *p=&x19;')
    while engine.peek():
        engine.step()
    view = MemoryView()
    view.resize(600, 600)
    view.show()
    app.processEvents()
    view.render(engine.runtime.snapshot(), [], engine.last, index_lanes=engine.index_lanes, animate=False)
    key = ('address', engine.runtime.snapshot()['p']['identity'])
    marker = view.motion.pointers[key]
    assert not marker.isVisible()
    view.scalar_scroll.setValue(view.scalar_scroll.maximum())
    assert marker.isVisible()
    pos = marker.pos()
    view.array_scroll.setValue(100)
    assert marker.pos() == pos
    view.close()


def test_null_and_one_past_have_no_arrow_pointing_at_real_element(app):
    engine = Engine('int a[2]={0};int *p=a;int *q=0;p+=2;p=0;')
    view = MemoryView()
    for _ in range(4):
        step(view, engine)
        view.motion.finish()
    assert len(view.motion.pointers) == 1
    item = next(iter(view.motion.pointers.values()))
    assert '尾后' in item.toolTip()
    step(view, engine)
    assert not view.motion.pointers
    view.close()


def test_pointer_declarations_do_not_shift_arrays(app):
    engine = Engine('int a[3]={0};int i=0;int *p=a;int *q=&a[1];a[i]=*q;')
    view = MemoryView()
    positions = []
    while engine.peek():
        step(view, engine)
        view.motion.finish()
        box = next(box for (name, index, _), box in view.boxes.items() if name == 'a' and index == 0)
        positions.append(box.mapRectToScene(box.rect()).top())
    assert len(set(positions)) == 1
    view.close()


def test_pointer_subscript_label_shows_counter_value_not_absolute_offset(app):
    engine = Engine('int a[4]={0};int *p=a+1;int i=0;p[i]=3;')
    view = MemoryView()
    while engine.peek():
        step(view, engine)
        view.motion.finish()
    blue = next(item for key, item in view.motion.pointers.items() if key[0] != 'address')
    assert blue.toolTip() == 'i = 0'
    target = next(box for (name, index, _), box in view.boxes.items() if name == 'a' and index == 1)
    rect = target.mapRectToScene(target.rect())
    assert rect.left() <= blue.pos().x() <= rect.right()
    assert blue.pos().y() == rect.top()-4
    view.close()
