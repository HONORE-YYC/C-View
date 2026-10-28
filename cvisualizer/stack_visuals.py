"""Compact pointer-stack rows, driven exclusively by MotionLayer's clock."""
from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QPen, QBrush, QPainterPath, QPolygonF, QFont, QFontMetricsF
from PySide6.QtWidgets import QGraphicsRectItem, QGraphicsTextItem, QGraphicsPathItem, QGraphicsPolygonItem

from .animations import smooth
from .stack_state import models
from .theme import neutral_color, track_color
from .value_format import display

RED, BLUE = '#dc2626', '#2563eb'
HEIGHT, ROW_HEIGHT = 54, 154


def label(parent, value, width, size=9, color='#64748b'):
    item = QGraphicsTextItem(parent)
    item.document().setDocumentMargin(0)
    item.setFont(QFont('Microsoft YaHei UI', size))
    item.setDefaultTextColor(neutral_color(color))
    track_color(item, 'text', color)
    item.setToolTip(value)
    item.setPlainText(QFontMetricsF(item.font()).elidedText(value, Qt.TextElideMode.ElideRight, max(1, width)))
    return item


def slots(model):
    if not model or not model['valid']:
        return []
    first, end = model['base'], model['top']
    if end-first <= 10:
        return list(range(end-1, first-1, -1))
    return list(range(end-1, end-6, -1))+['fold']+list(range(first+3, first-1, -1))


class StackCell(QGraphicsRectItem):
    def __init__(self, parent, value, width, tooltip, fold=False):
        super().__init__(0, 0, width, HEIGHT, parent)
        self._stack = True
        self.setPen(QPen(QColor(RED), 1.5))
        self.setBrush(QBrush(QColor('#fee2e2')))
        self.setToolTip(tooltip)
        self.value_label = label(self, str(value) if fold else display(value), width-1,
                                 7 if width < 21 else 9, '#991b1b')
        if width < 21:
            font = self.value_label.font()
            font.setPixelSize(max(5, min(9, int((width-2)/2))))
            self.value_label.setFont(font)
            self.value_label.setPlainText(QFontMetricsF(font).elidedText(str(value) if fold else display(value), Qt.TextElideMode.ElideRight, width-1))
        self.value_label.setToolTip(tooltip)
        self.value_label.setPos((width-self.value_label.boundingRect().width())/2,
                               (HEIGHT-self.value_label.boundingRect().height())/2)


class Marker(QGraphicsPathItem):
    def __init__(self, parent, name, width, upward=False):
        super().__init__(parent)
        self.upward = upward
        self.setPen(QPen(QColor(RED), 1.5))
        self.setToolTip(name)
        self.head = QGraphicsPolygonItem(self)
        self.head.setPen(QPen(Qt.PenStyle.NoPen))
        self.head.setBrush(QBrush(QColor(RED)))
        self.caption = label(self, name.rsplit('.', 1)[-1], width, 8, '#64748b')
        self.caption.setToolTip(name)

    def place(self, x, y, width):
        sign = 1 if self.upward else -1
        path = QPainterPath(QPointF(x, y+sign*18))
        path.lineTo(x, y+sign*4)
        self.setPath(path)
        self.head.setPolygon(QPolygonF([QPointF(x, y), QPointF(x-3, y+sign*6), QPointF(x+3, y+sign*6)]))
        text_width = self.caption.boundingRect().width()
        self.caption.setPos(max(4, min(x-text_width/2, width-text_width-4)),
                            y+20 if self.upward else y-35)


