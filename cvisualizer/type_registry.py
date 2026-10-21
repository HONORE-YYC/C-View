"""Expand lexical aliases and give structure tags stable internal identities."""
from copy import deepcopy
from dataclasses import dataclass
from .linked_language import SourceGenerator
from pycparser import c_ast as ast, c_generator


@dataclass
class StructSpec:
    name: str
    fields: list


class TypeRegistry:
    def __init__(self, program):
        self.program = program
        self.aliases = [{}]
        self.tags = [{}]
        self.structs = {}
        self.names = []
        self.counter = 0
        self.original = {}
        self.struct_nodes = {}
        self.generator = SourceGenerator(program)

    def lookup(self, scopes, name):
        return next((scope[name] for scope in reversed(scopes) if name in scope), None)

    def push(self):
        self.aliases.append({})
        self.tags.append({})

    def pop(self):
        self.aliases.pop()
        self.tags.pop()

    def normalize(self, tree):
        pending = [(tree, 0)]
        while pending:
            node, depth = pending.pop()
            if depth > 100:
                self.program.fail(node, '表达式或代码块嵌套过深（最多 100 层）')
            pending.extend((child, depth + 1) for _, child in node.children())
        self.remember(tree)
        tree.ext = [result for n in tree.ext if (result := self.walk(n)) is not None]
        return self

    def remember(self, node):
        if node is None:
            return
        if isinstance(node, (ast.Decl, ast.Typedef, ast.Typename, ast.Cast)):
            self.original[id(node)] = self.generator.visit(node)
        for _, child in node.children():
            self.remember(child)

    def walk(self, node):
        if node is None:
            return None
        if isinstance(node, ast.UnaryOp) and node.op == 'sizeof' and isinstance(node.expr, ast.ID):
            coord = node.coord
            original = self.program.preprocessed.original(max(1, coord.line-self.program.offset), coord.column)
            key = self.lookup(self.tags, node.expr.name)
            if original in self.program.allocations and key is not None:
                node.expr = ast.Typename(None, [], None, ast.TypeDecl(None, [], None, ast.Struct(key, None, coord), coord), coord)
                # Already canonical: do not resolve this internal tag through lexical scope again.
                return node
        if isinstance(node, ast.Typedef):
            if node.name in self.aliases[-1]:
                self.program.fail(node, 'typedef 名称重复声明')
            normalized = self.type(node.type, node.name)
            capacity = normalized
            while isinstance(capacity, ast.ArrayDecl):
                if capacity.dim is not None and not self.program._constant_integer(capacity.dim):
                    self.program.fail(node, 'typedef 数组容量需要整数常量表达式')
                capacity = capacity.type
            if isinstance(normalized, ast.FuncDecl):
                self.program.fail(node, '暂不支持函数类型别名')
            self.aliases[-1][node.name] = normalized
            return None
        if isinstance(node, ast.FuncDef):
            # A definition's parameter tag scope also contains its outer body.
            # Prototype FuncDecl normalization below still discards that scope.
            node.decl.type.type = self.type(node.decl.type.type)
            self.complete_object(node.decl.type.type, node.decl)
            self.push()
            if node.decl.type.args:
                for param in node.decl.type.args.params:
                    if isinstance(param, (ast.Decl, ast.Typename)):
                        self.walk(param)
                        self.complete_object(param.type, param)
            items = []
            for child in node.body.block_items or []:
                result = self.walk(child)
                items.append(result if result is not None else ast.EmptyStatement(coord=child.coord))
            node.body.block_items = items
            self.pop()
            return node
        if isinstance(node, ast.Compound):
            self.push()
            items = []
            for child in node.block_items or []:
                result = self.walk(child)
                items.append(result if result is not None else ast.EmptyStatement(coord=child.coord))
            node.block_items = items
            self.pop()
            return node
        if isinstance(node, ast.For):
            self.push()
            for attr in ('init', 'cond', 'next', 'stmt'):
                setattr(node, attr, self.walk(getattr(node, attr)))
            self.pop()
            return node
        if isinstance(node, (ast.Decl, ast.Typename)):
            if isinstance(node, ast.Decl) and node.bitsize:
                self.program.fail(node, '暂不支持结构体位域')
            node.type = self.type(node.type, tag_only=isinstance(node, ast.Decl) and node.name is None)
            if isinstance(node, ast.Decl) and node.name is not None:
                self.complete_object(node.type, node)
            self.walk(getattr(node, 'init', None))
            return node
        for attr in node.__slots__:
            if attr in ('coord', '__weakref__'):
                continue
            value = getattr(node, attr, None)
            if isinstance(value, ast.Node):
                setattr(node, attr, self.walk(value))
            elif isinstance(value, list):
                setattr(node, attr, [self.walk(x) if isinstance(x, ast.Node) else x for x in value])
        return node

    def type(self, node, display=None, tag_only=False):
        if isinstance(node, ast.TypeDecl):
            if isinstance(node.type, ast.IdentifierType) and len(node.type.names) == 1:
                alias = self.lookup(self.aliases, node.type.names[0])
                if alias is not None:
                    result = deepcopy(alias)
                    target = result
                    while isinstance(target, ast.ArrayDecl):
                        target = target.type
                    target.quals = list(dict.fromkeys(target.quals + node.quals))
                    leaf = result
                    while hasattr(leaf, 'type') and not isinstance(leaf, ast.TypeDecl):
                        leaf = leaf.type
                    leaf.declname = node.declname
                    return result
            node.type = self.type(node.type, display)
            return node
        if isinstance(node, ast.Union):
            self.program.fail(node, '暂不支持 union 联合体')
        if isinstance(node, ast.Struct):
            if id(node) in self.struct_nodes:
                return ast.Struct(self.struct_nodes[id(node)][1], None, node.coord)
            tag = node.name
            key = self.tags[-1].get(tag) if tag and (node.decls is not None or tag_only) else self.lookup(self.tags, tag)
            if key is None:
                self.counter += 1
                key = tag if tag and not any(k == 'struct ' + tag for k in self.structs) else (tag or 'anonymous') + '__' + str(self.counter)
                if tag:
                    self.tags[-1][tag] = key
                self.structs['struct ' + key] = StructSpec(tag or display or 'anonymous', None)
            self.struct_nodes[id(node)] = (node, key)
            spec = self.structs['struct ' + key]
            if node.decls is not None:
                if spec.fields is not None:
                    self.program.fail(node, '结构体重复定义')
                fields = []
                seen = set()
                for field in node.decls:
                    if not field.name or field.name in seen:
                        self.program.fail(field, '结构体字段需要唯一名称')
                    seen.add(field.name)
                    if field.bitsize:
                        self.program.fail(field, '暂不支持结构体位域')
                    field.type = self.type(field.type)
                    self.complete(field.type, field)
                    fields.append(field)
                spec.fields = fields
                self.names.append(spec.name)
            return ast.Struct(key, None, node.coord)
        if isinstance(node, ast.FuncDecl):
            node.type = self.type(node.type)
            self.push()
            if node.args:
                for param in node.args.params:
                    self.walk(param)
            self.pop()
            return node
        if isinstance(node, (ast.PtrDecl, ast.ArrayDecl)):
            if isinstance(node, ast.PtrDecl) and not isinstance(node.type, ast.TypeDecl):
                self.program.fail(node, '仅支持单级指针，不支持函数指针或数组指针')
            node.type = self.type(node.type, display)
            return node
        return node

    def complete(self, node, decl):
        if isinstance(node, ast.PtrDecl):
            return
        if isinstance(node, ast.ArrayDecl):
            if node.dim is None:
                self.program.fail(decl, '结构体字段不支持柔性数组')
            if not self.program._constant_integer(node.dim):
                self.program.fail(decl, '结构体数组成员容量需要整数常量表达式')
            return self.complete(node.type, decl)
        if isinstance(node, ast.TypeDecl) and isinstance(node.type, ast.Struct):
            spec = self.structs['struct ' + node.type.name]
            if spec.fields is None:
                self.program.fail(decl, '结构体不完整或包含自身的值成员')

    def complete_object(self, node, decl):
        while isinstance(node, ast.ArrayDecl):
            node = node.type
        if isinstance(node, ast.TypeDecl) and isinstance(node.type, ast.Struct):
            if self.structs['struct ' + node.type.name].fields is None:
                self.program.fail(decl, '不能创建不完整结构体')
