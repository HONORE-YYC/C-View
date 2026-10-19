"""Resolve member-array index markers without evaluating user expressions."""
from pycparser import c_ast as ast
from .motion import declaration_key
from .pointers import Pointer


def member_index_bindings(program):
    scopes, bindings = [{}], []

    def selector(node):
        if isinstance(node, ast.UnaryOp) and node.op in ('++', '--', 'p++', 'p--'):
            node = node.expr
        if isinstance(node, ast.Constant) and node.type in ('int', 'long int', 'long long int'):
            from .runtime import integer_literal
            return ('constant', integer_literal(node.value))
        path = []
        while isinstance(node, ast.StructRef):
            path.append((node.type, node.field.name))
            node = node.name
        if not isinstance(node, ast.ID):
            return None
        decl = next((scope[node.name] for scope in reversed(scopes) if node.name in scope), None)
        return ('member', declaration_key(decl), tuple(reversed(path))) if decl is not None else None

    def visit(node):
        if node is None:
            return
        scoped = isinstance(node, (ast.Compound, ast.For))
        if scoped:
            scopes.append({})
        if isinstance(node, ast.Decl) and node.name:
            scopes[-1][node.name] = node
        if isinstance(node, ast.ArrayRef):
            current, axes = node, []
            while isinstance(current, ast.ArrayRef):
                axes.append(selector(current.subscript))
                current = current.name
            if isinstance(current, ast.StructRef):
                array = selector(current)
                axes = tuple(reversed(axes))
                if array is not None and all(axis is not None for axis in axes) and len(axes) <= 2:
                    binding = array, axes
                    if binding not in bindings:
                        bindings.append(binding)
        for _, child in node.children():
            visit(child)
        if scoped:
            scopes.pop()

    for node in program.globals:
        visit(node)
    for function in program.functions.values():
        scopes.append({})
        for param in function.params:
            visit(param)
        visit(function.node.body)
        scopes.pop()
    visit(program.main)
    return bindings


def member_index_markers(bindings, variables):
    by_declaration = {cell['declaration']: (name, cell) for name, cell in variables.items()}
    by_identity = {cell['identity']: (name, cell) for name, cell in variables.items()}

    def resolve(selector):
        if selector[0] == 'constant':
            return '', {'value': selector[1], 'identity': None}
        result = by_declaration.get(selector[1])
        if result is None:
            return None
        name, cell = result
        for access, field in selector[2]:
            if access == '->':
                address = cell['value']
                if not isinstance(address, Pointer) or address.index not in (None, 0):
                    return None
                result = by_identity.get(address.identity)
                if result is None:
                    return None
                name, cell = result
            name += '.' + field
            cell = variables.get(name)
            if cell is None:
                return None
        return name, cell

    markers = {}
    for array_selector, axes in bindings:
        array = resolve(array_selector)
        counters = [resolve(axis) for axis in axes]
        if array is None or any(item is None for item in counters):
            continue
        name, cell = array
        values = [item[1]['value'] for item in counters]
        if not isinstance(cell['value'], list) or not all(isinstance(value, int) for value in values):
            continue
        for dimension, (counter, state) in enumerate(counters):
            if not counter:
                continue
            index = values[0] if dimension == 0 else tuple(values)
            label = counter if dimension == 0 else counter+'[列]'
            markers[name, cell['identity'], label, state['identity']] = index
    return markers
