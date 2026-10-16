import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PySide6.QtCore import QAbstractAnimation
from PySide6.QtTest import QTest
from cvisualizer.engine import Engine
from cvisualizer.views import MemoryView
from cvisualizer.window import MainWindow


def render_step(view, engine):
    event = engine.step()
    view.render(engine.runtime.snapshot(), [], event, pointers=engine.index_markers(), duration=600)
    return event


def test_copy_arrow_grows_fades_and_disappears(app):
    e, v = Engine('int a=3; int b; b=a; b=5;'), MemoryView()
    render_step(v, e); render_step(v, e); render_step(v, e)
    assert v.motion.busy
    assert len(v.motion.arrows) == 1
    arrow = v.motion.arrows[0]
    v.motion.animation.setCurrentTime(150)
    early = arrow.path().length()
    v.motion.animation.setCurrentTime(350)
    assert arrow.path().length() > early > 0
    v.motion.animation.setCurrentTime(550)
    assert 0 < arrow.opacity() < 1
    v.motion.finish()
    assert not v.motion.busy and not v.motion.arrows
    render_step(v, e)
    assert not v.motion.busy
    v.close()


def test_pointer_moves_continuously_without_rebuilding_boxes(app):
    e, v = Engine('int a[3]={0}; int i=0; a[i]=1; i=1;'), MemoryView()
    render_step(v, e); render_step(v, e); render_step(v, e)
    key = next(iter(e.index_markers()))
    start = v.motion.pointers[key].pos()
    render_step(v, e)
    marker = v.motion.pointers[key]
    destination = v.motion.destinations[key]
    rect = v.boxes[('a', 1, e.runtime.snapshot()['a']['identity'])]
    v.motion.animation.setCurrentTime(300)
    middle = marker.pos()
    assert middle != start and middle != destination
    assert min(start.x(), destination.x()) <= middle.x() <= max(start.x(), destination.x())
    assert rect.scene() is v.scene()
    v.motion.finish()
    assert marker.pos() == destination
    v.close()


def test_offscreen_source_does_not_get_a_transfer_arrow(app):
    e, v = Engine('int a[70]={0}; int x=a[69];'), MemoryView()
    render_step(v, e); render_step(v, e)
    assert v.motion.arrows == []
    v.close()


def test_pause_resume_stop_reset_and_tick_wait_for_animation(app):
    w = MainWindow()
    w.load_code('int a=3; int b; b=a; b=2;', [])
    w.step(); w.step(); w.step()
    assert w.visuals.motion.busy
    w.pause()
    assert w.visuals.motion.animation.state() == QAbstractAnimation.State.Paused
    w.play()
    assert w.visuals.motion.animation.state() == QAbstractAnimation.State.Running
    before = w.controller.engine.count
    w.on_tick()
    assert w.controller.engine.count == before
    w.stop()
    assert not w.visuals.motion.busy
    assert w.controller.engine.runtime.snapshot()['b']['value'] == 3
    w.reset()
    assert not w.visuals.motion.pointers and not w.visuals.motion.arrows
    w.close()


def test_refresh_does_not_restart_or_remove_running_animation(app):
    w = MainWindow()
    w.load_code('int a=3; int b; b=a;', [])
    w.step(); w.step(); w.step()
    motion = w.visuals.motion
    motion.animation.setCurrentTime(200)
    arrow = motion.arrows[0]
    w.refresh()
    assert motion.arrows[0] is arrow
    assert motion.animation.currentTime() == 200
    motion.finish()
    w.close()


def test_animation_finishes_in_event_loop_and_reenables_step(app):
    w = MainWindow()
    w.load_code('int a=3; int b; b=a; b=2;', [])
    w.speed.setValue(100)
    w.step(); w.step(); w.step()
    assert not w.buttons['step'].isEnabled()
    QTest.qWait(450)
    assert not w.visuals.motion.busy
    assert w.buttons['step'].isEnabled()
    w.step()
    assert w.controller.engine.runtime.snapshot()['b']['value'] == 2
    w.close()


def test_seek_skips_intermediate_animations(app):
    w = MainWindow()
    w.load_code('int a[3]={0}; int i=0;\nfor(i=0;i<3;i++){a[i]=i;}\nint x=a[2];', [])
    w.ensure_controller()
    index = next(i for i in range(w.targets.count()) if w.targets.itemData(i).line == 3)
    w.targets.setCurrentIndex(index)
    w.seek()
    for _ in range(100):
        w.on_tick()
        if w.controller.state != 'seeking':
            break
    assert w.controller.state == 'paused'
    assert not w.visuals.motion.busy
    assert w.controller.engine.runtime.snapshot()['a']['value'] == [0, 1, 2]
    w.step()
    assert w.visuals.motion.busy
    w.stop(); w.close()


def test_out_of_range_pointer_is_labelled_and_resize_cleans_animation(app):
    e, v = Engine('int a[2]={0}; int i=0; a[i]=1; i=2;'), MemoryView()
    render_step(v, e); render_step(v, e); render_step(v, e); render_step(v, e)
    pointer = next(iter(v.motion.pointers.values()))
    assert any('越界' in item.text() for item in pointer.childItems() if hasattr(item, 'text'))
    v.resize(900, 700)
    v.show()
    app.processEvents()
    assert not v.motion.busy
    assert len(v.motion.pointers) == 1
    v.close()


def test_final_step_animation_can_pause_and_resume_without_restarting(app):
    w = MainWindow()
    w.load_code('int a=3; int b; b=a;', [])
    w.step(); w.step(); w.step()
    w.pause()
    assert w.controller.state == 'finished'
    assert w.buttons['play'].isEnabled()
    w.play()
    assert w.controller.engine.count == 3
    assert w.visuals.motion.animation.state() == QAbstractAnimation.State.Running
    w.stop(); w.close()


def test_resize_after_single_step_keeps_step_button_usable(app):
    w = MainWindow()
    w.show()
    w.load_code('int a=3; int b; b=a; b=2;', [])
    w.step(); w.step(); w.step()
    assert not w.buttons['step'].isEnabled()
    w.resize(w.width()+100, w.height()+100)
    app.processEvents()
    assert not w.visuals.motion.busy
    assert w.buttons['step'].isEnabled()
    w.stop(); w.close()
