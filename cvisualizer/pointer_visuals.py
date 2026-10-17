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
        array = isinstance(target_cell['value'], list)
        index = address.index if array else None
        if not array and address.index not in (None, 0):
            continue
        key = ('address', cell['identity'])
        box_key = (target_name, index, address.identity)
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
                note = '尾后，不可解引用' if index == len(target_cell['value']) else '目标未绘制'
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
