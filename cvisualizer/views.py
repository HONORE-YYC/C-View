"""Gray boxes are uninitialized; green boxes contain stored values.

Read/write borders are independent of initialization and structure membership.
"""
from PySide6.QtCore import Qt, QPointF
from PySide6.QtGui import QColor, QFont, QFontMetricsF, QPen, QBrush, QPainter
from PySide6.QtWidgets import QGraphicsView, QGraphicsScene, QGraphicsRectItem, QGraphicsItem, QScrollBar

from .structures import Binding, describe, KINDS
from .animations import MotionLayer
from .pointers import Pointer
from .pointer_visuals import address_markers, RED
from .numeric import Char
import math


def display(value):
    if value is None:
        return '?'
    if isinstance(value, Char):
        return f'{repr(chr(value))} ({int(value)})'
    if isinstance(value, float):
        return f'{value:.6g}'
    return str(value)


class MemoryView(QGraphicsView):
    def __init__(self):
        super().__init__()
        self.setScene(QGraphicsScene(self))
        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self.setBackgroundBrush(QColor('#ffffff'))
        self.setMinimumWidth(340)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.NoAnchor)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.NoAnchor)
        self._data = ({}, [], None, {}, {}, ())
        self._rendering = False
        self._has_render = False
        self.boxes = {}
        self.array_anchors = {}
        self.function_boxes = {}
        self._context = ''
        self._view_offsets = {}
        self._restoring_offsets = None
        self._function_context = False
        self._array_scale = 1
        self._array_extent = 0
        self._array_exact_offset = None
        self._array_virtual = False
        self.motion = MotionLayer(self.scene(), self)
        self._content_parent = None
        self._sections = {}
        self._marker_sections, self._marker_targets = {}, {}
        self.scalar_scroll = QScrollBar(Qt.Orientation.Vertical, self.viewport())
        self.array_scroll = QScrollBar(Qt.Orientation.Vertical, self.viewport())
        for name, bar in [('scalar', self.scalar_scroll), ('array', self.array_scroll)]:
            bar.setSingleStep(24)
            bar.valueChanged.connect(lambda _, section=name: self._scroll_section(section))

    def _scroll_section(self, name):
        if self._rendering or name not in self._sections:
            return
        if name == 'array':
            self._array_exact_offset = None
        if name == 'array' and self._array_virtual:
            self.render(*self._data, animate=False, force=True)
            return
        clip, content = self._sections[name]
        bar = self.scalar_scroll if name == 'scalar' else self.array_scroll
        target_y = self._draw_offset-self._array_offset() if name == 'array' else -bar.value()
        delta = target_y - content.y()
        content.setY(target_y)
        for key, item in self.motion.pointers.items():
            if self._marker_sections.get(key, 'array') == name:
                shift = QPointF(0, delta)
                item.moveBy(0, delta)
                self.motion.destinations[key] += shift
                self.motion.origins[key] += shift
                if key in self._marker_targets:
                    item.setVisible(self._visible_box(self._marker_targets[key]))
        self.motion.finish()

    def _array_offset(self):
        if self._array_exact_offset is not None:
            return self._array_exact_offset
        maximum = self.array_scroll.maximum()
        return self.array_scroll.value()*self._array_extent//maximum if maximum else 0

    def _set_array_offset(self, offset):
        self._array_exact_offset = min(self._array_extent, max(0, int(offset)))
        bar = self.array_scroll
        bar.blockSignals(True)
        bar.setValue(self._array_exact_offset*bar.maximum()//self._array_extent if self._array_extent else 0)
        bar.blockSignals(False)
        self.render(*self._data, animate=False, force=True)

    def _content_y(self, y):
        if self._content_parent is not None and self._sections.get('array', (None,None))[1] is self._content_parent:
            return y-self._draw_offset
        return y

    def _begin_section(self, name, top, bottom, width, left=0):
        clip = QGraphicsRectItem(left, top, width, max(1, bottom-top))
        clip.setPen(QPen(Qt.PenStyle.NoPen))
        clip.setFlag(QGraphicsItem.GraphicsItemFlag.ItemClipsChildrenToShape)
        self.scene().addItem(clip)
        content = QGraphicsRectItem(clip)
        content.setPen(QPen(Qt.PenStyle.NoPen))
        self._sections[name] = clip, content
        self._content_parent = content

    def _end_section(self, name, bottom):
        clip, content = self._sections[name]
        bar = self.scalar_scroll if name == 'scalar' else self.array_scroll
        rect = clip.rect()
        offset = self._array_offset() if name == 'array' else bar.value()
        if self._restoring_offsets is not None:
            offset = self._restoring_offsets[0 if name == 'scalar' else 1]
        extent = max(0, int(bottom)-int(rect.bottom()))
        maximum = min(1_000_000_000, extent)
        scale = extent / maximum if maximum else 1
        if name == 'array':
            self._array_extent, self._array_scale = extent, scale
            self._array_exact_offset = int(min(offset, extent))
        bar.blockSignals(True)
        bar.setPageStep(max(1, int(rect.height()/scale)))
        bar.setRange(0, maximum)
        bar.setValue(int(min(offset, extent))*maximum//extent if extent else 0)
        bar.blockSignals(False)
        bar.setGeometry(int(rect.right()), int(rect.top()), 16, int(rect.height()))
        bar.setVisible(bar.maximum() > 0)
        content.setY(self._draw_offset-self._array_offset() if name == 'array' else -bar.value())
        self._content_parent = None

    def _visible_box(self, key):
        item = self.boxes[key]
        name = 'scalar' if key[1] is None else 'array'
        clip, _ = self._sections[name]
        return clip.rect().contains(item.mapRectToScene(item.rect()))

    def wheelEvent(self, event):
        position = self.mapToScene(event.position().toPoint())
        for name, (clip, _) in self._sections.items():
            if clip.rect().contains(position):
                bar = self.scalar_scroll if name == 'scalar' else self.array_scroll
                pixels = event.pixelDelta().y()
                delta = pixels if pixels else event.angleDelta().y() / 120 * bar.singleStep() * 3
                if name == 'array':
                    self._set_array_offset(self._array_offset()-int(delta))
                else:
                    bar.setValue(bar.value()-int(delta))
                event.accept()
                return
        event.ignore()

    def label(self, text, x, y, size=10, color='#334155', bold=False):
        font = QFont('Microsoft YaHei UI', size)
        font.setBold(bold)
        item = self.scene().addText(str(text), font)
        if self._content_parent is not None:
            item.setParentItem(self._content_parent)
        item.setDefaultTextColor(QColor(color))
        item.setPos(x, self._content_y(y))
        return item

    def box(self, name, value, x, y, width, read=False, written=False, purple=False, compact=False):
        fill = '#e5e7eb' if value is None else '#dcfce7'
        border = '#a1a8b3' if value is None else '#86bda4'
        if purple or self._function_context:
            fill, border = '#f3e8ff', '#a855f7'
        if read:
            border = '#60a5fa'
        if written:
            border = '#f59e0b'
        rect = self.scene().addRect(x, self._content_y(y), width, 36 if compact else 44, QPen(QColor(border), 2.5 if read or written else 1.3), QBrush(QColor(fill)))
        rect.setParentItem(self._content_parent)
        rect.setData(0, name)
        text = name if value is None else f'{name} = {display(value)}'
        rect.setToolTip(text + ('（未初始化）' if value is None else ''))
        item = self.label(text, x+6, y+5 if compact else y+8, 9 if compact else 10, '#172b4d', True)
        item.setToolTip(rect.toolTip())
        item.setPlainText(QFontMetricsF(item.font()).elidedText(text, Qt.TextElideMode.ElideRight, width-14))
        rect.value_label = item
        return rect

    @staticmethod
    def activity(name, index, cell, event):
        if not event or event.variables.get(name, {}).get('identity') != cell.get('identity'):
            return False, False
        return ((name, index) in event.reads,
                (name, index) in event.writes or (name, None) in event.writes)

    def render(self, variables, bindings, event=None, pointers=None, index_lanes=None, functions=(), duration=600, animate=True, force=False):
        pointers = pointers or {}
        data = (variables, list(bindings), event, pointers, index_lanes or {}, tuple(functions))
        if self._rendering:
            return
        if self._has_render and not force and data == self._data:
            return
        self._has_render = True
        context = event.function if event else ''
        self._restoring_offsets = None
        if context != self._context:
            self._view_offsets[self._context] = (self.scalar_scroll.value(), self._array_offset())
            self._restoring_offsets = self._view_offsets.get(context, (0, 0))
            self._context = context
        if event is None and not variables:
            self._view_offsets.clear()
            self._restoring_offsets = (0, 0)
        self._function_context = bool(context)
        self._array_virtual = any(isinstance(c['value'], list) and len(c['value']) > 64 for c in variables.values())
        self._draw_offset = self._restoring_offsets[1] if self._restoring_offsets is not None else self._array_offset()
        previous = {key: QPointF(item.pos()) for key, item in self.motion.pointers.items()}
        was_busy = self.motion.busy
        visible_before = {key for key in self.boxes if self._visible_box(key)}
        same_event = event is self._data[2]
        self._data = data
        self._rendering = True
        try:
            self.motion.clear()
            self.boxes, self.array_anchors, self.function_boxes = {}, {}, {}
            self._draw(variables, bindings, event)
            transfers = []
            if event and animate and not same_event and not event.calls:
                for source, target in dict.fromkeys(event.transfers):
                    if (source in visible_before and source in self.boxes and target in self.boxes
                            and self._visible_box(source) and self._visible_box(target)):
                        color = RED if isinstance(variables.get(target[0], {}).get('value'), Pointer) else '#16a34a'
                        transfers.append((self.boxes[source].mapRectToScene(self.boxes[source].rect()),
                                          self.boxes[target].mapRectToScene(self.boxes[target].rect()), color))
            destinations = {}
            lanes = {}
            for key, index in pointers.items():
                array, identity, counter, _ = key
                lane = lanes.get((array, identity), 0)
                lanes[array, identity] = lane+1
                box = self.boxes.get((array, index, identity))
                valid = box is not None
                label = f"{counter} = {variables.get(counter, {}).get('value', index)}"
                if valid:
                    rect = box.mapRectToScene(box.rect())
                    point = QPointF(rect.left()+18+min(lane*28, rect.width()-40), rect.top()-4)
                elif (array, identity) in self.array_anchors:
                    point = self.array_anchors[array, identity] + QPointF(0, lane*22+self._draw_offset-self._array_offset())
                    label += '（越界）' if not 0 <= index < len(variables[array]['value']) else '（未绘制）'
                else:
                    continue
                destinations[key] = (point, label, lane if valid else 0, valid)
            addresses, self._marker_sections, self._marker_targets = address_markers(self, variables, lanes)
            destinations.update(addresses)
            summary = None
            if event and event.calls and not event.expanded and animate and not same_event:
                effects = []
                for name, index in dict.fromkeys(event.writes):
                    cell = variables.get(name)
                    if not cell:
                        continue
                    indices = [key[1] for key in self.boxes if key[0] == name] if index is None and isinstance(cell['value'], list) else [index]
                    for target_index in indices:
                        key = name, target_index, cell['identity']
                        item = self.boxes.get(key)
                        if item is None:
                            continue
                        before = event.before.get(name, {})
                        old = before.get('value') if before.get('identity') == cell['identity'] else None
                        if target_index is not None:
                            old = old[target_index] if isinstance(old, list) and target_index < len(old) else None
                        label = name if target_index is None else f'{name}[{target_index}]'
                        old_text = label if old is None else f'{label} = {display(old)}'
                        old_text = QFontMetricsF(item.value_label.font()).elidedText(old_text, Qt.TextElideMode.ElideRight, item.rect().width()-14)
                        effects.append((item, item.value_label, old_text, item.value_label.toPlainText()))
                summary = {'calls': event.calls, 'rect': self._sections['array'][0].rect(), 'effects': effects}
            self.motion.start(transfers, destinations, previous, duration, animate and not same_event,
                              call_summary=summary)
            for key, item in self.motion.pointers.items():
                if key in addresses:
                    item.setParentItem(self._address_clip)
                    if key in self._marker_targets:
                        item.setVisible(self._visible_box(self._marker_targets[key]))
                else:
                    item.setParentItem(self._sections['array'][0])
        finally:
            self._rendering = False
            self._restoring_offsets = None
        if was_busy and not self.motion.busy:
            self.motion.settled.emit()
        if self._array_virtual and abs(self._draw_offset - self._array_offset()) > 1:
            self.render(*self._data, animate=False, force=True)

    def _draw(self, variables, bindings, event):
        self.scene().clear()
        self._sections = {}
        self._content_parent = None
        full_width = max(320, self.viewport().width()-20)
        height = max(1, self.viewport().height()-8)
        rail_width = min(184, max(120, int(full_width*.3)))
        width = full_width-rail_width-28
        rail_left = width+28
        self.scene().setSceneRect(0, 0, self.viewport().width(), self.viewport().height())
        self._address_clip = QGraphicsRectItem(0, 88, self.viewport().width(), max(1, height-88))
        self._address_clip.setPen(QPen(Qt.PenStyle.NoPen))
        self._address_clip.setFlag(QGraphicsItem.GraphicsItemFlag.ItemClipsChildrenToShape)
        self._address_clip.setZValue(15)
        self.scene().addItem(self._address_clip)
        columns = max(1, int((width-28)//150))
        box_width = (width-28)/columns-12
        y = 12
        if event:
            title = self.label(f'本步：{event.text}', 16, y, 10, '#0f766e', True)
            title.setToolTip(title.toPlainText())
            title.setPlainText(QFontMetricsF(title.font()).elidedText(title.toPlainText().replace('\n', ' '), Qt.TextElideMode.ElideRight, full_width-32))
            y = 32
            changes = []
            for name, index in dict.fromkeys(event.writes):
                after_cell = event.variables.get(name, {})
                before_cell = event.before.get(name, {})
                if before_cell.get('identity') != after_cell.get('identity'):
                    before_cell = {}
                old, new = before_cell.get('value'), after_cell.get('value')
                if index is not None:
                    old = old[index] if isinstance(old, list) and index < len(old) else None
                    new = new[index] if isinstance(new, list) and index < len(new) else None
                if isinstance(new, list):
                    continue
                target = name + (f'[{index}]' if index is not None else '')
                changes.append(f'{target}: {display(old) if old is not None else "未赋值"} → {display(new) if new is not None else "未赋值"}')
            if changes:
                info = self.label('  ·  '.join(changes[:8]), 16, y, 9, '#64748b')
                info.setToolTip(info.toPlainText())
                info.setPlainText(QFontMetricsF(info.font()).elidedText(info.toPlainText(), Qt.TextElideMode.ElideRight, full_width-32))
        self.label('数组与数据结构', 16, 58, 10, '#0f172a', True)
        heading = self.label(f'{self._context} / 局部变量' if self._context else '变量与函数', rail_left+6, 58, 10, '#0f172a', True)
        heading.setToolTip(heading.toPlainText())
        heading.setPlainText(QFontMetricsF(heading.font()).elidedText(heading.toPlainText(), Qt.TextElideMode.ElideRight, rail_width-12))
        self._begin_section('scalar', 88, height, rail_width, rail_left)
        y = 100
        scalars = [(name, cell) for name, cell in variables.items() if not isinstance(cell['value'], list)]
        functions = () if self._function_context else self._data[5]
        entries = [('function', name, None) for name in functions] + [('variable', name, cell) for name, cell in scalars]
        if entries:
            for pos, (kind, name, cell) in enumerate(entries):
                x = rail_left+8
                row_y = y+pos*54
                if kind == 'function':
                    self.function_boxes[name] = self.box(name+'()', None, x, row_y, rail_width-16, purple=True, compact=True)
                    continue
                read, written = self.activity(name, None, cell, event)
                self.boxes[name, None, cell['identity']] = self.box(name, cell['value'], x, row_y, rail_width-16, read, written, compact=True)
            y += len(entries)*54
        else:
            self.label('尚无标量变量', rail_left+6, y, 9, '#64748b')
        self._end_section('scalar', y)
        self.scene().addLine(rail_left-7, 58, rail_left-7, height, QPen(QColor('#e2e8f0')))
        self._begin_section('array', 88, height, width)
        y = 100
        bound = {b.array: b for b in bindings}
        if not any(isinstance(cell['value'], list) for cell in variables.values()):
            hint = self.label('声明数组后，在这里观察数组与数据结构。\n变量和函数显示在右侧。', 18, y, 10, '#64748b')
            hint.setTextWidth(max(80, width-36))
        for name, cell in variables.items():
            if not isinstance(cell['value'], list):
                continue
            model = describe(bound.get(name, Binding(name)), variables)
            self.label(f'{name}  /  {KINDS[model.kind]}', 16, y, 13, '#0f172a', True)
            self.array_anchors[name, cell['identity']] = QPointF(width-170, self._content_y(y+20))
            y += 34
            note = self.label(model.error or model.note or f'capacity = {len(model.values)}', 16, y, 9,
                              '#b45309' if model.error else '#64748b')
            note.setToolTip(note.toPlainText())
            note.setPlainText(QFontMetricsF(note.font()).elidedText(note.toPlainText().replace('\n', ' '), Qt.TextElideMode.ElideRight, width-30))
            # Reserve lanes from the program before counters enter/leave scope.
            pointer_count = self._data[4].get(cell.get('declaration'),
                sum(key[0] == name and key[1] == cell['identity'] for key in self._data[3]))
            pointer_count = max(pointer_count, self._data[4].get('__indirect_index_slots__', 0))
            pointer_count += self._data[4].get('__pointer_slots__',
                sum(isinstance(c['value'], Pointer) for c in variables.values()))
            marker_space = 20*max(0, pointer_count-1)
            y += math.ceil(note.boundingRect().height())+(42 if pointer_count else 12)+marker_space
            active = model.active
            vertical = model.kind == 'stack'
            labels_below = not vertical or width < box_width+190
            row_height = ((112 if labels_below else 96) if vertical else 112)+marker_space
            row_columns = 1 if vertical else columns
            row_count = (len(model.values)+row_columns-1)//row_columns
            start_row, end_row = 0, row_count
            if self._array_virtual:
                start_row = max(0, (self._draw_offset+88-y)//row_height-1)
                end_row = min(row_count, max(0, (self._draw_offset+height-y+row_height-1)//row_height+1))
            for pos in range(start_row*row_columns, min(len(model.values), end_row*row_columns)):
                index = len(model.values)-1-pos if vertical else pos
                x = 24 if vertical else 18+(pos % columns)*(box_width+12)
                cy = y+(pos//row_columns)*row_height
                read, written = self.activity(name, index, cell, event)
                self.boxes[name, index, cell['identity']] = self.box(f'{name}[{index}]', model.values[index], x, cy, box_width, read, written)
                if model.kind != 'array':
                    self.label('有效' if index in active else '空闲位', x+6 if labels_below else x+box_width+14,
                               cy+45 if labels_below else cy+11, 8, '#64748b')
                markers = model.markers.get(index, [])
                if markers:
                    self.label(' / '.join(markers), x if labels_below else x+box_width+75,
                               cy+60 if labels_below else cy+8, 9, '#0f766e', True)
            y += max(0, row_count-1)*row_height+(82 if labels_below else 58)+10
            if model.kind in ('list', 'queue'):
                order = ' → '.join(display(v) for v in model.logical[:20]) or '（空）'
                if len(model.logical) > 20:
                    order += ' → …'
                text = self.label('逻辑顺序：'+order, 18, y, 9, '#0f766e')
                text.setTextWidth(width-36)
                y += math.ceil(text.boundingRect().height())+12
            line = self.scene().addLine(16, self._content_y(y+4), width-4, self._content_y(y+4), QPen(QColor('#e2e8f0')))
            line.setParentItem(self._content_parent)
            y += 30
        self._end_section('array', y)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.render(*self._data, animate=False, force=True)

    def closeEvent(self, event):
        self.motion.clear()
        super().closeEvent(event)
