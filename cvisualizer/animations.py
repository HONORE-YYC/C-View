"""Time-based scene overlays. A frame changes only small overlay items."""
import math

from PySide6.QtCore import QObject, QPointF, QVariantAnimation, QAbstractAnimation, Signal, Qt
from PySide6.QtGui import QColor, QPen, QBrush, QPainterPath, QPolygonF, QFont
from PySide6.QtWidgets import QGraphicsPathItem, QGraphicsPolygonItem, QGraphicsItemGroup, QGraphicsSimpleTextItem


def smooth(value):
    value = max(0., min(1., value))
    return value * value * (3 - 2 * value)


class TransferArrow(QGraphicsPathItem):
    def __init__(self, source, target, color='#16a34a'):
        super().__init__()
        color = QColor(color)
        self.setPen(QPen(color, 3, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
        self.head = QGraphicsPolygonItem(self)
        self.head.setPen(QPen(Qt.PenStyle.NoPen))
        self.head.setBrush(QBrush(color))
        self.setZValue(20)
        if abs(source.center().y() - target.center().y()) < 15:
            start, end = source.topLeft() + QPointF(source.width()/2, -2), target.topLeft() + QPointF(target.width()/2, -2)
            lift = min(75, max(36, abs(end.x()-start.x())*.18))
            c1, c2 = start + QPointF(0, -lift), end + QPointF(0, -lift)
        elif source.right() < target.left() or target.right() < source.left():
            direction = 1 if target.center().x() > source.center().x() else -1
            start = QPointF(source.right()+2 if direction > 0 else source.left()-2, source.center().y())
            end = QPointF(target.left()-2 if direction > 0 else target.right()+2, target.center().y())
            bend = abs(end.x()-start.x())*.45
            c1, c2 = start + QPointF(direction*bend, 0), end - QPointF(direction*bend, 0)
        else:
            direction = 1 if target.center().y() > source.center().y() else -1
            start = QPointF(source.center().x(), source.bottom()+2 if direction > 0 else source.top()-2)
            end = QPointF(target.center().x(), target.top()-2 if direction > 0 else target.bottom()+2)
            bend = abs(end.y()-start.y())*.45
            c1, c2 = start + QPointF(0, direction*bend), end - QPointF(0, direction*bend)
        self.route = QPainterPath(start)
        self.route.cubicTo(c1, c2, end)
        self.frame(0)

    def frame(self, progress):
        growth = smooth(progress / .68)
        path = QPainterPath(self.route.pointAtPercent(0))
        for step in range(1, 41):
            path.lineTo(self.route.pointAtPercent(growth * step/40))
        self.setPath(path)
        tip = self.route.pointAtPercent(growth)
        previous = self.route.pointAtPercent(max(0, growth-.015))
        angle = math.atan2(tip.y()-previous.y(), tip.x()-previous.x())
        backward = QPointF(math.cos(angle)*11, math.sin(angle)*11)
        side = QPointF(-math.sin(angle)*5, math.cos(angle)*5)
        self.head.setPolygon(QPolygonF([tip, tip-backward+side, tip-backward-side]))
        fade = 1-smooth((progress-.76)/.24)
        self.setOpacity(min(1, progress*12)*fade)


class IndexPointer(QGraphicsItemGroup):
    def __init__(self, label, lane=0, valid=True, color=None, sideways=False):
        super().__init__()
        self.setZValue(10+lane)
        color = QColor(color or ('#2563eb' if valid else '#b45309'))
        height = 16+lane*17
        path = QPainterPath(QPointF(-24, 0) if sideways else QPointF(0, -height))
        if valid:
            path.lineTo(-5, 0) if sideways else path.lineTo(0, -5)
        stem = QGraphicsPathItem(path)
        stem.setPen(QPen(color, 2))
        self.addToGroup(stem)
        if valid:
            points = [QPointF(0, 0), QPointF(-7, -4), QPointF(-7, 4)] if sideways else [QPointF(0, 0), QPointF(-4, -7), QPointF(4, -7)]
            head = QGraphicsPolygonItem(QPolygonF(points))
            head.setPen(QPen(Qt.PenStyle.NoPen))
            head.setBrush(QBrush(color))
            self.addToGroup(head)
        text = QGraphicsSimpleTextItem(label)
        text.setFont(QFont('Microsoft YaHei UI', 9, QFont.Weight.Bold))
        text.setBrush(QBrush(color))
        text.setPos(-text.boundingRect().width()-28, -text.boundingRect().height()/2) if sideways else text.setPos(6, -height-9)
        # A white backing keeps labels readable while passing over other cells.
        from PySide6.QtWidgets import QGraphicsRectItem
        background = QGraphicsRectItem(text.boundingRect().adjusted(-2, -1, 2, 1))
        background.setPen(QPen(Qt.PenStyle.NoPen))
        background.setBrush(QBrush(QColor(255, 255, 255, 225)))
        background.setPos(text.pos())
        self.addToGroup(background)
        self.addToGroup(text)
        self.setToolTip(label)


class MotionLayer(QObject):
    settled = Signal()

    def __init__(self, scene, parent=None):
        super().__init__(parent)
        self.scene = scene
        self.arrows, self.pointers, self.destinations = [], {}, {}
        self.origins = {}
        self.summary = None
        self.animation = QVariantAnimation(self)
        self.animation.setStartValue(0.)
        self.animation.setEndValue(1.)
        self.animation.valueChanged.connect(self.frame)
        self.animation.finished.connect(self._complete)

    @property
    def busy(self):
        return self.animation.state() != QAbstractAnimation.State.Stopped

    def clear(self):
        self.animation.stop()
        if self.summary is not None:
            self.summary.close()
            self.summary = None
        for item in self.arrows + list(self.pointers.values()):
            if item.scene() is self.scene:
                self.scene.removeItem(item)
        self.arrows, self.pointers, self.destinations, self.origins = [], {}, {}, {}

    def start(self, transfers, pointers, previous, duration, animate=True, call_summary=None):
        self.clear()
        moving = False
        for key, spec in pointers.items():
            point, label, lane, valid, *style = spec
            item = IndexPointer(label, lane, valid, *style)
            self.scene.addItem(item)
            self.pointers[key], self.destinations[key] = item, point
            origin = previous.get(key, point) if animate else point
            self.origins[key] = origin
            item.setPos(origin)
            moving |= origin != point
        if animate:
            for transfer in transfers:
                arrow = TransferArrow(*transfer)
                self.scene.addItem(arrow)
                self.arrows.append(arrow)
            if call_summary and call_summary.get('calls'):
                from .function_animation import FunctionSummary
                self.summary = FunctionSummary(self.scene, call_summary)
                duration = max(duration, 900, 650*len(self.summary.calls)+400)
        if self.arrows or moving or self.summary is not None:
            self.animation.setDuration(max(1, int(duration)))
            self.animation.start()

    def frame(self, progress):
        t = smooth(progress / .8)
        for key, item in self.pointers.items():
            start, end = self.origins[key], self.destinations[key]
            item.setPos(start + (end-start)*t)
        for arrow in self.arrows:
            arrow.frame(progress)
        if self.summary is not None:
            self.summary.frame(progress)

    def _complete(self):
        self.frame(1.)
        for arrow in self.arrows:
            self.scene.removeItem(arrow)
        self.arrows = []
        if self.summary is not None:
            self.summary.close()
            self.summary = None
        self.settled.emit()

    def finish(self):
        if self.busy:
            self.animation.stop()
            self._complete()

    def pause(self):
        if self.animation.state() == QAbstractAnimation.State.Running:
            self.animation.pause()

    def resume(self):
        if self.animation.state() == QAbstractAnimation.State.Paused:
            self.animation.resume()
