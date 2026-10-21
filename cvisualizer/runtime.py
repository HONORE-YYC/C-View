"""Runtime values and expression semantics; no GUI and no Python eval."""
import ast as literal_ast
from dataclasses import dataclass
from copy import deepcopy
import math

from pycparser import c_ast as ast

from .language import CError
from .motion import declaration_key
from .pointers import Pointer
from .numeric import Long, LongLong, Char, type_name
from .value_format import display
from . import math_library
from . import struct_runtime
from .struct_runtime import StructValue
from . import formatted_io
from . import stream_io
from . import standard_library
from .arrays import Array, Matrix
from .qualifiers import qualifiers
from dataclasses import replace
import sys


@dataclass
class Cell:
    type: str
    value: object
    identity: int
    declaration: tuple
    readonly: bool = False
    pointee_const: bool = False


class Reference(tuple):
    def __new__(cls, name, cell, index, readonly=False):
        result = super().__new__(cls, (name, cell, index))
        result.readonly = readonly
        return result


class Sources(list):
    def __init__(self):
        super().__init__()
        self.seen = set()

    def add(self, source):
        if source not in self.seen:
            self.seen.add(source)
            self.append(source)


def integer_literal(text):
    text = text.rstrip('lL')
    if text.lower().startswith('0x'):
        return int(text, 16)
    return int(text, 8 if len(text) > 1 and text.startswith('0') else 10)


