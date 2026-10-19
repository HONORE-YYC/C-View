"""Boolean evaluation overlays; presentation never evaluates source code."""
from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QFont, QFontMetricsF, QPen
from PySide6.QtWidgets import QGraphicsItem, QGraphicsRectItem, QGraphicsSimpleTextItem

from .value_format import display
from .theme import neutral_color, track_color, cell_text_contrast


class BooleanSummary:
    def __init__(self, scene, spec):
        self.scene = scene
        self.evaluations = list(spec['evaluations'])
        rect = QRectF(spec['rect'])
        self.root = QGraphicsRectItem(QRectF(0, 0, max(1, rect.width()), max(1, rect.height())))
        self.root.setPos(rect.topLeft())
        self.root.setPen(QPen(Qt.PenStyle.NoPen))
        self.root.setBrush(QBrush(Qt.BrushStyle.NoBrush))
        self.root.setFlag(QGraphicsItem.GraphicsItemFlag.ItemClipsChildrenToShape)
        self.root.setZValue(45)
        scene.addItem(self.root)
        self.box = QGraphicsRectItem(QRectF(0, 0, 380, 100), self.root)
        self.label = QGraphicsSimpleTextItem(self.box)
        self.label.setFont(QFont('Microsoft YaHei UI', 12, QFont.Weight.Bold))
        track_color(self.label, 'brush', '#172b4d')
        self.label.setBrush(QBrush(neutral_color('#172b4d')))
        cell_text_contrast(self.label, '#172b4d')
        self.label.setPos(14, 20)
        self.result_label = QGraphicsSimpleTextItem(self.box)
        self.result_label.setFont(QFont('Microsoft YaHei UI', 11))
        self.result_label.setPos(14, 62)
        scale = min(1., self.root.rect().width()/400, self.root.rect().height()/120)
        self.box.setScale(scale)
        self.box.setPos((self.root.rect().width()-380*scale)/2,
                        (self.root.rect().height()-100*scale)/2)
        self.index = -1
        self.frame(0.)

    def frame(self, progress):
        from .animations import smooth
        cycle = min(max(0., float(progress)), .999999) * len(self.evaluations)
        index = min(int(cycle), len(self.evaluations)-1)
        local = cycle-index
        entry = self.evaluations[index]
        result = bool(entry['result'])
        if index != self.index:
            self.index = index
            expression = entry.get('expression', '')
            values = entry.get('operands')
            detail = ', '.join(display(value) for value in values) if values is not None else display(entry.get('value'))
            self.input_text = f'{expression}   [{detail}]'
            self.box.setToolTip(self.input_text + ' → ' + ('true' if result else 'false'))
        answered = local >= .48
        text = self.input_text + (' → ' + ('true' if result else 'false') if answered else '')
        self.label.setText(QFontMetricsF(self.label.font()).elidedText(text, Qt.TextElideMode.ElideRight, 350))
        self.label.setToolTip(self.box.toolTip())
        self.result_label.setText(('真 · true' if result else '假 · false') if answered else '布尔判断')
        result_color = ('#166534' if result else '#991b1b') if answered else '#64748b'
        track_color(self.result_label, 'brush', result_color)
        self.result_label.setBrush(QBrush(neutral_color(result_color)))
        cell_text_contrast(self.result_label, result_color)
        target = QColor('#86efac' if result else '#fca5a5')
        origin = QColor('#e5e7eb')
        amount = smooth((local-.22)/.26)
        color = QColor(*(round(a+(b-a)*amount) for a, b in zip(origin.getRgb(), target.getRgb())))
        self.box.setBrush(QBrush(color))
        self.box.setPen(QPen(QColor(('#16a34a' if result else '#dc2626') if answered else '#a1a8b3'), 2))
        self.root.setOpacity(1-smooth((local-.78)/.22))

    def close(self):
        if self.root.scene() is self.scene:
            self.scene.removeItem(self.root)
