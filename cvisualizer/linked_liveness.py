"""Conservative backward AST liveness; no user expression is evaluated."""
from pycparser import c_ast as ast


class LinkedLiveness:
    def __init__(self, program):
        self.after = {}
        self.entries = {}
        self.summaries = {}
        self.program = program
        for name, spec in program.functions.items():
            self.summaries[name] = self.reads(spec.node.body)
        # Include transitive global reads of arbitrarily named callees.
        for _ in range(len(self.summaries) + 1):
            for name, spec in program.functions.items():
                self.summaries[name] |= self.reads(spec.node.body)
        live = self.block(program.main, set())
        for name, spec in program.functions.items():
            self.entries[name] = self.block(spec.node.body, set())
        for node in reversed(program.globals):
            live = self.block(node, live)

    def preserve(self, node, names):
        """An inner declaration must not kill a later use of an outer binding."""
        if node is None or not names:
            return
        if id(node) in self.after:
            self.after[id(node)] |= names
        for _, child in node.children():
            self.preserve(child, names)

    def reads(self, node):
        if node is None:
            return set()
        if isinstance(node, ast.ID):
            return {node.name}
        if isinstance(node, ast.StructRef):
            return self.reads(node.name)
        if isinstance(node, ast.Assignment):
            return self.reads(node.rvalue) | (set() if node.op == '=' and isinstance(node.lvalue, ast.ID) else self.reads(node.lvalue))
        if isinstance(node, ast.Decl):
            dimensions = set()
            declared = node.type
            while isinstance(declared, ast.ArrayDecl):
                dimensions |= self.reads(declared.dim)
                declared = declared.type
            return self.reads(node.init) | dimensions
        if isinstance(node, ast.FuncCall):
            return self.reads(node.args) | self.summaries.get(getattr(node.name, 'name', ''), set())
        return set().union(*(self.reads(child) for _, child in node.children()))

    def block(self, node, future, brk=None, cont=None):
        if node is None:
            return set(future)
        self.after[id(node)] = set(future)
        if isinstance(node, (ast.Compound, ast.DeclList)):
            children = (node.block_items if isinstance(node, ast.Compound) else node.decls) or []
            protected = set(future) & {child.name for child in children if isinstance(child, ast.Decl)} if isinstance(node, ast.Compound) else set()
            live = set(future)
            for child in reversed(children):
                live = self.block(child, live, brk, cont) | protected
                self.preserve(child, protected)
            return live
        if isinstance(node, ast.If):
            branches = self.block(node.iftrue, future, brk, cont) | self.block(node.iffalse, future, brk, cont)
            self.after[id(node.cond)] = branches
            return self.reads(node.cond) | branches
        if isinstance(node, (ast.For, ast.While)):
            live = set(future) | self.reads(node.cond)
            while True:
                update = self.block(node.next, live, future, live) if isinstance(node, ast.For) else live
                body = self.block(node.stmt, update, future, update)
                new = set(future) | self.reads(node.cond) | body
                if new == live:
                    break
                live |= new
            self.after[id(node.cond or node)] = set(future) | body
            if isinstance(node, ast.For):
                declarations = node.init.decls if isinstance(node.init, ast.DeclList) else []
                protected = set(future) & {decl.name for decl in declarations}
                entry = self.block(node.init, live, brk, cont) | protected
                self.preserve(node, protected)
                return entry
            return live
        if isinstance(node, ast.Break):
            return set(brk or ())
        if isinstance(node, ast.Continue):
            return set(cont or ())
        if isinstance(node, ast.Return):
            self.after[id(node)] = set()
            return self.reads(node.expr)
        killed = set()
        if isinstance(node, ast.Decl):
            killed.add(node.name)
        if isinstance(node, ast.Assignment) and node.op == '=' and isinstance(node.lvalue, ast.ID):
            killed.add(node.lvalue.name)
        return (set(future) - killed) | self.reads(node)
