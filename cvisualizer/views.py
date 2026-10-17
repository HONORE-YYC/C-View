"""Gray boxes are uninitialized; green boxes contain stored values.

Read/write borders are independent of initialization and structure membership.
"""
from PySide6.QtCore import Qt, QPointF
from PySide6.QtGui import QColor, QFont, QFontMetricsF, QPen, QBrush, QPainter
from PySide6.QtWidgets import QGraphicsView, QGraphicsScene, QGraphicsRectItem, QGraphicsItem, QScrollBar

from .structures import Binding, describe, KINDS
from .animations import MotionLayer


def display(value):
    if value is None:
        return '?'
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
        self.motion = MotionLayer(self.scene(), self)
        self._content_parent = None
        self._sections = {}
        self.scalar_scroll = QScrollBar(Qt.Orientation.Vertical, self.viewport())
        self.array_scroll = QScrollBar(Qt.Orientation.Vertical, self.viewport())
        for name, bar in [('scalar', self.scalar_scroll), ('array', self.array_scroll)]:
            bar.setSingleStep(24)
            bar.valueChanged.connect(lambda _, section=name: self._scroll_section(section))

    def _scroll_section(self, name):
        if self._rendering or name not in self._sections:
            return
        clip, content = self._sections[name]
        bar = self.scalar_scroll if name == 'scalar' else self.array_scroll
        delta = -bar.value() - content.y()
        content.setY(-bar.value())
        if name == 'array':
            for key, item in self.motion.pointers.items():
                shift = QPointF(0, delta)
                item.moveBy(0, delta)
                self.motion.destinations[key] += shift
                self.motion.origins[key] += shift
        self.motion.finish()

    def _begin_section(self, name, top, bottom, width):
        clip = QGraphicsRectItem(0, top, width, max(1, bottom-top))
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
        bar.blockSignals(True)
        bar.setPageStep(int(rect.height()))
        bar.setRange(0, max(0, int(bottom-rect.bottom())))
        if self._restoring_offsets is not None:
            bar.setValue(self._restoring_offsets[0 if name == 'scalar' else 1])
        bar.blockSignals(False)
        bar.setGeometry(int(rect.right()), int(rect.top()), 16, int(rect.height()))
        bar.setVisible(bar.maximum() > 0)
        content.setY(-bar.value())
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
        item.setPos(x, y)
        return item

    def box(self, name, value, x, y, width, read=False, written=False, purple=False):
        fill = '#e5e7eb' if value is None else '#dcfce7'
        border = '#a1a8b3' if value is None else '#86bda4'
        if purple or self._function_context:
            fill, border = '#f3e8ff', '#a855f7'
        if read:
            border = '#60a5fa'
        if written:
            border = '#f59e0b'
        rect = self.scene().addRect(x, y, width, 44, QPen(QColor(border), 2.5 if read or written else 1.3), QBrush(QColor(fill)))
        rect.setParentItem(self._content_parent)
        rect.setData(0, name)
        text = name if value is None else f'{name} = {display(value)}'
        rect.setToolTip(text + ('（未初始化）' if value is None else ''))
        item = self.label(text, x+6, y+8, 10, '#172b4d', True)
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
            self._view_offsets[self._context] = (self.scalar_scroll.value(), self.array_scroll.value())
            self._restoring_offsets = self._view_offsets.get(context, (0, 0))
            self._context = context
        if event is None and not variables:
            self._view_offsets.clear()
            self._restoring_offsets = (0, 0)
        self._function_context = bool(context)
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
                        transfers.append((self.boxes[source].mapRectToScene(self.boxes[source].rect()),
                                          self.boxes[target].mapRectToScene(self.boxes[target].rect())))
            destinations = {}
            lanes = {}
            for key, index in pointers.items():
                array, identity, counter, _ = key
                lane = lanes.get((array, identity), 0)
                lanes[array, identity] = lane+1
                box = self.boxes.get((array, index, identity))
                valid = box is not None
                label = f'{counter} = {index}'
                if valid:
                    rect = box.mapRectToScene(box.rect())
                    point = QPointF(rect.left()+18+min(lane*28, rect.width()-40), rect.top()-4)
                elif (array, identity) in self.array_anchors:
                    point = self.array_anchors[array, identity] + QPointF(0, lane*22-self.array_scroll.value())
                    label += '（越界）' if not 0 <= index < len(variables[array]['value']) else '（未绘制）'
                else:
                    continue
                destinations[key] = (point, label, lane if valid else 0, valid)
            summary = None
            if event and event.calls and not event.expanded and animate and not same_event:
                effects = []
                for name, index in dict.fromkeys(event.writes):
                    cell = variables.get(name)
                    if not cell:
                        continue
                    indices = range(min(64, len(cell['value']))) if index is None and isinstance(cell['value'], list) else [index]
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
            for item in self.motion.pointers.values():
                item.setParentItem(self._sections['array'][0])
        finally:
            self._rendering = False
            self._restoring_offsets = None
        if was_busy and not self.motion.busy:
            self.motion.settled.emit()

    def _draw(self, variables, bindings, event):
        self.scene().clear()
        self._sections = {}
        self._content_parent = None
        width = max(300, self.viewport().width()-28)
        height = max(1, self.viewport().height())
        self.scene().setSceneRect(0, 0, self.viewport().width(), self.viewport().height())
        columns = max(2, int((width-24)//150))
        box_width = (width-28)/columns-12
        y = 12
        if not variables and not self._data[5]:
            for bar in (self.scalar_scroll, self.array_scroll):
                bar.setValue(0)
                bar.hide()
            self.label('每一步，都看得见', 18, y+12, 18, '#0f766e', True)
            item = self.label('定义变量或数组后，这里会生成方框。\n灰色：未赋值，仅显示名字\n绿色：已有值，显示「名字 = 值」\n蓝色边框：读取  ·  橙色边框：写入', 18, y+58, 10)
            item.setTextWidth(width-36)
            return
        if event:
            title = self.label(f'本步：{event.text}', 16, y, 10, '#0f766e', True)
            title.setToolTip(title.toPlainText())
            title.setPlainText(QFontMetricsF(title.font()).elidedText(title.toPlainText().replace('\n', ' '), Qt.TextElideMode.ElideRight, width-32))
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
                info.setPlainText(QFontMetricsF(info.font()).elidedText(info.toPlainText(), Qt.TextElideMode.ElideRight, width-32))
        scalar_bottom = min(220, max(144, int(height*.33)))
        self.label(f'函数 {self._context} / 局部变量' if self._context else '变量与函数', 16, 58, 12, '#0f172a', True)
        self._begin_section('scalar', 88, scalar_bottom, width)
        y = 100
        scalars = [(name, cell) for name, cell in variables.items() if not isinstance(cell['value'], list)]
        functions = () if self._function_context else self._data[5]
        entries = [('function', name, None) for name in functions] + [('variable', name, cell) for name, cell in scalars]
        if entries:
            for pos, (kind, name, cell) in enumerate(entries):
                x = 18+(pos % columns)*(box_width+12)
                row_y = y+(pos//columns)*63
                if kind == 'function':
                    self.function_boxes[name] = self.box(name+'()', None, x, row_y, box_width, purple=True)
                    continue
                read, written = self.activity(name, None, cell, event)
                self.boxes[name, None, cell['identity']] = self.box(name, cell['value'], x, row_y, box_width, read, written)
            y += ((len(entries)+columns-1)//columns)*63+16
        else:
            self.label('尚无标量变量', 18, y, 10, '#64748b')
        self._end_section('scalar', y)
        self.scene().addLine(16, scalar_bottom+6, width-4, scalar_bottom+6, QPen(QColor('#e2e8f0')))
        self._begin_section('array', scalar_bottom+12, height, width)
        y = scalar_bottom+20
        bound = {b.array: b for b in bindings}
        if not any(isinstance(cell['value'], list) for cell in variables.values()):
            self.label('声明数组后，在这里观察数组与数据结构。', 18, y, 10, '#64748b')
        for name, cell in variables.items():
            if not isinstance(cell['value'], list):
                continue
            model = describe(bound.get(name, Binding(name)), variables)
            self.label(f'{name}  /  {KINDS[model.kind]}', 16, y, 13, '#0f172a', True)
            self.array_anchors[name, cell['identity']] = QPointF(width-170, y+20)
            y += 34
            note = self.label(model.error or model.note or f'capacity = {len(model.values)}', 16, y, 9,
                              '#b45309' if model.error else '#64748b')
            note.setToolTip(note.toPlainText())
            note.setPlainText(QFontMetricsF(note.font()).elidedText(note.toPlainText().replace('\n', ' '), Qt.TextElideMode.ElideRight, width-30))
            # Reserve lanes from the program before counters enter/leave scope.
            pointer_count = self._data[4].get(cell.get('declaration'),
                sum(key[0] == name and key[1] == cell['identity'] for key in self._data[3]))
            marker_space = 20*max(0, pointer_count-1)
            y += note.boundingRect().height()+(42 if pointer_count else 12)+marker_space
            active = set(model.active)
            visible = list(range(min(64, len(model.values))))
            vertical = model.kind == 'stack'
            if vertical:
                visible.reverse()
            max_bottom = y
            for pos, index in enumerate(visible):
                x = 24 if vertical else 18+(pos % columns)*(box_width+12)
                cy = y+pos*(96+marker_space) if vertical else y+(pos//columns)*(112+marker_space)
                read, written = self.activity(name, index, cell, event)
                self.boxes[name, index, cell['identity']] = self.box(f'{name}[{index}]', model.values[index], x, cy, box_width, read, written)
                if model.kind != 'array':
                    self.label('有效' if index in active else '空闲位', x+6 if not vertical else x+box_width+14,
                               cy+45 if not vertical else cy+11, 8, '#64748b')
                markers = model.markers.get(index, [])
                if markers:
                    self.label(' / '.join(markers), x+box_width+75 if vertical else x,
                               cy+8 if vertical else cy+60, 9, '#0f766e', True)
                max_bottom = max(max_bottom, cy+(58 if vertical else 82))
            y = max_bottom+10
            if len(model.values) > 64:
                self.label(f'仅绘制前 64 / {len(model.values)} 个单元；执行器处理完整数组', 18, y, 9, '#64748b')
                y += 32
            if model.kind in ('list', 'queue'):
                order = ' → '.join(display(v) for v in model.logical[:20]) or '（空）'
                if len(model.logical) > 20:
                    order += ' → …'
                text = self.label('逻辑顺序：'+order, 18, y, 9, '#0f766e')
                text.setTextWidth(width-36)
                y += text.boundingRect().height()+12
            line = self.scene().addLine(16, y+4, width-4, y+4, QPen(QColor('#e2e8f0')))
            line.setParentItem(self._content_parent)
            y += 30
        self._end_section('array', y)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.render(*self._data, animate=False, force=True)

    def closeEvent(self, event):
        self.motion.clear()
        super().closeEvent(event)