class StackRow:
    def __init__(self, view, model, old, width, y, animate):
        self.model, self.old, self.width, self.animate = model, old, width, animate
        self.cells, self.moves, self.ghost = {}, [], None
        self.fold_count = max(0, model['count']-9) if model['valid'] else 0
        self.cell_width = min(32., max(4., (width-36)/11))
        self.right = width-12
        self.y = y-view._draw_offset+48
        self.order, self.old_order = slots(model), slots(old)
        self.positions = self.positions_for(self.order)
        old_positions = self.positions_for(self.old_order)
        self.left = self.right-max(1, len(self.order))*self.cell_width
        old_left = self.right-max(1, len(self.old_order))*self.cell_width
        parent = view._content_parent
        title = label(parent, model['name']+' · 顺序栈', width-20, 10, '#0f172a')
        title.setPos(12, y-view._draw_offset)
        self.title = title
        self.bracket = QGraphicsPathItem(parent)
        self.bracket.setPen(QPen(QColor(BLUE), 2))
        self.bracket.setZValue(-1)
        self.top_marker = Marker(parent, model['top_name'], width*.55)
        self.base_marker = Marker(parent, model['base_name'], width*.55, True)
        self.base_marker.place(self.right-self.cell_width/2, self.y+HEIGHT+7, width)
        self.marker_start = old_left-5 if animate else self.left-5
        self.marker_end = self.left-5
        self.old_left = old_left if animate else self.left
        for index in self.order:
            fold = index == 'fold'
            value = '…' if fold else model['values'][index]
            tip = f'省略 {self.fold_count} 个元素' if fold else f"{model['storage_name']}[{index}] = {display(value)}"
            card = StackCell(parent, value, self.cell_width, tip, fold)
            if fold:
                count = QFontMetricsF(card.value_label.font()).elidedText(str(self.fold_count), Qt.TextElideMode.ElideRight, self.cell_width-1)
                card.value_label.setPlainText('…\n'+count)
                card.value_label.setPos((self.cell_width-card.value_label.boundingRect().width())/2, 10)
            self.cells[index] = card
            end = self.positions[index]
            start = old_positions.get(index, QPointF(min(old_left, self.left)-self.cell_width-10, self.y))
            if (animate and not fold and index not in old_positions and old and old.get('popped')
                    and model['count'] > old['count'] and model['popped'] == old['popped']):
                # Make room for the retained pop before sliding in the new value.
                card._stack_staged_entry = True
                start = end-QPointF(8, 0)
            self.moves.append((card, start if animate else end, end, False))
            if not fold:
                view.boxes[model['storage_name'], index, model['storage_identity']] = card
                read, written = view.activity(model['storage_name'], index,
                    {'identity': model['storage_identity']}, view._data[2])
                if read or written:
                    card.setPen(QPen(QColor('#f59e0b' if written else '#60a5fa'), 2))
        popped = model['popped']
        if popped and model['valid']:
            self.ghost = StackCell(parent, popped['value'], self.cell_width, '最近出栈：'+display(popped['value']))
            end = QPointF(self.left-self.cell_width-10, self.y)
            previous_pop = old.get('popped') if old else None
            new_pop = previous_pop != popped
            self.ghost._stack_retained_pop = not new_pop and model['count'] > (old or model)['count']
            start = old_positions.get(popped['index'], QPointF(old_left, self.y)) if new_pop else QPointF(old_left-self.cell_width-10, self.y)
            self.moves.append((self.ghost, start if animate else end, end, False))
            view.boxes.setdefault((model['storage_name'], popped['index'], model['storage_identity']), self.ghost)
        else:
            new_pop = False
        # During contraction, keep outgoing cards until the shared transition ends.
        if animate and old and old.get('storage_identity') == model.get('storage_identity'):
            for index in self.old_order:
                if index in self.order or index == 'fold' or new_pop and index == popped['index']:
                    continue
                card = StackCell(parent, old['values'][index], self.cell_width, display(old['values'][index]))
                start = old_positions[index]
                self.moves.append((card, start, QPointF(self.left-self.cell_width-10, self.y), True))
        if not self.order:
            note = '空栈' if model['valid'] else model['error']
            self.note = label(parent, note, width-26, 9, '#64748b')
            self.note.setPos(12, self.y+18)
        self.frame(0 if animate else 1)

    def positions_for(self, order):
        return {index: QPointF(self.right-(len(order)-slot)*self.cell_width, self.y)
                for slot, index in enumerate(order)}

    def frame(self, progress):
        t = smooth(progress)
        for card, start, end, outgoing in self.moves:
            staged = getattr(card, '_stack_staged_entry', False)
            phase = max(0., (progress-.4)/.6) if staged else min(1., progress/.4) if getattr(card, '_stack_retained_pop', False) else progress
            movement = smooth(phase)
            card.setPos(start+(end-start)*movement)
            card.setOpacity(movement if staged else 1-t if outgoing else 1)
            card.setVisible(not outgoing or progress < 1)
        left = self.old_left+(self.left-self.old_left)*t
        path = QPainterPath(QPointF(left-3, self.y-5))
        path.lineTo(self.right+5, self.y-5)
        path.lineTo(self.right+5, self.y+HEIGHT+5)
        path.lineTo(left-3, self.y+HEIGHT+5)
        self.bracket.setPath(path)
        self.top_marker.place(self.marker_start+(self.marker_end-self.marker_start)*t, self.y+5, self.width)


class StackLayer:
    def __init__(self, view, snapshot, before, width, top, animate):
        self.model, self.old_model = models(snapshot), models(before)
        self.rows, self.animate = {}, animate
        self.bottom = top+len(self.model)*ROW_HEIGHT
        for position, (identity, model) in enumerate(self.model.items()):
            y = top+position*ROW_HEIGHT
            if y+ROW_HEIGHT < view._draw_offset+88 or y > view._draw_offset+view.viewport().height()+ROW_HEIGHT:
                continue
            old = self.old_model.get(identity)
            if old and old['storage_identity'] != model['storage_identity']:
                old = None
            self.rows[identity] = StackRow(view, model, old, width, y, animate)

    def frame(self, progress):
        for row in self.rows.values():
            row.frame(progress)
