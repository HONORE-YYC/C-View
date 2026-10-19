"""Function-call overlays driven exclusively by MotionLayer's animation clock."""
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QFont, QPainterPath, QPen
from PySide6.QtWidgets import QGraphicsItem, QGraphicsRectItem, QGraphicsSimpleTextItem
from .value_format import display as display_value

PURPLE = '#9333ea'
PURPLE_FILL = '#e9d5ff'


class FunctionSummary:
    """A clipped input→function diagram followed by an affected-value pulse."""

    def __init__(self, scene, spec):
        self.scene = scene
        self.calls = list(spec['calls'])
        self.call_count = len(spec['calls'])
        self.effects = [(box, label, old, new, QBrush(box.brush()), QPen(box.pen()))
                        for box, label, old, new in spec.get('effects', [])]
        for box, label, old, new, brush, pen in self.effects:
            label.setPlainText(old)
        rect = QRectF(spec['rect'])
        self.root = QGraphicsRectItem(QRectF(0, 0, max(0, rect.width()), max(0, rect.height())))
        self.root.setPos(rect.topLeft())
        self.root.setPen(QPen(Qt.PenStyle.NoPen))
        self.root.setBrush(QBrush(QColor('#faf5ff')))
        self.root.setFlag(QGraphicsItem.GraphicsItemFlag.ItemClipsChildrenToShape)
        self.root.setZValue(40)
        self.scene.addItem(self.root)
        self.content = None
        self.call_index = -1
        self.arrows = []
        self.frame(0.)

    def _text(self, text, x, y, width, parent, size=10, bold=False):
        item = QGraphicsSimpleTextItem(text, parent)
        item.setFont(QFont('Microsoft YaHei UI', size,
                           QFont.Weight.Bold if bold else QFont.Weight.Normal))
        item.setBrush(QBrush(QColor('#581c87')))
        item.setToolTip(text)
        while item.boundingRect().width() > width and len(item.text()) > 2:
            item.setText(item.text()[:-2] + '…')
        item.setPos(x, y)
        return item

    def _box(self, rect, text, tooltip, compact=False):
        box = QGraphicsRectItem(rect, self.content)
        box.setPen(QPen(QColor('#c084fc'), 1.5))
        box.setBrush(QBrush(QColor('#f3e8ff')))
        box.setToolTip(tooltip)
        inset = 4 if compact else 8
        label = self._text(text, rect.x()+inset, rect.y()+(5 if compact else 9),
                           rect.width()-2*inset, box, size=8 if compact else 10, bold=True)
        label.setToolTip(tooltip)
        return box

    def _build_call(self, index):
        from .animations import TransferArrow
        self.arrows = []
        if self.content is not None:
            self.scene.removeItem(self.content)
            self.content.setParentItem(None)
        self.call_index = index
        call = self.calls[index]
        inputs = call.get('inputs', [])
        input_tooltip = '\n'.join(
            f"{entry.get('expression', entry.get('name', ''))} → "
            f"{entry.get('name', '')} = {display_value(entry.get('value'))}"
            for entry in inputs)
        compact = self.root.rect().width() < 300 or self.root.rect().height() < 130
        shown = inputs[:1 if compact else 4]
        width = max(160, min(460, self.root.rect().width())) if compact else 460
        height = 60 if compact else max(150, 60 + max(1, len(shown))*49)
        self.content = QGraphicsRectItem(QRectF(0, 0, width, height), self.root)
        self.content.setPen(QPen(Qt.PenStyle.NoPen))
        self.content.setBrush(QBrush(Qt.BrushStyle.NoBrush))
        scale = min(self.root.rect().width()/width, self.root.rect().height()/height, 1.)
        self.content.setScale(scale)
        self.content.setPos((self.root.rect().width()-width*scale)/2,
                            (self.root.rect().height()-height*scale)/2)
        count = f' · {index+1}/{self.call_count}' if self.call_count > 1 else ''
        self._text('函数调用' + count, 5 if compact else 16, 1 if compact else 8,
                   width-10, self.content, size=8 if compact else 10, bold=True)
        target = (QRectF(width*.62, 25, width*.35, 29) if compact
                  else QRectF(304, height/2-20, 140, 44))
        result = ('无返回值' if call.get('return') is None
                  else '返回 ' + display_value(call['return']))
        self._box(target, call['name'] + '()', call['name'] + '()\n' + result, compact)
        if not compact:
            self._text(result, 306, target.bottom()+8,
                       138, self.content, size=9)
        if not shown:
            shown = [{'name': '', 'expression': '无参数', 'value': ''}]
        for row, entry in enumerate(shown):
            source = (QRectF(5, 25, width*.43, 29) if compact
                      else QRectF(16, 40+row*49, 200, 39))
            expression = str(entry.get('expression', entry.get('name', '')))
            name = entry.get('name', '')
            value = display_value(entry.get('value'))
            text = f'{expression} = {value}' if name else expression
            tooltip = f'{expression} → {name} = {value}' if name else expression
            if compact and len(inputs) > 1:
                text += f' (+{len(inputs)-1})'
                tooltip = input_tooltip
            self._box(source, text, tooltip, compact)
            arrow = TransferArrow(source, target, PURPLE)
            arrow.setParentItem(self.content)
            start = QPointF(source.right()+3, source.center().y())
            end = QPointF(target.left()-3, target.center().y())
            arrow.route = QPainterPath(start)
            arrow.route.cubicTo(start+QPointF(40, 0), end-QPointF(40, 0), end)
            self.arrows.append(arrow)
        if len(inputs) > 4 and not compact:
            overflow = self._text(f'另有 {len(inputs)-4} 个参数', 16, height-18, 200,
                                  self.content, size=8)
            overflow.setToolTip(input_tooltip)

    def frame(self, progress):
        from .animations import smooth
        progress = max(0., min(1., float(progress)))
        cycle = min(progress/.65, .999999) * len(self.calls)
        index = min(int(cycle), len(self.calls)-1)
        if index != self.call_index:
            self._build_call(index)
        for arrow in self.arrows:
            arrow.frame(cycle-index if progress < .65 else 1.)
        self.root.setOpacity(1-smooth((progress-.62)/.06))
        # The overlay is gone before the result pulse reveals the real memory boxes.
        for box, label, old, new, brush, pen in self.effects:
            if progress < .69:
                label.setPlainText(old)
                box.setBrush(brush)
                box.setPen(pen)
            else:
                label.setPlainText(new)
                fade = smooth((progress-.84)/.16)
                original, purple = brush.color(), QColor(PURPLE_FILL)
                color = QColor(*(round(a+(b-a)*fade) for a, b in zip(
                    purple.getRgb(), original.getRgb())))
                box.setBrush(QBrush(color) if progress < 1 else brush)
                border = QPen(pen)
                border.setColor(QColor(*(round(a+(b-a)*fade) for a, b in zip(
                    QColor(PURPLE).getRgb(), pen.color().getRgb()))))
                border.setWidthF(max(2, pen.widthF()))
                border.setStyle(Qt.PenStyle.SolidLine)
                box.setPen(border if progress < 1 else pen)

    def close(self):
        for box, label, old, new, brush, pen in self.effects:
            box.setBrush(brush)
            box.setPen(pen)
            label.setPlainText(new)
        self.effects = []
        if self.root.scene() is self.scene:
            self.scene.removeItem(self.root)
