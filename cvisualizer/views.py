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
from .value_format import display
from .array_folding import FoldedArray, Fold
from .matrix_visuals import is_matrix, indexed, index_label, draw_row, exposed_rect
from .theme import neutral_color, track_color, apply_scene_theme, is_dark, cell_text_contrast
import math


class MemoryView(QGraphicsView):
    def __init__(self):
        super().__init__()
        self.setScene(QGraphicsScene(self))
        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self.setBackgroundBrush(neutral_color('#ffffff'))
        self.setMinimumWidth(340)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.NoAnchor)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.NoAnchor)
        self._data = ({}, [], None, {}, {}, ())
        self._rendering = False
        self._has_render = False
        self.boxes = {}
        self.matrix_stacks, self.matrix_reveals = {}, []
        self.array_anchors = {}
        self.function_boxes = {}
        self.structure_boxes = {}
        self.linked_layer = None
        self.stack_layer = None
        self._structure_names = ()
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

    def set_dark_mode(self, enabled):
        self.setBackgroundBrush(neutral_color('#ffffff', enabled))
        apply_scene_theme(self.scene(), enabled)
        self.viewport().update()

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
        name = 'array' if getattr(item, '_linked', False) else ('scalar' if key[1] is None else 'array')
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
        track_color(item, "text", color)
        item.setDefaultTextColor(neutral_color(color))
        item.setPos(x, self._content_y(y))
        return item

    def box(self, name, value, x, y, width, read=False, written=False, purple=False, compact=False, owner=None):
        fill = '#e5e7eb' if value is None else '#dcfce7'
        border = '#a1a8b3' if value is None else '#86bda4'
        if purple or self._function_context:
            fill, border = '#f3e8ff', '#a855f7'
        if read:
            border = '#60a5fa'
        if written:
            border = '#f59e0b'
        rect = self.scene().addRect(x, self._content_y(y), width, 36 if compact and not owner else 44, QPen(QColor(border), 2.5 if read or written else 1.3), QBrush(neutral_color(fill)))
        rect.setParentItem(self._content_parent)
        track_color(rect, "brush", fill)
        rect.setData(0, name)
        text = name if value is None else f'{name} = {display(value)}'
        rect.setToolTip(text + ('（未初始化）' if value is None else '') + ('\n'+str(value) if isinstance(value, Pointer) and str(value) != display(value) else ''))
        item = self.label(text, x+6, y+5 if compact else y+8, 9 if compact else 10, '#172b4d', True)
        cell_text_contrast(item, '#172b4d')
        item.setToolTip(rect.toolTip())
        item.setPlainText(QFontMetricsF(item.font()).elidedText(text, Qt.TextElideMode.ElideRight, width-14))
        rect.value_label = item
        if owner:
            item.setPos(x+6, self._content_y(y+17))
            badge = self.label(owner, x+6, y-1, 7, '#dc2626')
            badge.setParentItem(rect)
            badge.setToolTip(owner)
            badge.setPlainText(QFontMetricsF(badge.font()).elidedText(owner, Qt.TextElideMode.ElideRight, width-14))
            rect.owner_label = badge
            rect.setToolTip(f'{owner} · {rect.toolTip()}')
        return rect

    def folded_box(self, name, fold, x, y, width, matrix_columns=None, owner=None):
        count = fold.end-fold.start
        description = f'{count} 个未赋值元素' if fold.value is None else f'{count} 个相同值：{display(fold.value)}'
        if matrix_columns is not None:
            description = f'{count} 个未赋值行' if fold.value is None else f'{count} 个相同行'
            description += f' · {matrix_columns} 列'
        tooltip = f'{name}[{fold.start}..{fold.end-1}] · {description}'
        label = self.label(description, x, y-33, 9, '#64748b')
        label.setToolTip(tooltip)
        label.setPlainText(QFontMetricsF(label.font()).elidedText(description, Qt.TextElideMode.ElideRight, width))
        bracket_y = self._content_y(y-10)
        for x1,y1,x2,y2 in ((x+8,bracket_y+6,x+8,bracket_y),
                             (x+8,bracket_y,x+width-8,bracket_y),
                             (x+width-8,bracket_y,x+width-8,bracket_y+6)):
            line = self.scene().addLine(x1,y1,x2,y2,QPen(QColor('#64748b'),1.3))
            line.setParentItem(self._content_parent)
            line.setToolTip(tooltip)
        rect = self.box('',fold.value,x,y,width,owner=owner)
        rect.value_label.setPlainText('...')
        rect.value_label.setPos(x+(width-rect.value_label.boundingRect().width())/2,self._content_y(y+(17 if owner else 7)))
        rect.setToolTip(tooltip)
        rect.value_label.setToolTip(tooltip)

    def array_layout(self, name, cell, variables, model, event):
        keep = set(model.markers)
        if model.kind == 'list':
            keep.update((len(model.active)-1,len(model.active)))
        keep.update(index for key,index in self._data[3].items() if key[0] == name and key[1] == cell['identity'])
        keep.update((getattr(c['value'], 'row', None) if is_matrix(cell['value']) and getattr(c['value'], 'row', None) is not None else c['value'].index or 0) for c in variables.values()
                    if isinstance(c['value'],Pointer) and c['value'].identity == cell['identity'])
        if event and event.variables.get(name,{}).get('identity') == cell['identity']:
            # Whole-array declarations retain compact initialization; individual actions remain visible.
            whole = (name,None) in event.writes
            keep.update(index for n,index in event.reads + ([] if whole else event.writes)
                        if n == name and index is not None)
        keep = {index[0] if isinstance(index, tuple) else index for index in keep}
        return FoldedArray(model.values,keep)

    @staticmethod
    def activity(name, index, cell, event):
        if not event or event.variables.get(name, {}).get('identity') != cell.get('identity'):
            return False, False
        return ((name, index) in event.reads,
                (name, index) in event.writes or (name, None) in event.writes)

    def render(self, variables, bindings, event=None, pointers=None, index_lanes=None, functions=(), duration=600, animate=True, force=False, structures=None):
        if structures is not None and tuple(structures) != self._structure_names:
            self._structure_names = tuple(structures)
            force = True
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
        self._array_virtual = any(c.get('linked_node') or c.get('stack_node') for c in variables.values()) or any(isinstance(c['value'], list) and not c.get('is_struct') and len(c['value']) > 64 for c in variables.values())
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
            self.structure_boxes = {}
            self.matrix_stacks, self.matrix_reveals = {}, []
            self._linked_animate = animate and not same_event
            self._draw(variables, bindings, event)
            transfers = []
            if event and animate and not same_event and not event.calls:
                for source, target in dict.fromkeys(event.transfers):
                    source_front = (source[0], source[1][0], source[2]) if isinstance(source[1], tuple) else source
                    if ((source in visible_before or source_front in visible_before) and source in self.boxes and target in self.boxes
                            and self._visible_box(source) and self._visible_box(target)):
                        color = RED if isinstance(variables.get(target[0], {}).get('value'), Pointer) else '#16a34a'
                        source_box, target_box = self.boxes[source], self.boxes[target]
                        anchors = ((source_box, target_box) if any(getattr(box, '_linked', False) or getattr(box, '_stack', False) for box in (source_box, target_box)) else ())
                        transfers.append((exposed_rect(source_box), exposed_rect(target_box), color, *anchors))
            destinations = {}
            matrix_targets = {}
            lanes = {}
            for key, index in pointers.items():
                array, identity, counter, _ = key
                lane = lanes.get((array, identity), 0)
                lanes[array, identity] = lane+1
                box = self.boxes.get((array, index, identity))
                if box is None and isinstance(index, tuple):
                    box = self.boxes.get((array, index[0], identity))
                valid = box is not None
                label = f"{counter} = {variables.get(counter, {}).get('value', index[1] if isinstance(index, tuple) else index)}"
                if valid:
                    rect = box.mapRectToScene(box.rect())
                    point = QPointF(rect.left()+18+min(lane*28, rect.width()-40), rect.top()-4)
                elif (array, identity) in self.array_anchors:
                    point = self.array_anchors[array, identity] + QPointF(0, lane*22+self._draw_offset-self._array_offset())
                    value = variables[array]['value']
                    valid_index = (0 <= index[0] < len(value) and 0 <= index[1] < value.columns) if isinstance(index, tuple) else 0 <= index < len(value)
                    label += '（越界）' if not valid_index else '（未绘制）'
                else:
                    continue
                destinations[key] = (point, label, lane if valid else 0, valid)
                if box is not None and hasattr(box, 'matrix_delta'):
                    matrix_targets[key] = box
            addresses, self._marker_sections, self._marker_targets = address_markers(self, variables, lanes)
            destinations.update(addresses)
            for key, target in self._marker_targets.items():
                box = self.boxes.get(target)
                if box is not None and hasattr(box, 'matrix_delta'):
                    matrix_targets[key] = box
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
                            old = indexed(old, target_index)
                        label = index_label(name, target_index)
                        old_text = label if old is None else f'{label} = {display(old)}'
                        if getattr(item, '_stack', False):
                            old_text = display(old)
                        old_text = QFontMetricsF(item.value_label.font()).elidedText(old_text, Qt.TextElideMode.ElideRight, item.rect().width()-14)
                        effects.append((item, item.value_label, old_text, item.value_label.toPlainText()))
                summary = {'calls': event.calls, 'rect': self._sections['array'][0].rect(), 'effects': effects}
            boolean_summary = None
            if event and getattr(event, 'booleans', None):
                boolean_summary = {'evaluations': event.booleans,
                                   'rect': self._sections['array'][0].rect()}
            self.motion.start(transfers, destinations, previous, duration, animate and not same_event,
                              call_summary=summary, boolean_summary=boolean_summary,
                              matrix_reveals=self.matrix_reveals, matrix_targets=matrix_targets, linked_layer=self.linked_layer,
                              stack_layer=self.stack_layer)
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
                    old = indexed(old, index)
                    new = indexed(new, index)
                if isinstance(new, list):
                    continue
                target = index_label(name, index)
                changes.append(f'{target}: {display(old) if old is not None else "未赋值"} → {display(new) if new is not None else "未赋值"}')
            if changes:
                info = self.label('  ·  '.join(changes[:8]), 16, y, 9, '#64748b')
                info.setToolTip(info.toPlainText())
                info.setPlainText(QFontMetricsF(info.font()).elidedText(info.toPlainText(), Qt.TextElideMode.ElideRight, full_width-32))
        self.label('数组与数据结构', 16, 58, 10, '#0f172a', True)
        heading = self.label(f'{self._context} / 局部变量' if self._context else '结构体、函数与变量', rail_left+6, 58, 10, '#0f172a', True)
        heading.setToolTip(heading.toPlainText())
        heading.setPlainText(QFontMetricsF(heading.font()).elidedText(heading.toPlainText(), Qt.TextElideMode.ElideRight, rail_width-12))
        self._begin_section('scalar', 88, height, rail_width, rail_left)
        y = 100
        linked_members = {name+'.'+field for name, cell in variables.items()
                          for field in cell.get('linked_node', {}).values()}
        from .stack_state import models as stack_models
        stacks = stack_models(variables)
        self._stack_members = {model[field] for model in stacks.values() for field in ('base_name', 'top_name')}
        claimed_storage = {model['storage_identity'] for model in stacks.values() if model['storage_identity'] is not None}
        scalars = [(name, cell) for name, cell in variables.items() if not isinstance(cell['value'], list) and not cell.get('is_struct') and name not in linked_members | self._stack_members]
        functions = () if self._function_context else self._data[5]
        entries = ([('structure', name, None) for name in self._structure_names]
                   + [('function', name, None) for name in functions]
                   + [('variable', name, cell) for name, cell in scalars])
        if entries:
            for pos, (kind, name, cell) in enumerate(entries):
                x = rail_left+8
                row_y = y+pos*54
                if kind == 'structure':
                    box = self.box(name, None, x, row_y, rail_width-16, compact=True)
                    box.setBrush(QBrush(QColor('#fee2e2')))
                    track_color(box, 'brush', '#fee2e2')
                    box.setPen(QPen(QColor('#dc2626'), 1.6))
                    self.structure_boxes[name] = box
                    continue
                if kind == 'function':
                    self.function_boxes[name] = self.box(name+'()', None, x, row_y, rail_width-16, purple=True, compact=True)
                    continue
                read, written = self.activity(name, None, cell, event)
                self.boxes[name, None, cell['identity']] = self.box(name, cell['value'], x, row_y, rail_width-16, read, written, compact=True, owner=cell.get('struct_owner'))
            y += len(entries)*54
        else:
            self.label('尚无标量变量', rail_left+6, y, 9, '#64748b')
        self._end_section('scalar', y)
        self.scene().addLine(rail_left-7, 58, rail_left-7, height, QPen(QColor('#e2e8f0')))
        self._begin_section('array', 88, height, width)
        y = 100
        from .linked_visuals import LinkedLayer
        before = event.before if event and self._linked_animate else variables
        self.linked_layer = LinkedLayer(self, variables, before, width, y+76, self._linked_animate)
        if self.linked_layer.model or self.linked_layer.old_model:
            self.label('单链表 · 节点与后继指针', 16, y-8, 10, '#dc2626', True)
            y = self.linked_layer.bottom+12
        from .stack_visuals import StackLayer
        self.stack_layer = StackLayer(self, variables, before, width, y, self._linked_animate)
        y = self.stack_layer.bottom
        bound = {b.array: b for b in bindings}
        if not stacks and not self.linked_layer.model and not self.linked_layer.old_model and not any(isinstance(cell['value'], list) and not cell.get('is_struct') for cell in variables.values()):
            hint = self.label('声明数组后，在这里观察数组与数据结构。\n变量和函数显示在右侧。', 18, y, 10, '#64748b')
            hint.setTextWidth(max(80, width-36))
        for name, cell in variables.items():
            if not isinstance(cell['value'], list) or cell.get('is_struct') or cell['identity'] in claimed_storage:
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
            y += math.ceil(note.boundingRect().height())+42+marker_space
            active = model.active
            layout = self.array_layout(name,cell,variables,model,event)
            vertical = model.kind == 'stack'
            labels_below = not vertical or width < box_width+190
            row_height = ((112 if labels_below else 96) if vertical else 112)+marker_space
            matrix = is_matrix(cell['value'])
            if matrix:
                row_height = max(row_height, 136+48*min(cell['value'].columns, 4)+marker_space)
            row_columns = 1 if vertical else columns
            row_count = (len(layout)+row_columns-1)//row_columns
            start_row, end_row = 0, row_count
            if self._array_virtual:
                start_row = max(0, (self._draw_offset+88-y)//row_height-1)
                end_row = min(row_count, max(0, (self._draw_offset+height-y+row_height-1)//row_height+1))
            for pos in range(start_row*row_columns, min(len(layout), end_row*row_columns)):
                index = layout[len(layout)-1-pos if vertical else pos]
                x = 24 if vertical else 18+(pos % columns)*(box_width+12)
                cy = y+(pos//row_columns)*row_height
                if isinstance(index,Fold):
                    self.folded_box(name,index,x,cy,box_width, cell['value'].columns if matrix else None, owner=cell.get('struct_owner'))
                    if model.kind != 'array':
                        self.label('有效' if index.start in active else '空闲位', x+6,
                                   cy+45,8,'#64748b')
                    continue
                if matrix:
                    draw_row(self, name, index, cell, event, x, cy, box_width)
                    continue
                read, written = self.activity(name, index, cell, event)
                self.boxes[name, index, cell['identity']] = self.box(f'{name}[{index}]', model.values[index], x, cy, box_width, read, written, owner=cell.get('struct_owner'))
                if model.kind != 'array':
                    self.label('有效' if index in active else '空闲位', x+6 if labels_below else x+box_width+14,
                               cy+45 if labels_below else cy+11, 8, '#64748b')
                markers = model.markers.get(index, [])
                if markers:
                    self.label(' / '.join(markers), x if labels_below else x+box_width+75,
                               cy+60 if labels_below else cy+8, 9, '#0f766e', True)
            y += max(0, row_count-1)*row_height+(row_height-20 if matrix else (82 if labels_below else 58))+10
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
