"""Separate the const pointer itself from the const object it points to."""
from pycparser import c_ast as ast


def qualifiers(node):
    if isinstance(node, ast.ArrayDecl):
        base = node.type
        while isinstance(base, ast.ArrayDecl):
            base = base.type
        return 'const' in node.dim_quals, 'const' in base.quals
    if isinstance(node, ast.PtrDecl):
        return 'const' in node.quals, 'const' in node.type.quals
    return 'const' in node.quals, False
