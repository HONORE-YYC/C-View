"""Parse the documented C subset while retaining original source locations."""
from dataclasses import dataclass
import re

from pycparser import c_ast as ast, c_parser, c_generator
from .errors import CError
from .preprocessor import Preprocessor
from .numeric import type_name
from .type_registry import TypeRegistry
from .math_library import FUNCTIONS as MATH_FUNCTIONS
from .qualifiers import qualifiers


@dataclass(frozen=True)
class Location:
    line: int
    column: int
    text: str
    kind: str = 'statement'


@dataclass(frozen=True)
class Function:
    name: str
    node: ast.FuncDef
    params: list[ast.Decl]
    return_type: str


_BUILTINS = {'printf', 'scanf', 'abs', 'labs', 'rand', 'srand', 'atoi', 'atol', 'atof',
             'strlen', 'strcpy', 'strncpy', 'strcat', 'strncat', 'strcmp', 'strncmp',
             'strchr', 'strrchr', 'strstr'}
_BUILTINS |= set(MATH_FUNCTIONS)
_TOKENS = re.compile(r'"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'|//[^\n]*|/\*[\s\S]*?\*/')
_GENERATOR = c_generator.CGenerator()


class Program:
    def __init__(self, source):
        if len(source) > 64000:
            raise CError('代码超过 64000 字符，请缩小教学示例')
        self.source = source
        self.preprocessed = Preprocessor().process(source)
        cleaned = self.preprocessed.text
        # A string such as printf("main(") is not a function definition.
        masked = _TOKENS.sub(lambda m: ' ' * len(m[0]), cleaned)
        self.offset = 0 if re.search(r'\bmain\s*\(', masked) else 1
        parsed_source = cleaned if not self.offset else 'int main(void) {\n' + cleaned + '\n}'
        try:
            self.tree = c_parser.CParser().parse(parsed_source)
        except (c_parser.ParseError, RecursionError) as exc:
            match = re.search(r':(\d+):(\d+):', str(exc))
            line, column = self.preprocessed.original(max(1, int(match[1])-self.offset), int(match[2])) if match else (0, 0)
            detail = str(exc).split(': ', 1)[-1]
            raise CError(f'C 语法错误：{detail}', line, column) from None
        self.type_registry = TypeRegistry(self).normalize(self.tree)
        self.structs = self.type_registry.structs
        self.structure_names = self.type_registry.names
        self.globals = []
        self.main = None
        self.functions = {}
        declarations = {}
        definitions = {}
        for node in self.tree.ext:
            definition = isinstance(node, ast.FuncDef)
            decl = node.decl if definition else node
            if isinstance(decl, ast.Decl) and isinstance(decl.type, ast.FuncDecl):
                name = decl.name
                if name in _BUILTINS:
                    self.fail(decl, f'{name} 是内置函数保留名称')
                if definition and name in definitions:
                    self.fail(decl, f'函数 {name} 重复定义')
                if definition and node.param_decls:
                    self.fail(decl, '函数参数请使用现代 C 声明语法')
                params, return_type, signature = self._signature(decl, definition)
                if name in declarations and declarations[name][0] != signature:
                    self.fail(decl, f'函数 {name} 的声明与定义不兼容')
                declarations[name] = (signature, decl)
                if definition:
                    definitions[name] = Function(name, node, params, return_type)
                    if name == 'main':
                        self.main = node.body
                    else:
                        self.functions[name] = definitions[name]
            elif isinstance(node, ast.Decl):
                self.globals.append(node)
            else:
                self.fail(node, '暂不支持此顶层声明')
        if self.main is None:
            raise CError('缺少 int main(void) 函数')
        for name, (_, decl) in declarations.items():
            if name not in definitions:
                self.fail(decl, f'函数 {name} 已声明但没有定义')
        for node in self.globals:
            if node.name in definitions:
                self.fail(node, f'{node.name} 与函数名称重复')
            self._check(node, global_scope=True)
        self._calls = {name: set() for name in definitions}
        for function in definitions.values():
            for param in function.params:
                if param.name in definitions or param.name in _BUILTINS:
                    self.fail(param, f'参数名称 {param.name} 与函数名称重复')
            self._check(function.node.body, function=function)
        self._field_ids = {id(field) for spec in self.structs.values() for field in spec.fields or []}
        for spec in self.structs.values():
            for field in spec.fields or []:
                self._check(field, global_scope=True)
        self._check_recursion(definitions)

    def _signature(self, decl, definition):
        if set(decl.quals) - {'const', 'volatile'} or decl.storage or decl.funcspec:
            self.fail(decl, '函数暂不支持类型修饰符或存储修饰符')
        return_type = self._scalar_type(decl.type.type, allow_void=True)
        params = decl.type.args.params if decl.type.args else []
        if (len(params) == 1 and isinstance(params[0], ast.Typename)
                and isinstance(params[0].type, ast.TypeDecl)
                and isinstance(params[0].type.type, ast.IdentifierType)
                and params[0].type.type.names == ['void']):
            params = []
        if decl.name == 'main':
            if return_type != 'int':
                self.fail(decl, 'main 必须返回 int')
            if params:
                self.fail(decl, 'main 暂不支持参数，请使用 int main(void)')
        types = []
        names = set()
        for param in params:
            if not isinstance(param, (ast.Decl, ast.Typename)):
                self.fail(param, '函数参数仅支持命名的数值或一维数组参数')
            if definition and (not isinstance(param, ast.Decl) or not param.name):
                self.fail(param, '函数定义中的参数必须有名称')
            if param.name and param.name in names:
                self.fail(param, f'参数 {param.name} 重复声明')
            names.add(param.name)
            if (isinstance(param, ast.Decl)
                               and (param.storage or param.funcspec or param.init or param.bitsize)):
                self.fail(param, '函数参数暂不支持修饰符或初始化')
            type_node = param.type
            array = isinstance(type_node, ast.ArrayDecl)
            columns = None
            if array:
                dimensions = []
                while isinstance(type_node, ast.ArrayDecl):
                    dimensions.append(type_node)
                    if set(type_node.dim_quals) - {'const', 'volatile', 'restrict'}:
                        self.fail(param, '不支持数组参数方括号修饰符')
                    if type_node.dim is not None:
                        self._check(type_node.dim)
                    type_node = type_node.type
                if len(dimensions) > 2 or not isinstance(type_node, ast.TypeDecl):
                    self.fail(param, '数组参数最多支持二维')
                if len(dimensions) == 2:
                    if dimensions[1].dim is None:
                        self.fail(param, '二维数组参数需要列容量')
                    columns = _GENERATOR.visit(dimensions[1].dim)
            pointer = isinstance(type_node, ast.PtrDecl)
            parameter_type = self._scalar_type(type_node)
            types.append((parameter_type.rstrip('*'), array or pointer, qualifiers(param.type)[1], columns))
        return params, return_type, (return_type, qualifiers(decl.type.type)[1], tuple(types))

    def _scalar_type(self, node, allow_void=False):
        if isinstance(node, ast.PtrDecl):
            if set(node.quals) - {'const', 'volatile', 'restrict'} or not isinstance(node.type, ast.TypeDecl):
                self.fail(node, '仅支持单级数值指针，不支持指针修饰符或多级指针')
            return self._scalar_type(node.type) + '*'
        if isinstance(node, ast.TypeDecl) and isinstance(node.type, ast.Struct):
            if set(node.quals) - {'const', 'volatile'}:
                self.fail(node, '暂不支持类型修饰符')
            return 'struct ' + node.type.name
        supported = (['int'], ['float'], ['double'], ['long'], ['long', 'int'], ['int', 'long'], ['char'], ['_Bool'], ['long', 'long'], ['long', 'long', 'int'])
        if allow_void:
            supported += (['void'],)
        if (not isinstance(node, ast.TypeDecl) or set(node.quals) - {'const', 'volatile'}
                or not isinstance(node.type, ast.IdentifierType)
                or node.type.names not in supported):
            self.fail(node, '函数类型仅支持 int、long、float、double、char；void 仅可用于返回类型或空参数列表')
        return type_name(node.type.names)

    def _check_recursion(self, definitions):
        # Iterative DFS also handles long acyclic chains without Python recursion.
        complete = set()
        for root in definitions:
            if root in complete:
                continue
            active = {root}
            stack = [(root, iter(self._calls[root]))]
            while stack:
                name, children = stack[-1]
                child = next(children, None)
                if child is None:
                    complete.add(name)
                    active.remove(name)
                    stack.pop()
                elif child in active:
                    self.fail(definitions[name].node, f'暂不支持递归调用（包括相互递归）：{name} → {child}')
                elif child not in complete:
                    active.add(child)
                    stack.append((child, iter(self._calls[child])))

    def location(self, node, kind='statement'):
        coord = node.coord
        line, column = self.preprocessed.original(max(1, coord.line-self.offset), coord.column) if coord else (1, 1)
        text = self.type_registry.original.get(id(node))
        return Location(line, column, text if text is not None else _GENERATOR.visit(node), kind)

    def fail(self, node, message):
        # Reporting invalid/deep ASTs must not regenerate the invalid subtree.
        coord = node.coord
        line, column = self.preprocessed.original(max(1, coord.line-self.offset), coord.column) if coord else (1, 1)
        raise CError(message, line, column)

    def _check(self, node, loops=0, depth=0, function=None, global_scope=False):
        if node is None:
            return
        if depth > 100:
            self.fail(node, '表达式或代码块嵌套过深（最多 100 层）')
        allowed = (ast.Compound, ast.Decl, ast.TypeDecl, ast.IdentifierType, ast.ArrayDecl, ast.PtrDecl,
                   ast.InitList, ast.Constant, ast.ID, ast.Assignment, ast.BinaryOp,
                   ast.UnaryOp, ast.ArrayRef, ast.Struct, ast.StructRef, ast.If, ast.For, ast.While, ast.Break,
                   ast.Continue, ast.Return, ast.EmptyStatement, ast.DeclList,
                   ast.FuncCall, ast.ExprList, ast.Cast, ast.Typename)
        if not isinstance(node, allowed):
            self.fail(node, f'第一版暂不支持 {type(node).__name__}')
        if isinstance(node, ast.IdentifierType) and node.names not in (['int'], ['long'], ['long', 'int'], ['int', 'long'], ['char'], ['float'], ['double'], ['_Bool'], ['long', 'long'], ['long', 'long', 'int']):
            self.fail(node, '仅支持 int、long、char、float、double 类型')
        if isinstance(node, ast.Struct):
            return
        if isinstance(node, ast.StructRef):
            self._check(node.name, loops, depth + 1, function, global_scope)
            return
        if isinstance(node, ast.Decl) and node.name is None:
            return
        if isinstance(node, ast.Decl):
            self.type_registry.complete_object(node.type, node)
        if isinstance(node, ast.Cast):
            self._scalar_type(node.to_type.type)
        if isinstance(node, ast.PtrDecl):
            self._scalar_type(node)
        if isinstance(node, ast.TypeDecl) and set(node.quals) - {'const', 'volatile'}:
            self.fail(node, '暂不支持类型修饰符')
        if isinstance(node, ast.Decl) and (node.storage or node.funcspec or node.bitsize):
            self.fail(node, '暂不支持类型修饰符、存储修饰符或位域')
        if isinstance(node, ast.Decl) and id(node) not in getattr(self, '_field_ids', set()) and node.name in (self.functions.keys() | _BUILTINS | {'main'}):
            self.fail(node, f'变量名称 {node.name} 与函数名称重复')
        if isinstance(node, ast.Decl) and isinstance(node.type, ast.ArrayDecl):
            current, dimensions = node.type, []
            while isinstance(current, ast.ArrayDecl):
                dimensions.append(current)
                current = current.type
            if len(dimensions) > 2:
                self.fail(node, '数组最多支持二维')
            for axis, dimension in enumerate(dimensions):
                dim = dimension.dim
                if dim is None and (axis or node.init is None):
                    self.fail(node, '仅首维容量可从初始化列表推断')
                if dim is not None and not self._constant_integer(dim):
                    if global_scope:
                        self.fail(node, '全局数组容量需要整数常量表达式')
                    if node.init is not None:
                        self.fail(node, '运行时容量的数组不能带初始化列表')
        if isinstance(node, ast.ID) and node.name in (self.functions.keys() | _BUILTINS | {'main'}):
            self.fail(node, f'函数 {node.name} 只能用于函数调用，不能作为变量使用')
        if isinstance(node, ast.ArrayDecl):
            if not isinstance(node.type, (ast.TypeDecl, ast.ArrayDecl)) or node.dim_quals:
                self.fail(node, '方括号修饰符仅用于函数参数')
        if isinstance(node, ast.Constant) and node.type not in ('int', 'long int', 'long long int', 'char', 'float', 'double', 'string'):
            self.fail(node, f'暂不支持 {node.type} 常量')
        if isinstance(node, ast.Constant) and node.type in ('int', 'long int', 'long long int') and len(node.value) > 32:
            self.fail(node, '整数字面量过长；最大支持 64 位有符号 long')
        if isinstance(node, ast.Constant) and node.type in ('float', 'double') and node.value.lower().startswith('0x'):
            self.fail(node, '第一版暂不支持十六进制浮点字面量，请使用十进制')
        if isinstance(node, ast.Assignment) and node.op not in ('=', '+=', '-=', '*=', '/=', '%='):
            self.fail(node, f'暂不支持运算符 {node.op}')
        if isinstance(node, ast.BinaryOp) and node.op not in ('+', '-', '*', '/', '%', '<', '<=', '>', '>=', '==', '!=', '&&', '||'):
            self.fail(node, f'暂不支持运算符 {node.op}')
        if isinstance(node, ast.UnaryOp) and node.op not in ('+', '-', '!', 'p++', 'p--', '++', '--', '&', '*'):
            self.fail(node, f'暂不支持运算符 {node.op}')
        if isinstance(node, (ast.Break, ast.Continue)) and not loops:
            self.fail(node, 'break/continue 只能出现在循环内')
        if isinstance(node, ast.Return) and function:
            if function.return_type == 'void' and node.expr is not None:
                self.fail(node, 'void 函数的 return 不能带返回值')
            if function.return_type != 'void' and node.expr is None:
                self.fail(node, '非 void 函数的 return 必须带返回值')
        if isinstance(node, ast.FuncCall):
            if global_scope:
                self.fail(node, '全局变量初始化必须使用常量，不能调用函数')
            if not isinstance(node.name, ast.ID):
                self.fail(node, '仅支持通过函数名称直接调用')
            name = node.name.name
            if name == 'main':
                self.fail(node, 'main 是程序入口，不能作为函数调用')
            if name not in self.functions and name not in _BUILTINS:
                self.fail(node, f'函数 {name} 未定义或暂不支持')
            if name in self.functions:
                args = node.args.exprs if node.args else []
                expected = len(self.functions[name].params)
                if len(args) != expected:
                    self.fail(node, f'函数 {name} 需要 {expected} 个参数，实际提供 {len(args)} 个')
                if function:
                    self._calls[function.name].add(name)
            self._check(node.args, loops, depth + 1, function, global_scope)
            return
        child_loops = loops + isinstance(node, (ast.For, ast.While))
        for _, child in node.children():
            self._check(child, child_loops, depth + 1, function, global_scope)

    @staticmethod
    def _constant_integer(node, depth=0):
        if depth > 100:
            return False
        if isinstance(node, ast.Constant):
            return node.type in ('int', 'long int', 'long long int', 'char')
        if isinstance(node, ast.UnaryOp) and node.op in ('+', '-', '!'):
            return Program._constant_integer(node.expr, depth+1)
        if isinstance(node, ast.BinaryOp):
            return Program._constant_integer(node.left, depth+1) and Program._constant_integer(node.right, depth+1)
        return False

    def targets(self):
        result = []
        self.target_functions = {}

        def walk(node):
            if node is None:
                return
            if isinstance(node, ast.Compound):
                for child in node.block_items or []:
                    walk(child)
            elif isinstance(node, ast.DeclList):
                for child in node.decls:
                    walk(child)
            elif isinstance(node, (ast.For, ast.While, ast.If)):
                if isinstance(node, ast.For):
                    walk(node.init)
                result.append(self.location(node.cond or node, 'condition'))
                walk(node.stmt if isinstance(node, (ast.For, ast.While)) else node.iftrue)
                if isinstance(node, ast.If):
                    walk(node.iffalse)
                if isinstance(node, ast.For) and node.next:
                    result.append(self.location(node.next, 'update'))
            else:
                result.append(self.location(node))

        for node in self.globals:
            walk(node)
        for function in self.functions.values():
            first = len(result)
            result.append(self.location(function.node.decl, 'function'))
            walk(function.node.body)
            self.target_functions.update((loc, function.name) for loc in result[first:])
        walk(self.main)
        for loc in result:
            self.target_functions.setdefault(loc, '')
        return result

    def call_reaches(self, names, target):
        """Whether a pending call can enter the function owning a seek target."""
        pending, seen = list(names), set()
        while pending:
            name = pending.pop()
            if name == target:
                return True
            if name not in seen:
                seen.add(name)
                pending.extend(self._calls.get(name, ()))
        return False
