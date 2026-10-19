"""Resolve typed addresses into red markers without evaluating C expressions."""
from PySide6.QtCore import QPointF

from .pointers import Pointer


RED = '#dc2626'


def address_markers(view, variables, blue_lanes):
    destinations, sections, targets = {}, {}, {}
    by_identity = {cell['identity']: (name, cell) for name, cell in variables.items()}
    array_lanes, scalar_lanes = {}, {}
    for name, cell in variables.items():
        address = cell['value']
        if not isinstance(address, Pointer) or address.identity is None:
            continue
        target = by_identity.get(address.identity)
        if target is None:
            continue
        target_name, target_cell = target
        # Aggregate instances are represented by their member cards, so anchor
        # a structure pointer to its first visible member instead of a hidden root.
        if target_cell.get('is_struct'):
            is_array = isinstance(target_cell['value'], list)
            if not is_array and address.index not in (None, 0):
                continue
            prefix = target_name + (f'[{address.index or 0}]' if is_array else '') + '.'
            member_key = next((box_key for box_key in view.boxes
                               if box_key[0].startswith(prefix) and view._visible_box(box_key)), None)
            if member_key is None:
                continue
            target_name, member_index, member_identity = member_key
            target_cell = variables[target_name]
            from dataclasses import replace
            address = replace(address, identity=member_identity,
                              index=member_index[1] if isinstance(member_index, tuple) else member_index,
                              row=member_index[0] if isinstance(member_index, tuple) else None)
        array = isinstance(target_cell['value'], list)
        index = address.index if array else None
        matrix = hasattr(target_cell['value'], 'columns')
        pointer_row = getattr(address, 'row', None)
        if matrix and pointer_row is not None:
            index = (pointer_row, address.index or 0)
        if not array and address.index not in (None, 0):
            continue
        key = ('address', cell['identity'])
        box_key = (target_name, index, address.identity)
        box = view.boxes.get(box_key)
        # A dormant rear element may be represented by the compact row stack.
        # Point at that stack until an actual access draws the element card.
        if box is None and matrix and isinstance(index, tuple):
            row, column = index
            if 0 <= row < len(target_cell['value']) and 0 <= column < target_cell['value'].columns:
                box_key = (target_name, row, address.identity)
                box = view.boxes.get(box_key)
        if array:
            lane = array_lanes.get(address.identity, 0)
            array_lanes[address.identity] = lane+1
            lane += blue_lanes.get((target_name, address.identity), 0)
            if box:
                rect = box.mapRectToScene(box.rect())
                point = QPointF(rect.left()+18+min(lane*28, rect.width()-40), rect.top()-4)
                destinations[key] = (point, name, lane, True, RED, False)
                targets[key] = box_key
            elif (target_name, address.identity) in view.array_anchors:
                point = view.array_anchors[target_name, address.identity] + QPointF(0, lane*22+view._draw_offset-view._array_offset())
                tail = (index[1] == target_cell['value'].columns if matrix and isinstance(index, tuple)
                        else index == len(target_cell['value']))
                note = '尾后，不可解引用' if tail else '目标未绘制'
                destinations[key] = (point, f'{name}（{note}）', 0, False, RED, False)
            sections[key] = 'array'
        elif box:
            lane = scalar_lanes.get(address.identity, 0)
            scalar_lanes[address.identity] = lane+1
            rect = box.mapRectToScene(box.rect())
            # A short horizontal marker points at the scalar from the canvas side.
            point = QPointF(rect.left()-3, rect.top()+10+min(lane*14, 24))
            destinations[key] = (point, name, lane, True, RED, True)
            sections[key], targets[key] = 'scalar', box_key
    return destinations, sections, targets
