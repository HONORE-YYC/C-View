"""Bounded stacked row cards and independently exposed matrix elements."""
from PySide6.QtCore import QPointF
from .array_folding import row_summary


def is_matrix(value):
    return isinstance(value, list) and hasattr(value, 'columns')


def indexed(value, index):
    if not isinstance(value, list):
        return None
    try:
        if isinstance(index, tuple):
            row, column = index
            return value[row][column] if 0 <= row < len(value) and 0 <= column < value.columns else None
        return value[index] if 0 <= index < len(value) else None
    except (IndexError, TypeError, AttributeError):
        return None


def index_label(name, index):
    return name + ''.join(f'[{part}]' for part in (index if isinstance(index, tuple) else (index,))) if index is not None else name


def active_columns(name, row, cell, event):
    if not event or event.variables.get(name, {}).get('identity') != cell['identity']:
        return []
    signature = (name, cell['identity'], id(event.reads), len(event.reads),
                 id(event.writes), len(event.writes), id(event.transfers), len(event.transfers))
    cached = getattr(event, '_matrix_columns', {})
    if signature not in cached:
        columns = {}
        whole = (name, None) in event.writes
        indices = [] if whole else list(event.writes)
        if not whole:
            indices.extend(target[:2] for source, target in event.transfers)
            indices.extend(source[:2] for source, target in event.transfers)
        indices.extend(event.reads)
        for n, index in indices:
            if n == name and isinstance(index, tuple) and 0 <= index[1] < cell['value'].columns:
                columns.setdefault(index[0], {}).setdefault(index[1], None)
        cached[signature] = {r: list(values) for r, values in columns.items()}
        event._matrix_columns = cached
    return cached[signature].get(row, [])



def draw_row(view, name, row, cell, event, x, y, width):
    matrix = cell['value']
    count = matrix.columns if matrix.columns <= 4 else 3
    key = name, row, cell['identity']
    rear = []
    for slot in reversed(range(count)):
        read, written = view.activity(name, (row, slot), cell, event)
        card = view.box('', matrix[row][slot], x+5*(slot+1), y-7*(slot+1), width, read, written, owner=cell.get('struct_owner'))
        card.value_label.setVisible(False)
        if hasattr(card, 'owner_label'):
            card.owner_label.setVisible(False)
        card.setZValue(-2-slot)
        card.setData(0, None)
        card.setToolTip(f'{name}[{row}] · {matrix.columns} 列')
        rear.append(card)
    view.matrix_stacks[key] = rear
    initialized = row_summary(matrix[row]) is not None
    read, written = view.activity(name, row, cell, event)
    front = view.box(index_label(name, row), 0 if initialized else None, x, y, width, read, written, owner=cell.get('struct_owner'))
    front.value_label.setPlainText(index_label(name, row))
    front.setToolTip(f'{name}[{row}] · {matrix.columns} 列')
    front.value_label.setToolTip(front.toolTip())
    front.setZValue(1)
    front.value_label.setZValue(2)
    view.boxes[key] = front
    if matrix.columns >= 5:
        view.label(f'{matrix.columns} 列', x+5, y+45, 8, '#64748b')
    columns = active_columns(name, row, cell, event)
    if len(columns) > 4:
        note = view.label(f'\u53e6\u6709 {len(columns)-4} \u4e2a\u8bbf\u95ee', x+5, y+252, 8, '#64748b')
        note.setToolTip(f'{name}[{row}] \u00b7 \u5171 {len(columns)} \u4e2a\u5143\u7d20\u88ab\u8bbf\u95ee\uff1b\u663e\u793a 4 \u4e2a')
    for lane, column in enumerate(sorted(columns[:4])):
        read, written = view.activity(name, (row, column), cell, event)
        # The actual column label remains precise even when the representative stack is compressed.
        slot = min(column, count-1)
        card = view.box(index_label(name, (row, column)), matrix[row][column],
                        x+5*(slot+1), y-7*(slot+1), width, read, written, owner=cell.get('struct_owner'))
        card.value_label.setParentItem(card)
        card.matrix_origin = QPointF(card.pos())
        card.matrix_delta = QPointF(-5*(slot+1), 7*(slot+1)+64+lane*48)
        card.setZValue(-.5)
        card.value_label.setVisible(False)
        if hasattr(card, 'owner_label'):
            card.owner_label.setVisible(False)
        view.matrix_reveals.append(card)
        view.boxes[name, (row, column), cell['identity']] = card


def exposed_rect(item):
    rect = item.mapRectToScene(item.rect())
    if hasattr(item, 'matrix_delta'):
        rect.translate(item.matrix_delta)
    return rect
