"""Bindings map ordinary C variables to educational views without changing code."""
from dataclasses import dataclass, field
from .arrays import Indices, OrderedValues


KINDS = {'array': '数组', 'list': '顺序表', 'stack': '栈', 'queue': '循环队列'}


@dataclass
class Binding:
    array: str
    kind: str = 'array'
    length: str = ''
    top: str = ''
    front: str = ''
    rear: str = ''


@dataclass
class Structure:
    name: str
    kind: str
    values: list
    active: list = field(default_factory=list)
    logical: list = field(default_factory=list)
    markers: dict = field(default_factory=dict)
    note: str = ''
    error: str = ''


def describe(binding, variables):
    raw = variables.get(binding.array, {}).get('value')
    model = Structure(binding.array, binding.kind, raw if isinstance(raw, list) else [])
    if not isinstance(raw, list):
        model.error = f'等待数组 {binding.array} 定义，或该变量已离开作用域'
        return model
    size = len(raw)
    model.active = Indices(size)

    def scalar(name):
        value = variables.get(name, {}).get('value')
        if not isinstance(value, int):
            raise ValueError(f'状态变量 {name or "（未设置）"} 尚未定义、未初始化或不是 int')
        return value

    try:
        if binding.kind == 'list':
            length = scalar(binding.length)
            if not 0 <= length <= size:
                raise ValueError(f'长度 {binding.length}={length} 超出 0–{size}')
            model.active = Indices(length)
            model.note = f'length = {length}  /  capacity = {size}'
        elif binding.kind == 'stack':
            top = scalar(binding.top)
            if not -1 <= top < size:
                raise ValueError(f'栈顶 {binding.top}={top} 超出 -1–{size-1}')
            model.active = Indices(top + 1)
            if top >= 0:
                model.markers = {top: ['top']}
            model.note = f'top = {top}  ·  ' + ('空栈' if top == -1 else f'{top+1} 个元素')
        elif binding.kind == 'queue':
            front, rear = scalar(binding.front), scalar(binding.rear)
            if not 0 <= front < size or not 0 <= rear < size:
                raise ValueError(f'front、rear 必须处于 0–{size-1}')
            count = (rear - front + size) % size
            model.active = Indices(count, front, size)
            model.markers.setdefault(front, []).append('front')
            model.markers.setdefault(rear, []).append('rear')
            state = '空队列' if count == 0 else ('队列已满' if count == size-1 else f'{count} 个元素')
            model.note = f'front = {front}  ·  rear = {rear}  ·  {state}  ·  预留一个空位'
        elif binding.kind != 'array':
            raise ValueError(f'未知显示类型 {binding.kind}')
        model.logical = OrderedValues(raw, model.active)
    except ValueError as error:
        model.error = str(error)
        model.kind = 'array'
        model.active = Indices(size)
    return model
