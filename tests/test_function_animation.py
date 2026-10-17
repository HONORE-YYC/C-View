from PySide6.QtCore import QAbstractAnimation, QRectF
from PySide6.QtGui import QBrush, QColor, QPen
from PySide6.QtWidgets import QGraphicsScene, QGraphicsTextItem

from cvisualizer.animations import MotionLayer, TransferArrow


def summary_scene(rect=None, calls=None):
    scene = QGraphicsScene()
    box = scene.addRect(5, 5, 80, 40, brush=QBrush(QColor('#e0f2fe')))
    label = QGraphicsTextItem('9', box)
    motion = MotionLayer(scene)
    spec = {'calls': calls or [{'name': 'add', 'inputs': [
        {'name': 'a', 'expression': 'x', 'value': 3},
        {'name': 'b', 'expression': 'y + 2', 'value': 6}], 'return': 9}],
        'rect': rect or QRectF(0, 100, 500, 200),
        'effects': [(box, label, '0', '9')]}
    return scene, motion, box, label, spec


def test_summary_flows_before_revealing_purple_effects_and_restores(app):
    scene, motion, box, label, spec = summary_scene()
    base = box.brush().color()
    motion.start([], {}, {}, 1000, call_summary=spec)
    assert motion.busy and motion.summary is not None
    assert label.toPlainText() == '0'
    motion.animation.setCurrentTime(150)
    arrow = motion.summary.arrows[0]
    early = arrow.path().length()
    assert arrow.pen().color() == QColor('#9333ea')
    motion.animation.setCurrentTime(350)
    assert arrow.path().length() > early > 0
    assert label.toPlainText() == '0'
    motion.animation.setCurrentTime(600)
    assert 0 < arrow.opacity() < 1
    motion.animation.setCurrentTime(740)
    assert label.toPlainText() == '9'
    assert box.brush().color() != base
    motion.finish()
    assert box.brush().color() == base
    assert motion.summary is None and not motion.busy
    assert len(scene.items()) == 2


def test_summary_pause_resume_and_clear_restore_effects(app):
    scene, motion, box, label, spec = summary_scene()
    base = box.brush().color()
    motion.start([], {}, {}, 1000, call_summary=spec)
    motion.animation.setCurrentTime(740)
    motion.pause()
    assert motion.animation.state() == QAbstractAnimation.State.Paused
    motion.resume()
    assert motion.animation.state() == QAbstractAnimation.State.Running
    motion.clear()
    assert box.brush().color() == base and label.toPlainText() == '9'
    assert motion.summary is None and len(scene.items()) == 2
    scene.clear()
    motion.clear()


def test_tiny_panel_clips_summary_and_long_inputs_have_tooltips(app):
    rect = QRectF(35, 80, 145, 60)
    scene, motion, box, label, spec = summary_scene(rect=rect, calls=[{
        'name': 'long_function_name', 'inputs': [
            {'name': 'array', 'expression': 'very_long_array_expression', 'value': list(range(100))}
        ], 'return': 9}])
    motion.start([], {}, {}, 1000, call_summary=spec)
    summary = motion.summary
    assert rect.contains(summary.root.sceneBoundingRect())
    assert summary.root.flags() & summary.root.GraphicsItemFlag.ItemClipsChildrenToShape
    assert summary.content.scale() >= .8
    assert any('very_long_array_expression' in item.toolTip() for item in scene.items())
    motion.clear()


def test_multiple_calls_cycle_and_nonanimated_render_has_no_overlay(app):
    calls = [{'name': name, 'inputs': [], 'return': 9} for name in ['one', 'two']]
    scene, motion, box, label, spec = summary_scene(calls=calls)
    motion.start([], {}, {}, 1000, call_summary=spec)
    assert motion.summary.call_index == 0
    motion.animation.setCurrentTime(int(motion.animation.duration()*.45))
    assert motion.summary.call_index == 1
    motion.finish()
    motion.start([], {}, {}, 1000, animate=False, call_summary=spec)
    assert motion.summary is None and not motion.busy
    assert label.toPlainText() == '9'


def test_regular_transfer_stays_green(app):
    arrow = TransferArrow(QRectF(0, 0, 40, 30), QRectF(100, 0, 40, 30))
    assert arrow.pen().color() == QColor('#16a34a')


def test_clear_during_input_flow_reveals_final_values_without_stale_items(app):
    scene, motion, box, label, spec = summary_scene()
    base = box.brush().color()
    motion.start([], {}, {}, 1000, call_summary=spec)
    assert label.toPlainText() == '0'
    motion.clear()
    assert label.toPlainText() == '9' and box.brush().color() == base
    assert len(scene.items()) == 2


def test_large_summary_bounds_call_and_input_diagrams(app):
    calls = [{'name': f'call{index}', 'inputs': [
        {'name': f'arg{param}', 'value': param} for param in range(100)],
        'return': index} for index in range(100)]
    scene, motion, box, label, spec = summary_scene(calls=calls)
    motion.start([], {}, {}, 1000, call_summary=spec)
    assert len(motion.summary.calls) == len(calls)
    assert len(motion.summary.arrows) <= 4
    assert any('arg99' in item.toolTip() for item in scene.items())
    for progress in (.15, .3, .45, .64):
        motion.animation.setCurrentTime(int(motion.animation.duration()*progress))
        assert len(scene.items()) < 40
    assert motion.summary.call_index >= 98
    motion.finish()
    assert len(scene.items()) == 2


def test_summary_duration_allows_each_call_to_be_seen_and_respects_slow_speed(app):
    scene, motion, box, label, spec = summary_scene()
    motion.start([], {}, {}, 200, call_summary=spec)
    one_call_duration = motion.animation.duration()
    assert one_call_duration >= 900
    spec['calls'] *= 3
    motion.start([], {}, {}, 200, call_summary=spec)
    assert motion.animation.duration() >= one_call_duration + 2*650
    motion.start([], {}, {}, 4000, call_summary=spec)
    assert motion.animation.duration() >= 4000
    motion.clear()


def test_input_labels_use_caller_expression_and_void_return_is_named(app):
    scene, motion, box, label, spec = summary_scene()
    spec['calls'][0]['return'] = None
    motion.start([], {}, {}, 1000, call_summary=spec)
    texts = [item.text() for item in scene.items() if hasattr(item, 'text')]
    assert 'x = 3' in texts and 'y + 2 = 6' in texts
    assert '无返回值' in texts
    assert any('x → a = 3' in item.toolTip() for item in scene.items())
    motion.clear()


def test_effect_border_is_purple_and_original_pen_is_restored(app):
    scene, motion, box, label, spec = summary_scene()
    original = QPen(QColor('#f97316'), 3)
    box.setPen(original)
    motion.start([], {}, {}, 1000, call_summary=spec)
    motion.animation.setCurrentTime(int(motion.animation.duration()*.74))
    assert box.pen().color() == QColor('#9333ea')
    motion.clear()
    assert box.pen() == original
