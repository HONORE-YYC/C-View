from PySide6.QtCore import QPointF
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QGraphicsScene

from cvisualizer.animations import MotionLayer


def test_address_markers_are_red_and_move_on_existing_animation_clock(app):
    scene = QGraphicsScene()
    motion = MotionLayer(scene)
    key = ('address', 7)
    destinations = {key: (QPointF(200, 160), 'p', 0, True, '#dc2626', False)}
    motion.start([], destinations, {key: QPointF(80, 160)}, 600)
    item = motion.pointers[key]
    assert motion.busy
    assert any(child.pen().color() == QColor('#dc2626') for child in item.childItems() if hasattr(child, 'pen'))
    motion.animation.setCurrentTime(240)
    assert 80 < item.pos().x() < 200
    motion.pause()
    motion.resume()
    motion.finish()
    assert item.pos() == QPointF(200, 160)
    motion.clear()
    assert not scene.items()


def test_pointer_assignment_transfer_can_be_red_without_changing_value_transfers(app):
    from PySide6.QtCore import QRectF
    scene = QGraphicsScene()
    motion = MotionLayer(scene)
    source, target = QRectF(0, 0, 80, 40), QRectF(100, 100, 80, 40)
    motion.start([(source, target, '#dc2626'), (source, target)], {}, {}, 600)
    assert [arrow.pen().color().name() for arrow in motion.arrows] == ['#dc2626', '#16a34a']
    motion.clear()
