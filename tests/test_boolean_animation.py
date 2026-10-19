from PySide6.QtCore import QAbstractAnimation, QRectF
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QGraphicsScene

from cvisualizer.animations import MotionLayer
from cvisualizer.function_animation import display_value
from cvisualizer.numeric import Char
from cvisualizer.views import display


def spec(*results):
    return {'rect': QRectF(10, 50, 450, 200), 'evaluations': [
        {'expression': 'x > 3', 'value': int(result), 'result': result}
        for result in results]}


def test_character_labels_have_no_numeric_suffix_including_function_inputs():
    assert display(Char(65)) == "'A'"
    assert display(Char(10)) == "'\\n'"
    assert display_value(Char(65)) == "'A'"
    assert display_value([Char(65), Char(66)]) == "['A', 'B']"


def test_step_descriptions_use_character_and_boolean_display_values():
    from cvisualizer.engine import Engine
    engine = Engine("char c='A';bool b=true;c='B';b=false;")
    messages = []
    while engine.peek():
        messages.append(engine.step().message)
    assert messages[0] == "定义 c = 'A'"
    assert messages[1] == '定义 b = true'
    assert messages[2].endswith("→ 'B'")
    assert messages[3].endswith('→ false')


def test_boolean_overlay_gray_then_result_then_removed(app):
    for result, color in [(True, '#86efac'), (False, '#fca5a5')]:
        scene = QGraphicsScene()
        motion = MotionLayer(scene)
        motion.start([], {}, {}, 1000, boolean_summary=spec(result))
        summary = motion.boolean_summary
        assert motion.busy and summary.box.brush().color() == QColor('#e5e7eb')
        motion.animation.setCurrentTime(600)
        assert summary.box.brush().color() == QColor(color)
        assert ('true' if result else 'false') in summary.label.text()
        motion.animation.setCurrentTime(920)
        assert 0 < summary.root.opacity() < 1
        motion.finish()
        assert not scene.items() and motion.boolean_summary is None


def test_boolean_pause_clear_and_no_animation(app):
    scene = QGraphicsScene()
    motion = MotionLayer(scene)
    motion.start([], {}, {}, 1000, boolean_summary=spec(True, False))
    motion.pause()
    assert motion.animation.state() == QAbstractAnimation.State.Paused
    motion.resume()
    motion.animation.setCurrentTime(int(motion.animation.duration() * .7))
    assert motion.boolean_summary.index == 1
    motion.clear()
    assert not scene.items() and not motion.busy
    motion.start([], {}, {}, 1000, animate=False, boolean_summary=spec(True))
    assert not scene.items() and not motion.busy


def test_function_summary_finishes_before_boolean_overlay(app):
    scene = QGraphicsScene()
    motion = MotionLayer(scene)
    calls = {'calls': [{'name': 'positive', 'inputs': [], 'return': 1}],
             'rect': QRectF(10, 50, 450, 200)}
    motion.start([], {}, {}, 1000, call_summary=calls, boolean_summary=spec(True))
    assert motion.summary.root.isVisible()
    assert not motion.boolean_summary.root.isVisible()
    motion.animation.setCurrentTime(int(motion.animation.duration()*.85))
    assert motion.summary.root.opacity() == 0
    assert motion.boolean_summary.root.isVisible()
    motion.finish()
    assert not scene.items()
