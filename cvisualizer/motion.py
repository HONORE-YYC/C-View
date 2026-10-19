"""Static lexical bindings for array index indicators; no expression execution."""
from pycparser import c_ast as ast
from .pointers import Pointer


def declaration_key(node):
    return node.name, node.coord.line, node.coord.column


def pointer_slots(program):
    """Reserve marker space before pointers enter scope, keeping arrays stable."""
    count = 0
    class Counter(ast.NodeVisitor):
        def visit_Decl(self, node):
            nonlocal count
            if isinstance(node.type, ast.PtrDecl):
                count += 1
            self.generic_visit(node)
    Counter().visit(program.tree)
    return count + sum(isinstance(p.type, ast.ArrayDecl) for f in program.functions.values() for p in f.params)


def indirect_index_slots(program, bindings):
    indirect = {declaration_key(p) for f in program.functions.values() for p in f.params
                if isinstance(p.type, (ast.ArrayDecl, ast.PtrDecl))}
    class Collector(ast.NodeVisitor):
        def visit_Decl(self, node):
            if isinstance(node.type, ast.PtrDecl):
                indirect.add(declaration_key(node))
            self.generic_visit(node)
    Collector().visit(program.tree)
    return max((sum(a == key for a, _ in bindings) for key in indirect), default=0)


def index_bindings(program, matrices=False):
    scopes, bindings = [{}], []

    def lookup(name):
        return next((scope[name] for scope in reversed(scopes) if name in scope), None)

    def visit(node):
        if node is None:
            return
        scoped = isinstance(node, (ast.Compound, ast.For))
        if scoped:
            scopes.append({})
        if isinstance(node, ast.Decl):
            scopes[-1][node.name] = node
        if (matrices and isinstance(node, ast.ArrayRef) and isinstance(node.name, ast.ArrayRef)
                and isinstance(node.name.name, ast.ID)):
            column = node.subscript
            if isinstance(column, ast.UnaryOp) and column.op in ('++', '--', 'p++', 'p--'):
                column = column.expr
            row = node.name.subscript
            if isinstance(row, ast.UnaryOp) and row.op in ('++', '--', 'p++', 'p--'):
                row = row.expr
            array = lookup(node.name.name.name)
            counter = lookup(column.name) if isinstance(column, ast.ID) else None
            selector = None
            if isinstance(row, ast.ID) and lookup(row.name) is not None:
                selector = ('counter', declaration_key(lookup(row.name)))
            elif isinstance(row, ast.Constant) and row.type in ('int', 'long int', 'long long int'):
                literal = row.value.rstrip('lL')
                base = 16 if literal.lower().startswith('0x') else 8 if len(literal) > 1 and literal.startswith('0') else 10
                selector = ('constant', int(literal, base))
            if array is not None and counter is not None and selector is not None:
                binding = declaration_key(array), selector, declaration_key(counter)
                if binding not in bindings:
                    bindings.append(binding)
        if not matrices and isinstance(node, ast.ArrayRef) and isinstance(node.name, ast.ID):
            index = node.subscript
            if isinstance(index, ast.UnaryOp) and index.op in ('++', '--', 'p++', 'p--'):
                index = index.expr
            if isinstance(index, ast.ID):
                array, counter = lookup(node.name.name), lookup(index.name)
                if (array is not None and counter is not None
                        and isinstance(array.type, (ast.ArrayDecl, ast.PtrDecl))
                        and isinstance(counter.type, ast.TypeDecl)):
                    pair = declaration_key(array), declaration_key(counter)
                    if pair not in bindings:
                        bindings.append(pair)
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


def index_markers(bindings, variables, matrix_bindings=()):
    by_declaration = {cell['declaration']: (name, cell) for name, cell in variables.items()}
    by_identity = {cell['identity']: (name, cell) for name, cell in variables.items()}
    markers = {}
    for array_key, counter_key in bindings:
        if array_key not in by_declaration or counter_key not in by_declaration:
            continue
        array, a = by_declaration[array_key]
        counter, c = by_declaration[counter_key]
        offset, pointer_row = 0, None
        if isinstance(a['value'], Pointer):
            pointer = a['value']
            target = by_identity.get(pointer.identity)
            if not target:
                continue
            array, a = target
            offset = pointer.index or 0
            pointer_row = pointer.row
        if isinstance(a['value'], list) and isinstance(c['value'], int):
            index = c['value'] + offset
            if hasattr(a['value'], 'columns') and pointer_row is not None:
                index = (pointer_row, index)
            markers[array, a['identity'], counter, c['identity']] = index
    for array_key, selector, counter_key in matrix_bindings:
        if array_key not in by_declaration or counter_key not in by_declaration:
            continue
        array, a = by_declaration[array_key]
        counter, c = by_declaration[counter_key]
        offset = 0
        if isinstance(a['value'], Pointer):
            pointer = a['value']
            target = by_identity.get(pointer.identity)
            if target is None or pointer.row is not None:
                continue
            array, a = target
            offset = pointer.index or 0
        if selector[0] == 'counter':
            row_cell = by_declaration.get(selector[1])
            row = row_cell[1]['value'] if row_cell else None
        else:
            row = selector[1]
        if hasattr(a['value'], 'columns') and isinstance(row, int) and isinstance(c['value'], int):
            markers[array, a['identity'], counter+'[列]', c['identity']] = (row+offset, c['value'])
    return markers