class Runtime:
    def __init__(self, program):
        self.program = program
        self.scopes = [{}]
        self.callers = []
        self.heap = {}
        self.freed = set()
        self.write_targets = []
        self.output = ''
        self.reads, self.writes = [], []
        self.next_identity = 1
        self.random_state = 1
        self.transfers = []
        self._source_frames = []
        self.call_function = None
        self.input_provider = None
        self.input_text = ''
        self.input_position = 0
        self.literals = {}
        self.literal_pool = {}
        self.consume = None
        self.booleans = []

    def fail(self, node, message):
        self.program.fail(node, message)

    def visible_cells(self):
        """Name/identity lookup without copying array contents during dereference."""
        visible = {}
        for scope in self.scopes:
            visible.update(scope)
        visible.update(self.heap)
        visible = struct_runtime.flattened(visible)
        visible = {name: cell for name, cell in visible.items() if cell.identity not in self.freed}
        identities = {cell.identity for cell in visible.values()}
        for value in list(visible.values()):
            pointer = value.value
            if isinstance(pointer, Pointer) and pointer.identity not in identities:
                target = self.find_identity(pointer.identity)
                if target:
                    name, cell = target
                    alias = name if name not in visible else f'{name}@{cell.identity}'
                    visible.update(dict(struct_runtime.cells(alias, cell)))
                    identities.add(cell.identity)
        return visible

    def snapshot(self):
        return struct_runtime.snapshot(self, self.visible_cells())

    def find_identity(self, identity):
        if identity in self.freed:
            return None
        if identity in self.literals:
            return f'字符串{identity}', self.literals[identity]
        for name, cell in struct_runtime.flattened(self.heap).items():
            if cell.identity == identity:
                return name, cell
        for scopes in [self.scopes] + list(reversed(self.callers)):
            for scope in reversed(scopes):
                for name, cell in struct_runtime.flattened(scope).items():
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
        size = cell.value.columns if isinstance(cell.value, Matrix) and pointer.row is not None else len(cell.value) if isinstance(cell.value, list) else 1
        if pointer.row is not None and (not isinstance(cell.value, Matrix) or not 0 <= pointer.row < len(cell.value)):
            self.fail(node, '数组行下标越界')
        if not 0 <= offset <= size or (not address and offset == size):
            self.fail(node, '指针越界：不能访问对象范围外或尾后位置')
        for alias, value in self.visible_cells().items():
            if value.identity == cell.identity:
                name = alias
                break
        index = (pointer.row, offset) if pointer.row is not None else offset if isinstance(cell.value, list) else None
        if isinstance(cell.value, struct_runtime.StructArray) and not address:
            path, member, _ = struct_runtime.array_member(self, name, cell, offset, node)
            return Reference(path, member, None, pointer.readonly)
        return Reference(name, cell, index, pointer.readonly)

    def pointer_offset(self, pointer, amount, node):
        self.pointer_ref(pointer, node, address=True)
        if not isinstance(amount, int):
            self.fail(node, '指针偏移必须是整数')
        target = self.find_identity(pointer.identity)[1]
        index = (pointer.index or 0) + amount
        size = target.value.columns if isinstance(target.value, Matrix) and pointer.row is not None else len(target.value) if isinstance(target.value, list) else 1
        if not 0 <= index <= size:
            self.fail(node, '指针偏移越界')
        return Pointer(pointer.identity, index if isinstance(target.value, list) or index else None,
                       pointer.base_type, pointer.name, pointer.readonly, pointer.row)

    def cell(self, name, node):
        for scope in reversed(self.scopes):
            if name in scope:
                if scope[name].identity in self.freed:
                    self.fail(node, '引用目标已释放')
                return scope[name]
        self.fail(node, f'变量 {name} 未声明')

    def convert(self, value, type_name, node, pointee_const=False):
        if type_name.startswith('struct ') and not type_name.endswith('*'):
            if not isinstance(value, StructValue) or value.type != type_name:
                self.fail(node, '结构体赋值类型不匹配')
            return deepcopy(value)
        if type_name == 'bool':
            return self.truth(value, node)
        if type_name.endswith('*'):
            if isinstance(value, int) and value == 0:
                return Pointer(None, None, type_name[:-1], '')
            if not isinstance(value, Pointer) or value.base_type != type_name[:-1]:
                self.fail(node, '指针类型不匹配；只可赋同类型地址或空指针 0')
            if value.readonly and not pointee_const:
                self.fail(node, '不能丢弃指针目标的 const 只读修饰符')
            return replace(value, readonly=pointee_const)
        if not isinstance(value, (int, float)):
            self.fail(node, '需要数值，不能使用整个数组或字符串参与运算')
        if isinstance(value, float) and not math.isfinite(value):
            self.fail(node, '浮点数溢出或不是有限数值')
        if type_name in ('int', 'long', 'long long', 'char'):
            result = int(value)
            if type_name == 'char':
                return Char(result % 256)
            bits = 64 if type_name in ('long', 'long long') else 32
            if not -(2 ** (bits-1)) <= result < 2 ** (bits-1):
                self.fail(node, f'{bits} 位有符号整数溢出')
            return LongLong(result) if type_name == 'long long' else Long(result) if type_name == 'long' else result
        return float(value)

    def record_boolean(self, node, value, result, operands=None):
        expression = self.program.location(node).text
        # Parser coordinates also distinguish separate expansions of one macro.
        position = (node.coord.line, node.coord.column) if node.coord else None
        record = {'expression': expression, 'value': value, 'result': bool(result),
                  'position': position}
        if operands is not None:
            record['operands'] = operands
        if (self.booleans and self.booleans[-1]['position'] == position
                and self.booleans[-1]['expression'] == expression
                and self.booleans[-1]['value'] == value and self.booleans[-1]['result'] == bool(result)):
            return bool(result)
        if len(self.booleans) < 16:
            self.booleans.append(record)
        return bool(result)

    def truth(self, value, node):
        if isinstance(value, Pointer):
            return self.record_boolean(node, value, value.identity is not None)
        if not isinstance(value, (int, float)):
            self.fail(node, '条件或逻辑运算需要数值；srand 没有返回值')
        return self.record_boolean(node, value, bool(value))

    def declare(self, node, global_scope=False):
        if node.name is None:
            return '定义结构体类型'
        scope = self.scopes[-1]
        if node.name in scope:
            self.fail(node, f'变量 {node.name} 重复定义')
        if sum(len(s) for s in self.scopes) >= 512:
            self.fail(node, '同时存活变量超过 512 个')
        array = isinstance(node.type, ast.ArrayDecl)
        pointer = isinstance(node.type, ast.PtrDecl)
        base = node.type.type if array or pointer else node.type
        matrix = array and isinstance(base, ast.ArrayDecl)
        if matrix:
            base = base.type
        if not isinstance(base, ast.TypeDecl):
            self.fail(node, '不支持此声明')
        declared_type = self.program._scalar_type(base) + ('*' if pointer else '')
        if declared_type.startswith('struct ') and not declared_type.endswith('*'):
            return struct_runtime.declare(self, node, global_scope)
        readonly, pointee_const = qualifiers(node.type)
        if matrix:
            return self.declare_matrix(node, base, declared_type, 'const' in base.quals, global_scope)
        if array:
            readonly, pointee_const = 'const' in base.quals, False
        string_initial = None
        if array and declared_type == 'char' and isinstance(node.init, ast.Constant) and node.init.type == 'string':
            string_initial = self.string_literal(node.init)
        if array:
            if node.type.dim is None:
                size = len(string_initial)+1 if string_initial is not None else len(node.init.exprs or []) if isinstance(node.init, ast.InitList) else 0
                if not size:
                    self.fail(node, '省略数组容量时需要初始化列表或字符串')
            else:
                size = self.evaluate(node.type.dim)
            if not isinstance(size, int) or size <= 0:
                self.fail(node, '数组容量必须为正整数')
            if size > sys.maxsize:
                self.fail(node, '数组容量超出本机可表示的索引范围')
            initial = Array(size)
        else:
            initial = (False if declared_type == 'bool' else self.convert(0, declared_type, node)) if global_scope else None
        scope[node.name] = Cell(declared_type, initial, self.next_identity, declaration_key(node))
        scope[node.name].pointee_const = pointee_const
        self.next_identity += 1
        if array:
            if string_initial is not None:
                text = string_initial
                if len(text) > size or any(ord(c) > 255 for c in text):
                    self.fail(node, '字符串超出字符数组容量或包含非单字节字符')
                scope[node.name].value = Array(size, Char(0))
                for i, char in enumerate(text):
                    self.write((node.name, scope[node.name], i), ord(char), node)
                self.writes.append((node.name, None))
                scope[node.name].readonly = readonly
                return f'定义字符数组 {node.name}'
            if node.init is not None and not isinstance(node.init, ast.InitList):
                self.fail(node, '数组需要初始化列表，例如 {1, 2, 3}')
            exprs = node.init.exprs if node.init else []
            if len(exprs) > size:
                self.fail(node, '数组初始化元素多于容量')
            if node.init or global_scope:
                scope[node.name].value = Array(size, False if declared_type == 'bool' else self.convert(0, declared_type, node))
            for i, expr in enumerate(exprs):
                value, sources = self.evaluate_sources(expr)
                self.write((node.name, scope[node.name], i), value, expr, sources)
        elif node.init is not None:
            value, sources = self.evaluate_sources(node.init)
            self.write((node.name, scope[node.name], None), value, node.init, sources)
        self.writes.append((node.name, None))
        scope[node.name].readonly = readonly
        return f'定义 {node.name} = {display(scope[node.name].value)}'

    def dimension(self, expression, node):
        value = self.evaluate(expression)
        if not isinstance(value, int) or not 0 < value <= sys.maxsize:
            self.fail(node, '数组容量必须为正整数且不超过本机索引范围')
        return value

    def declare_matrix(self, node, base, declared_type, readonly, global_scope):
        # Evaluate each bound exactly once, in declarator order.
        rows = self.dimension(node.type.dim, node) if node.type.dim is not None else None
        columns = self.dimension(node.type.type.dim, node)
        exprs = node.init.exprs or [] if isinstance(node.init, ast.InitList) else []
        if node.init is not None and not isinstance(node.init, ast.InitList):
            self.fail(node, '二维数组需要初始化列表')
        entries, cursor = [], 0
        for expr in exprs:
            nested = isinstance(expr, ast.InitList)
            string = declared_type == 'char' and isinstance(expr, ast.Constant) and expr.type == 'string'
            if nested or string:
                if cursor % columns:
                    self.fail(expr, '嵌套初始化列表必须从数组行首开始')
                items = expr.exprs or [] if nested else self.string_literal(expr)
                if len(items) > columns:
                    self.fail(expr, '数组初始化元素多于列容量')
                for column, item in enumerate(items):
                    if isinstance(item, ast.InitList):
                        self.fail(item, '数组最多支持二维初始化')
                    entries.append((cursor + column, item, string))
                cursor += columns
            else:
                entries.append((cursor, expr, False))
                cursor += 1
        if rows is None:
            rows = (cursor + columns - 1) // columns
            if not rows:
                self.fail(node, '省略数组容量时需要非空初始化列表')
        if cursor > rows * columns:
            self.fail(node, '数组初始化元素多于容量')
        default = self.convert(0, declared_type, node) if node.init is not None or global_scope else None
        cell = Cell(declared_type, Matrix(rows, columns, default), self.next_identity, declaration_key(node))
        self.next_identity += 1
        self.scopes[-1][node.name] = cell
        for offset, expr, string in entries:
            value, sources = (ord(expr), ()) if string else self.evaluate_sources(expr)
            self.write((node.name, cell, divmod(offset, columns)), value, node, sources)
        cell.readonly = readonly
        self.writes.append((node.name, None))
        return f'定义二维数组 {node.name}'

    def reference(self, node, address=False):
        if isinstance(node, ast.StructRef):
            return struct_runtime.member_ref(self, node, address)
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
        if isinstance(value, Array):
            # A selected row decays to its first scalar element.
            self.reads.append((name, index))
            return Pointer(cell.identity, 0, cell.type, name, cell.readonly or getattr(ref, 'readonly', False), index)
        if value is None:
            self.fail(node, f'{name}' + (f'[{index}]' if index is not None else '') + ' 未初始化')
        self.reads.append((name, index))
        if isinstance(value, StructValue):
            for path, member in struct_runtime.cells(name, cell):
                if not isinstance(member.value, StructValue):
                    self.contribute((path, None, member.identity))
        self.contribute((name, index, cell.identity))
        return value

    def evaluate_sources(self, node):
        sources = Sources()
        self._source_frames.append(sources)
        try:
            return self.evaluate(node), sources
        finally:
            self._source_frames.pop()

    def contribute(self, source):
        if self._source_frames:
            self._source_frames[-1].add(source)

    def write(self, ref, value, node, sources=()):
        name, cell, index = ref
        self.check_writable(ref, node)
        if isinstance(cell.value, Matrix) and not isinstance(index, tuple):
            self.fail(node, '数组行不能整体赋值')
        if isinstance(cell.value, StructValue):
            return struct_runtime.copy_into(self, ref, value, node, sources)
        converted = self.convert(value, cell.type, node, cell.pointee_const)
        if index is None:
            cell.value = converted
        else:
            cell.value[index] = converted
        self.writes.append((name, index))
        self.write_targets.append((cell.identity, index))
        target = name, index, cell.identity
        self.transfers.extend((source, target) for source in sources if source != target)
        return converted

    def check_writable(self, ref, node):
        if ref[1].readonly or getattr(ref, 'readonly', False):
            self.fail(node, '不能修改 const 只读对象')

    def string_literal(self, node):
        try:
            text = literal_ast.literal_eval(node.value)
        except (ValueError, SyntaxError):
            self.fail(node, '字符串转义格式不受支持')
        if any(ord(c) > 255 for c in text):
            self.fail(node, '字符数组需要 0–255 单字节字符')
        return text

    def literal_pointer(self, node):
        text = self.string_literal(node)
        if text in self.literal_pool:
            identity = self.literal_pool[text]
            return Pointer(identity, 0, 'char', f'字符串{identity}', True)
        value = Array(len(text)+1, Char(0))
        for i, char in enumerate(text):
            value[i] = Char(ord(char))
        identity = self.next_identity
        self.next_identity += 1
        self.literals[identity] = Cell('char', value, identity, ('literal', 0, 0), True)
        self.literal_pool[text] = identity
        return Pointer(identity, 0, 'char', f'字符串{identity}', True)

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
                equal = (left.identity, left.row, left.index or 0) == (right.identity, right.row, right.index or 0)
                result = int(equal if op == '==' else not equal)
                self.record_boolean(node, result, result, (left, right))
                return result
            self.pointer_ref(left, node, address=True)
            self.pointer_ref(right, node, address=True)
            if left.identity != right.identity or left.row != right.row:
                self.fail(node, '指针相减和顺序比较要求指向同一对象')
            a, b = left.index or 0, right.index or 0
            if op == '-':
                return a - b
            if op in ('<', '<=', '>', '>='):
                result = int({'<': a < b, '<=': a <= b, '>': a > b, '>=': a >= b}[op])
                self.record_boolean(node, result, result, (left, right))
                return result
            self.fail(node, '不支持此指针运算')
        if not isinstance(left, (int, float)) or not isinstance(right, (int, float)):
            self.fail(node, '运算需要数值')
        both_int = isinstance(left, int) and isinstance(right, int)
        integer_type = 'long long' if isinstance(left, LongLong) or isinstance(right, LongLong) else 'long' if isinstance(left, Long) or isinstance(right, Long) else 'int'
        if op in ('/', '%') and right == 0:
            self.fail(node, '除零：除数或取余的右操作数不能为 0')
        if op == '%':
            if not both_int:
                self.fail(node, '取余运算要求两个整数')
            quotient = (abs(left) // abs(right)) * (-1 if (left < 0) != (right < 0) else 1)
            self.convert(quotient, integer_type, node)
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
            result = int(comparisons[op])
            self.record_boolean(node, result, result, (left, right))
            return result
        return self.convert(result, integer_type if both_int else 'double', node)

    def evaluate(self, node):
        if isinstance(node, ast.Cast):
            target = self.program._scalar_type(node.to_type.type)
            value = self.evaluate(node.expr)
            if target.endswith('*'):
                if self.program.preprocessed.cast_kinds.get((node.coord.line-self.program.offset, node.coord.column)) != 'const_cast':
                    self.fail(node, '指针转换仅支持 const_cast<T*>')
                if not isinstance(value, Pointer) or value.base_type != target[:-1]:
                    self.fail(node, 'const_cast 仅支持同类型单级指针')
                return replace(value, readonly=qualifiers(node.to_type.type)[1])
            return self.convert(value, target, node)

        if isinstance(node, ast.Constant):
            if node.type == 'string':
                return self.literal_pointer(node)
            if node.type in ('int', 'long int', 'long long int'):
                value = integer_literal(node.value)
                return self.convert(value, 'long long' if node.type == 'long long int' else 'long' if node.type == 'long int' or value > 2147483647 else 'int', node)
            if node.type == 'char':
                try:
                    value = literal_ast.literal_eval(node.value)
                except (ValueError, SyntaxError):
                    self.fail(node, '不支持此字符转义')
                if len(value) != 1 or ord(value) > 255:
                    self.fail(node, 'char 常量需要单个 0–255 字符')
                # Stream-enabled code needs C++ char literal type for insertion;
                # ordinary C snippets retain int literal semantics.
                return Char(ord(value)) if self.program.preprocessed.iostream else ord(value)
            if node.type in ('float', 'double'):
                return self.convert(float(node.value.rstrip('fFlL')), 'double', node)
            self.fail(node, '字符串只能作为 printf 的格式文本')
        if isinstance(node, ast.StructRef):
            if not struct_runtime.is_member_lvalue(node):
                return struct_runtime.temporary_member(self, node)
            ref = self.reference(node)
            if isinstance(ref[1].value, list):
                base_type = f'{ref[1].type}[{ref[1].value.columns}]' if isinstance(ref[1].value, Matrix) else ref[1].type
                return Pointer(ref[1].identity, 0, base_type, ref[0], ref[1].readonly or getattr(ref, 'readonly', False))
            return self.read(ref, node)
        if isinstance(node, (ast.ID, ast.ArrayRef)):
            if isinstance(node, ast.ID):
                cell = self.cell(node.name, node)
                if isinstance(cell.value, list):
                    base_type = f'{cell.type}[{cell.value.columns}]' if isinstance(cell.value, Matrix) else cell.type
                    return Pointer(cell.identity, 0, base_type, node.name, cell.readonly)
            return self.read(self.reference(node), node)
        if isinstance(node, ast.Assignment):
            ref = self.reference(node.lvalue)
            right, sources = self.evaluate_sources(node.rvalue)
            value = right if node.op == '=' else self.binary(node.op[0], self.read(ref, node), right, node)
            result = self.write(ref, value, node, sources)
            self.contribute((ref[0], ref[2], ref[1].identity))
            return result
        if isinstance(node, ast.BinaryOp):
            stream = stream_io.chain(node)
            if stream:
                return stream_io.execute(self, node, *stream)
            left = self.evaluate(node.left)
            if node.op == '&&':
                result = int(self.truth(left, node.left) and self.truth(self.evaluate(node.right), node.right))
                self.record_boolean(node, result, result)
                return result
            if node.op == '||':
                result = int(self.truth(left, node.left) or self.truth(self.evaluate(node.right), node.right))
                self.record_boolean(node, result, result)
                return result
            return self.binary(node.op, left, self.evaluate(node.right), node)
        if isinstance(node, ast.UnaryOp):
            if node.op == 'sizeof':
                declaration = ast.Decl('__heap', [], None, [], [], node.expr.type, None, None, coord=node.coord)
                loc = self.program.location(node)
                initialized = self.program.allocations[(loc.line, loc.column)]
                cell = struct_runtime.make_cell(self, declaration, initialized)
                name = f'堆#{cell.identity}'
                if len(self.heap) >= 512:
                    self.fail(node, '同时存活堆对象超过 512 个')
                self.heap[name] = cell
                self.writes.append((name, None))
                return Pointer(cell.identity, None, cell.type, name)
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
                ref = self.reference(node.expr, address=True)
                name, cell, index = ref
                if cell.type.endswith('*'):
                    self.fail(node, '不支持多级指针')
                return Pointer(cell.identity, index, cell.type, name, cell.readonly or getattr(ref, 'readonly', False))
            if node.op == '*':
                return self.read(self.reference(node), node)
            if node.op in ('p++', 'p--', '++', '--'):
                ref = self.reference(node.expr)
                old = self.read(ref, node)
                new = self.write(ref, self.binary('+' if '+' in node.op else '-', old, 1, node), node)
                return old if node.op.startswith('p') else new
            # The signed minimum is a unary-minus expression in the parser.
            if node.op == '-' and isinstance(node.expr, ast.Constant) and node.expr.type in ('int', 'long int', 'long long int'):
                value = -integer_literal(node.expr.value)
                return self.convert(value, 'long long' if node.expr.type == 'long long int' else 'long' if node.expr.type == 'long int' or value < -2147483647 else 'int', node)
            value = self.evaluate(node.expr)
            if node.op == '!':
                result = int(not self.truth(value, node.expr))
                self.record_boolean(node, result, result)
                return result
            if not isinstance(value, (int, float)):
                self.fail(node, '一元运算需要数值；srand 没有返回值')
            return self.convert(value if node.op == '+' else -value, 'long long' if isinstance(value, LongLong) else 'long' if isinstance(value, Long) else 'int' if isinstance(value, int) else 'double', node)
        if isinstance(node, ast.ExprList):
            for expr in node.exprs[:-1]:
                self.evaluate_sources(expr)
            return self.evaluate(node.exprs[-1]) if node.exprs else 0
        if isinstance(node, ast.FuncCall):
            if node.name.name == '__cv_delete':
                args = node.args.exprs if node.args else []
                if len(args) != 1:
                    self.fail(node, 'delete 需要单个指针')
                pointer = self.evaluate(args[0])
                if not isinstance(pointer, Pointer):
                    self.fail(node, 'delete 需要指针')
                if pointer.identity is None:
                    return 0
                target = next((name for name, cell in self.heap.items() if cell.identity == pointer.identity), None)
                if target is None or pointer.index not in (None, 0) or pointer.row is not None:
                    self.fail(node, 'delete 目标已释放或不是 new 创建的对象')
                self.freed.update(cell.identity for _, cell in struct_runtime.cells(target, self.heap[target]))
                del self.heap[target]
                return 0
            if node.name.name in self.program.functions:
                return self.call_function(node)
            if node.name.name in ('printf', 'scanf'):
                return getattr(formatted_io, node.name.name)(self, node)
            if node.name.name in math_library.FUNCTIONS:
                return math_library.execute(self, node)
            if node.name.name in standard_library.FUNCTIONS:
                return standard_library.execute(self, node)
            return self.stdlib(node)
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
