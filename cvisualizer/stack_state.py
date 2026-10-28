"""Recognized pointer-based stacks and presentation-only last-pop records."""
from copy import deepcopy
from pycparser import c_ast as ast
from .pointers import Pointer
from .arrays import Matrix


def stack_types(program):
    result = {}
    for name, spec in program.structs.items():
        fields = spec.fields or []
        if len(fields) != 3:
            continue
        pointers = fields[:2]
        if not all(isinstance(field.type, ast.PtrDecl) and isinstance(field.type.type, ast.TypeDecl)
                   and isinstance(field.type.type.type, ast.IdentifierType) for field in pointers):
            continue
        if program._scalar_type(pointers[0].type) != program._scalar_type(pointers[1].type):
            continue
        size = fields[2]
        if not isinstance(size.type, ast.TypeDecl) or not isinstance(size.type.type, ast.IdentifierType) or program._scalar_type(size.type) != 'int':
            continue
        result[name] = dict(base=fields[0].name, top=fields[1].name, capacity=size.name)
    return result


def models(snapshot):
    by_identity = {cell['identity']: (name, cell) for name, cell in snapshot.items()}
    result = {}
    for name, cell in snapshot.items():
        fields = cell.get('stack_node')
        if not fields:
            continue
        model = dict(name=name, fields=fields, base_name=name+'.'+fields['base'],
                     top_name=name+'.'+fields['top'], capacity_name=name+'.'+fields['capacity'],
                     storage_name='', storage_identity=None, values=[], base=0, top=0,
                     capacity=0, count=0, valid=False, error='等待栈初始化',
                     popped=deepcopy(cell.get('stack_popped')))
        result[cell['identity']] = model
        base = snapshot.get(model['base_name'], {}).get('value')
        top = snapshot.get(model['top_name'], {}).get('value')
        capacity = snapshot.get(model['capacity_name'], {}).get('value')
        if not isinstance(base, Pointer) or base.identity is None:
            continue
        storage = by_identity.get(base.identity)
        if not storage:
            model['error'] = '栈存储空间已释放或不可访问'
            continue
        storage_name, storage_cell = storage
        values = storage_cell['value']
        if not isinstance(values, list) or isinstance(values, Matrix) or base.row is not None:
            model['error'] = '栈需要一维数组存储空间'
            continue
        model.update(storage_name=storage_name, storage_identity=base.identity, values=values)
        if model['popped'] and model['popped'].get('storage_identity', base.identity) != base.identity:
            model['popped'] = None
        if not isinstance(top, Pointer):
            continue
        first, end = base.index or 0, top.index or 0
        if top.identity != base.identity or top.base_type != base.base_type or top.row is not None:
            model['error'] = '栈顶和栈底必须指向同一数组'
            continue
        if not isinstance(capacity, int):
            continue
        if capacity < 0 or not 0 <= first <= end <= first+capacity <= len(values):
            model['error'] = '栈指针或容量超出存储范围'
            continue
        model.update(base=first, top=end, capacity=capacity, count=end-first, valid=True, error='')
    return result


def observe_write(rt, ref, before, after):
    """Called after pointer writes; never changes the user's storage or reads."""
    if not isinstance(before, Pointer) or not isinstance(after, Pointer):
        return
    if before.identity is None or before.identity != after.identity or before.row is not None or after.row is not None:
        return
    old_index, new_index = before.index or 0, after.index or 0
    if new_index >= old_index:
        return
    from .struct_runtime import StructValue, flattened
    roots = list(rt.visible_cells().values())
    for scopes in rt.callers:
        for scope in scopes:
            roots.extend(flattened(scope).values())
    seen = set()
    for cell in roots:
        fields = rt.program.stack_types.get(cell.type)
        if not fields or not isinstance(cell.value, StructValue) or cell.identity in seen:
            continue
        seen.add(cell.identity)
        members = cell.value.fields
        if members[fields['top']].identity != ref[1].identity:
            continue
        base = members[fields['base']].value
        storage = rt.find_identity(after.identity)
        if not isinstance(base, Pointer) or base.identity != after.identity or not storage:
            continue
        values = storage[1].value
        if isinstance(values, list) and not isinstance(values, Matrix) and (base.index or 0) <= new_index < old_index <= len(values):
            previous = rt.stack_popped.get(cell.identity, {})
            rt.stack_popped[cell.identity] = dict(value=deepcopy(values[new_index]), index=new_index,
                                                 serial=previous.get('serial', 0)+1,
                                                 storage_identity=after.identity)
