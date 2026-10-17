"""Static lexical bindings for array index indicators; no expression execution."""
from pycparser import c_ast as ast


def declaration_key(node):
    return node.name, node.coord.line, node.coord.column


def index_bindings(program):
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
        if isinstance(node, ast.ArrayRef) and isinstance(node.name, ast.ID):
            index = node.subscript
            if isinstance(index, ast.UnaryOp) and index.op in ('++', '--', 'p++', 'p--'):
                index = index.expr
            if isinstance(index, ast.ID):
                array, counter = lookup(node.name.name), lookup(index.name)
                if (array is not None and counter is not None
                        and isinstance(array.type, ast.ArrayDecl)
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


def index_markers(bindings, variables):
    by_declaration = {cell['declaration']: (name, cell) for name, cell in variables.items()}
    markers = {}
    for array_key, counter_key in bindings:
        if array_key not in by_declaration or counter_key not in by_declaration:
            continue
        array, a = by_declaration[array_key]
        counter, c = by_declaration[counter_key]
        if isinstance(a['value'], list) and isinstance(c['value'], int):
            markers[array, a['identity'], counter, c['identity']] = c['value']
    return markers
