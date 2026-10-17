"""Runtime values and expression semantics; no GUI and no Python eval."""
import ast as literal_ast
from dataclasses import dataclass
from copy import deepcopy
import math
import re

from pycparser import c_ast as ast

from .language import CError
from .motion import declaration_key
from .pointers import Pointer


@dataclass
class Cell:
    type: str
    value: object
    identity: int
    declaration: tuple


def integer_literal(text):
    if text.lower().startswith('0x'):
        return int(text, 16)
    return int(text, 8 if len(text) > 1 and text.startswith('0') else 10)


class Runtime:
    def __init__(self, program):
        self.program = program
        self.scopes = [{}]
        self.callers = []
        self.write_targets = []
        self.output = ''
        self.reads, self.writes = [], []
        self.next_identity = 1
        self.random_state = 1
        self.transfers = []
        self._source_frames = []
        self.call_function = None

    def fail(self, node, message):
        self.program.fail(node, message)

    def visible_cells(self):
        """Name/identity lookup without copying array contents during dereference."""
        visible = {}
        for scope in self.scopes:
            visible.update(scope)
        identities = {cell.identity for cell in visible.values()}
        for value in list(visible.values()):
            pointer = value.value
            if isinstance(pointer, Pointer) and pointer.identity not in identities:
                target = self.find_identity(pointer.identity)
                if target:
                    name, cell = target
                    alias = name if name not in visible else f'{name}@{cell.identity}'
                    visible[alias] = cell
                    identities.add(cell.identity)
        return visible

    def snapshot(self):
        return {name: {'type': cell.type, 'value': deepcopy(cell.value), 'identity': cell.identity,
                       'declaration': cell.declaration} for name, cell in self.visible_cells().items()}

    def find_identity(self, identity):
        for scopes in [self.scopes] + list(reversed(self.callers)):
            for scope in reversed(scopes):
                for name, cell in scope.items():
                    if cell.identity == identity:
                        return name, cell
        return None

    def pointer_ref(self, pointer, node, address=False):
        if not isinstance(pointer, Pointer):
            self.fail(node, '解引用需要指针')
        if pointer.identity is None:
            self.fail(node, '不能解引用或移动空指针')
        target = self.find_identity(pointer.identity)
        if target is None:
            self.fail(node, '悬空指针：目标对象已离开作用域')
        name, cell = target
        offset = pointer.index if pointer.index is not None else 0
        size = len(cell.value) if isinstance(cell.value, list) else 1
        if not 0 <= offset <= size or (not address and offset == size):
            self.fail(node, '指针越界：不能访问对象范围外或尾后位置')
        for alias, value in self.visible_cells().items():
            if value.identity == cell.identity:
                name = alias
                break
        index = offset if isinstance(cell.value, list) else None
        return name, cell, index

    def pointer_offset(self, pointer, amount, node):
        self.pointer_ref(pointer, node, address=True)
        if not isinstance(amount, int):
            self.fail(node, '指针偏移必须是整数')
        target = self.find_identity(pointer.identity)[1]
        index = (pointer.index or 0) + amount
        size = len(target.value) if isinstance(target.value, list) else 1
        if not 0 <= index <= size:
            self.fail(node, '指针偏移越界')
        return Pointer(pointer.identity, index if isinstance(target.value, list) or index else None,
                       pointer.base_type, pointer.name)

    def cell(self, name, node):
        for scope in reversed(self.scopes):
            if name in scope:
                return scope[name]
        self.fail(node, f'变量 {name} 未声明')

    def convert(self, value, type_name, node):
        if type_name.endswith('*'):
            if isinstance(value, int) and value == 0:
                return Pointer(None, None, type_name[:-1], '')
            if not isinstance(value, Pointer) or value.base_type != type_name[:-1]:
                self.fail(node, '指针类型不匹配；只可赋同类型地址或空指针 0')
            return value
        if not isinstance(value, (int, float)):
            self.fail(node, '需要数值，不能使用整个数组或字符串参与运算')
        if isinstance(value, float) and not math.isfinite(value):
            self.fail(node, '浮点数溢出或不是有限数值')
        if type_name == 'int':
            result = int(value)
            if not -2147483648 <= result <= 2147483647:
                self.fail(node, '32 位有符号整数溢出')
            return result
        return float(value)

    def truth(self, value, node):
        if isinstance(value, Pointer):
            return value.identity is not None
        if not isinstance(value, (int, float)):
            self.fail(node, '条件或逻辑运算需要数值；srand 没有返回值')
        return bool(value)

    def declare(self, node, global_scope=False):
        scope = self.scopes[-1]
        if node.name in scope:
            self.fail(node, f'变量 {node.name} 重复定义')
        if sum(len(s) for s in self.scopes) >= 512:
            self.fail(node, '同时存活变量超过 512 个')
        array = isinstance(node.type, ast.ArrayDecl)
        pointer = isinstance(node.type, ast.PtrDecl)
        base = node.type.type if array or pointer else node.type
        if not isinstance(base, ast.TypeDecl):
            self.fail(node, '不支持此声明')
        type_name = base.type.names[0] + ('*' if pointer else '')
        if array:
            size = self.evaluate(node.type.dim)
            if not 1 <= size <= 4096:
                self.fail(node, '数组容量必须在 1–4096 之间')
            live = sum(len(c.value) for s in self.scopes for c in s.values() if isinstance(c.value, list))
            if live + size > 16384:
                self.fail(node, '数组总元素超过 16384 个')
            initial = [None] * size
        else:
            initial = self.convert(0, type_name, node) if global_scope else None
        scope[node.name] = Cell(type_name, initial, self.next_identity, declaration_key(node))
        self.next_identity += 1
        if array:
            if node.init is not None and not isinstance(node.init, ast.InitList):
                self.fail(node, '数组需要初始化列表，例如 {1, 2, 3}')
            exprs = node.init.exprs if node.init else []
            if len(exprs) > size:
                self.fail(node, '数组初始化元素多于容量')
            if node.init or global_scope:
                scope[node.name].value = [self.convert(0, type_name, node)] * size
            for i, expr in enumerate(exprs):
                value, sources = self.evaluate_sources(expr)
                self.write((node.name, scope[node.name], i), value, expr, sources)
        elif node.init is not None:
            value, sources = self.evaluate_sources(node.init)
            self.write((node.name, scope[node.name], None), value, node.init, sources)
        self.writes.append((node.name, None))
        return f'定义 {node.name} = {scope[node.name].value}'

    def reference(self, node, address=False):
        if isinstance(node, ast.UnaryOp) and node.op == '*':
            pointer, _ = self.evaluate_sources(node.expr)
            return self.pointer_ref(pointer, node, address)
        if isinstance(node, ast.ID):
            cell = self.cell(node.name, node)
            if isinstance(cell.value, list):
                self.fail(node, '数组需要下标，不能整体赋值或参与运算')
            return node.name, cell, None
        if isinstance(node, ast.ArrayRef):
            pointer, _ = self.evaluate_sources(node.name)
            # Index reads choose an address; they are not copied into the target.
            index, _ = self.evaluate_sources(node.subscript)
            if not isinstance(index, int):
                self.fail(node, '数组下标必须是整数')
            return self.pointer_ref(self.pointer_offset(pointer, index, node), node, address)
        self.fail(node, '赋值或自增的目标必须是变量或数组元素')

    def read(self, ref, node):
        name, cell, index = ref
        value = cell.value if index is None else cell.value[index]
        if value is None:
            self.fail(node, f'{name}' + (f'[{index}]' if index is not None else '') + ' 未初始化')
        self.reads.append((name, index))
        self.contribute((name, index, cell.identity))
        return value

    def evaluate_sources(self, node):
        sources = []
        self._source_frames.append(sources)
        try:
            return self.evaluate(node), sources
        finally:
            self._source_frames.pop()

    def contribute(self, source):
        if self._source_frames and source not in self._source_frames[-1]:
            self._source_frames[-1].append(source)

    def write(self, ref, value, node, sources=()):
        name, cell, index = ref
        converted = self.convert(value, cell.type, node)
        if index is None:
            cell.value = converted
        else:
            cell.value[index] = converted
        self.writes.append((name, index))
        self.write_targets.append((cell.identity, index))
        target = name, index, cell.identity
        self.transfers.extend((source, target) for source in sources if source != target)
        return converted

    def binary(self, op, left, right, node):
        if isinstance(left, Pointer) or isinstance(right, Pointer):
            if op == '+' and isinstance(left, int) and isinstance(right, Pointer):
                return self.pointer_offset(right, left, node)
            if isinstance(left, Pointer) and isinstance(right, int) and op in ('+', '-'):
                return self.pointer_offset(left, right if op == '+' else -right, node)
            if op in ('==', '!='):
                if isinstance(left, int) and left == 0:
                    left = Pointer(None, None, right.base_type, '')
                if isinstance(right, int) and right == 0:
                    right = Pointer(None, None, left.base_type, '')
            if not isinstance(left, Pointer) or not isinstance(right, Pointer) or left.base_type != right.base_type:
                self.fail(node, '指针类型不匹配或不支持此运算')
            if op in ('==', '!='):
                equal = (left.identity, left.index or 0) == (right.identity, right.index or 0)
                return int(equal if op == '==' else not equal)
            self.pointer_ref(left, node, address=True)
            self.pointer_ref(right, node, address=True)
            if left.identity != right.identity:
                self.fail(node, '指针相减和顺序比较要求指向同一对象')
            a, b = left.index or 0, right.index or 0
            if op == '-':
                return a - b
            if op in ('<', '<=', '>', '>='):
                return int({'<': a < b, '<=': a <= b, '>': a > b, '>=': a >= b}[op])
            self.fail(node, '不支持此指针运算')
        if not isinstance(left, (int, float)) or not isinstance(right, (int, float)):
            self.fail(node, '运算需要数值')
        both_int = isinstance(left, int) and isinstance(right, int)
        if op in ('/', '%') and right == 0:
            self.fail(node, '除零：除数或取余的右操作数不能为 0')
        if op == '%':
            if not both_int:
                self.fail(node, '取余运算要求两个整数')
            quotient = (abs(left) // abs(right)) * (-1 if (left < 0) != (right < 0) else 1)
            self.convert(quotient, 'int', node)
            result = left - quotient * right
        elif op == '/' and both_int:
            result = (abs(left) // abs(right)) * (-1 if (left < 0) != (right < 0) else 1)
        elif op == '/':
            result = left / right
        elif op == '+':
            result = left + right
        elif op == '-':
            result = left - right
        elif op == '*':
            result = left * right
        else:
            comparisons = {'<': left < right, '<=': left <= right, '>': left > right,
                           '>=': left >= right, '==': left == right, '!=': left != right}
            return int(comparisons[op])
        return self.convert(result, 'int' if both_int else 'double', node)

    def evaluate(self, node):
        if isinstance(node, ast.Constant):
            if node.type == 'int':
                return self.convert(integer_literal(node.value), 'int', node)
            if node.type in ('float', 'double'):
                return self.convert(float(node.value.rstrip('fFlL')), 'double', node)
            self.fail(node, '字符串只能作为 printf 的格式文本')
        if isinstance(node, (ast.ID, ast.ArrayRef)):
            if isinstance(node, ast.ID):
                cell = self.cell(node.name, node)
                if isinstance(cell.value, list):
                    return Pointer(cell.identity, 0, cell.type, node.name)
            return self.read(self.reference(node), node)
        if isinstance(node, ast.Assignment):
            ref = self.reference(node.lvalue)
            right, sources = self.evaluate_sources(node.rvalue)
            value = right if node.op == '=' else self.binary(node.op[0], self.read(ref, node), right, node)
            result = self.write(ref, value, node, sources)
            self.contribute((ref[0], ref[2], ref[1].identity))
            return result
        if isinstance(node, ast.BinaryOp):
            left = self.evaluate(node.left)
            if node.op == '&&':
                return int(self.truth(left, node.left) and self.truth(self.evaluate(node.right), node.right))
            if node.op == '||':
                return int(self.truth(left, node.left) or self.truth(self.evaluate(node.right), node.right))
            return self.binary(node.op, left, self.evaluate(node.right), node)
        if isinstance(node, ast.UnaryOp):
            if node.op == '&':
                if isinstance(node.expr, ast.UnaryOp) and node.expr.op == '*':
                    value, _ = self.evaluate_sources(node.expr.expr)
                    if not isinstance(value, Pointer):
                        self.fail(node, '取地址和解引用需要指针')
                    return value
                if isinstance(node.expr, ast.ArrayRef):
                    value, _ = self.evaluate_sources(node.expr.name)
                    offset, _ = self.evaluate_sources(node.expr.subscript)
                    return self.pointer_offset(value, offset, node)
                name, cell, index = self.reference(node.expr, address=True)
                if cell.type.endswith('*'):
                    self.fail(node, '不支持多级指针')
                return Pointer(cell.identity, index, cell.type, name)
            if node.op == '*':
                return self.read(self.reference(node), node)
            if node.op in ('p++', 'p--', '++', '--'):
                ref = self.reference(node.expr)
                old = self.read(ref, node)
                new = self.write(ref, self.binary('+' if '+' in node.op else '-', old, 1, node), node)
                return old if node.op.startswith('p') else new
            # The signed minimum is a unary-minus expression in the parser.
            if node.op == '-' and isinstance(node.expr, ast.Constant) and node.expr.type == 'int':
                return self.convert(-integer_literal(node.expr.value), 'int', node)
            value = self.evaluate(node.expr)
            if node.op == '!':
                return int(not self.truth(value, node))
            if not isinstance(value, (int, float)):
                self.fail(node, '一元运算需要数值；srand 没有返回值')
            return self.convert(value if node.op == '+' else -value, 'int' if isinstance(value, int) else 'double', node)
        if isinstance(node, ast.ExprList):
            for expr in node.exprs[:-1]:
                self.evaluate_sources(expr)
            return self.evaluate(node.exprs[-1]) if node.exprs else 0
        if isinstance(node, ast.FuncCall):
            if node.name.name in self.program.functions:
                return self.call_function(node)
            return self.printf(node) if node.name.name == 'printf' else self.stdlib(node)
        self.fail(node, f'此处不能执行 {type(node).__name__}')

    def stdlib(self, node):
        name = node.name.name
        args = node.args.exprs if node.args else []
        expected = 0 if name == 'rand' else 1
        if len(args) != expected:
            self.fail(node, f'{name} 需要 {expected} 个参数')
        value = self.evaluate(args[0]) if args else None
        if expected and not isinstance(value, int):
            self.fail(node, f'{name} 的参数必须是 int')
        if name == 'abs':
            return self.convert(abs(value), 'int', node)
        if name == 'srand':
            self.random_state = value & 0xffffffff
            return None  # void: valid as a statement, invalid as a numeric operand.
        # A reproducible teaching LCG; RAND_MAX is 32767, not a platform ABI promise.
        self.random_state = (1103515245 * self.random_state + 12345) & 0x7fffffff
        return (self.random_state >> 16) & 32767

    def printf(self, node):
        args = node.args.exprs if node.args else []
        if not args or not isinstance(args[0], ast.Constant) or args[0].type != 'string':
            self.fail(node, 'printf 第一个参数必须为字符串常量')
        try:
            fmt = literal_ast.literal_eval(args[0].value)
        except (ValueError, SyntaxError):
            self.fail(node, 'printf 字符串转义格式不受支持')
        tokens = re.findall(r'%(?:%|d|f)|%', fmt)
        if '%' in tokens:
            self.fail(node, 'printf 仅支持 %d、%f、%%')
        specs = [s for s in tokens if s != '%%']
        if len(specs) != len(args) - 1:
            self.fail(node, 'printf 格式与参数数量不一致')
        values = []
        for spec, expr in zip(specs, args[1:]):
            value = self.evaluate(expr)
            if (spec == '%d' and not isinstance(value, int)) or (spec == '%f' and not isinstance(value, float)):
                self.fail(expr, f'printf {spec} 与参数类型不匹配')
            values.append(value)
        rendered = fmt % tuple(values)
        if len(self.output) + len(rendered) > 100000:
            self.fail(node, '输出超过 100000 字符上限')
        self.output += rendered
        return len(rendered)
