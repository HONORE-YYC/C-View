"""Teaching subset of C++ streams using the existing interpreter I/O buffer."""
import ast as literals
import re
from dataclasses import replace
from pycparser import c_ast as ast
from .formatted_io import InputCancelled, c_string
from .numeric import Char
from .pointers import Pointer
from .arrays import Matrix

NAMES = {'cin', 'cout', 'endl'}


def normalize(tokens):
    """Drop namespace syntax token-wise, retaining locations and string literals."""
    tokens = list(tokens)
    indices = [i for i, token in enumerate(tokens) if not token.text.isspace()]
    words = [tokens[i].text for i in indices]
    for pos in range(len(indices)):
        count = 0
        if words[pos:pos+4] == ['using', 'namespace', 'std', ';']:
            count = 4
        elif words[pos:pos+3] == ['std', ':', ':'] and pos+3 < len(words) and words[pos+3] in NAMES:
            count = 3
            index = indices[pos+3]
            origin = tokens[indices[pos]]
            tokens[index] = replace(tokens[index], line=origin.line, column=origin.column, expanded=True)
        for index in indices[pos:pos+count]:
            tokens[index] = replace(tokens[index], text=' ' * len(tokens[index].text))
    return tokens


def chain(node):
    if not isinstance(node, ast.BinaryOp) or node.op not in ('<<', '>>'):
        return None
    operator, args, root = node.op, [], node
    while isinstance(root, ast.BinaryOp) and root.op == operator:
        args.append(root.right)
        root = root.left
    name = getattr(root, 'name', None) if isinstance(root, ast.ID) else None
    if (name, operator) not in (('cin', '>>'), ('cout', '<<')):
        return None
    return name, list(reversed(args))


def execute(rt, node, name, args):
    for expr in args:
        if name == 'cin':
            extract(rt, node, expr)
        else:
            text = render(rt, expr)
            if len(rt.output) + len(text) > 100000:
                rt.fail(node, '输出超过 100000 字符上限')
            rt.output += text
    # Stream objects are not numeric results in this bounded subset.
    return None


def render(rt, expr):
    if isinstance(expr, ast.ID) and expr.name == 'endl':
        return '\n'
    if isinstance(expr, ast.Constant) and expr.type == 'char':
        return chr(rt.evaluate(expr))
    if isinstance(expr, ast.Constant) and expr.type == 'string':
        try:
            return literals.literal_eval(expr.value).split('\0', 1)[0]
        except (SyntaxError, ValueError):
            rt.fail(expr, '字符串或字符转义格式不受支持')
    value = rt.evaluate(expr)
    if isinstance(value, Pointer):
        if value.base_type != 'char':
            rt.fail(expr, 'cout 暂仅支持数值、字符和字符串输出')
        return c_string(rt, value, expr)
    if isinstance(value, Char):
        return chr(value)
    if isinstance(value, int):
        return str(int(value))
    if isinstance(value, float):
        return format(value, '.6g')
    rt.fail(expr, 'cout 暂仅支持数值、字符和字符串输出')


def ensure(rt, node):
    if rt.input_position < len(rt.input_text):
        return
    loc = rt.program.location(node)
    if rt.input_provider is None:
        raise InputCancelled('等待 cin 输入', loc.line, loc.column)
    line = rt.input_provider({'kind': 'cin', 'format': '', 'line': loc.line,
                              'statement': loc.text, 'output': rt.output})
    if line is None:
        raise InputCancelled('已取消输入；可继续或单步重试', loc.line, loc.column)
    if len(line) > 100000 or len(rt.input_text) + len(line) > 1000000:
        rt.fail(node, '输入超过容量限制')
    rt.input_text += line + '\n'


def extract(rt, statement, expr):
    if isinstance(expr, ast.ID):
        ref = (expr.name, rt.cell(expr.name, expr), None)
    else:
        ref = rt.reference(expr)
    name, cell, index = ref
    capacity = None
    if cell.type != 'char*':
        rt.check_writable(ref, expr)
    if cell.type == 'char*':
        pointer = rt.read(ref, expr)
        ref = rt.pointer_ref(pointer, expr)
        name, cell, index = ref
        capacity = cell.value.columns-index[1] if isinstance(index, tuple) else len(cell.value)-index if isinstance(cell.value, list) else 1
    elif isinstance(cell.value, Matrix) and isinstance(index, int):
        if cell.type != 'char':
            rt.fail(expr, 'cin 目标需要数值变量或字符数组')
        capacity, index = cell.value.columns, (index, 0)
        ref = (name, cell, index)
    elif isinstance(cell.value, list) and index is None:
        if cell.type != 'char' or isinstance(cell.value, Matrix):
            rt.fail(expr, 'cin 目标需要数值变量或字符数组')
        capacity, index = len(cell.value), 0
        ref = (name, cell, index)
    if cell.type not in ('int', 'long', 'long long', 'float', 'double', 'char', 'bool'):
        rt.fail(expr, 'cin 目标需要数值变量或字符数组')
    rt.check_writable(ref, expr)
    while True:
        ensure(rt, statement)
        if not rt.input_text[rt.input_position].isspace():
            break
        rt.input_position += 1
    remaining = rt.input_text[rt.input_position:]
    if capacity is not None:
        text = re.match(r'\S+', remaining)[0]
        if len(text)+1 > capacity:
            rt.fail(expr, 'cin 输入超过字符数组容量（需要预留结束符）')
        values = [ord(char) for char in text] + [0]
        if any(value > 255 for value in values):
            rt.fail(expr, 'char 支持 0–255 的单字节字符')
        for offset, value in enumerate(values):
            target = (index[0], index[1]+offset) if isinstance(index, tuple) else index+offset if index is not None else None
            rt.write((name, cell, target), value, expr)
    elif cell.type == 'char':
        text = remaining[0]
        if ord(text) > 255:
            rt.fail(expr, 'char 支持 0–255 的单字节字符')
        rt.write(ref, ord(text), expr)
    else:
        integer = cell.type in ('int', 'long', 'long long', 'bool')
        pattern = r'[+-]?\d+' if integer else r'[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?'
        match = re.match(pattern, remaining, re.ASCII)
        if not match:
            rt.fail(expr, 'cin 输入与目标类型不匹配')
        text = match[0]
        if integer:
            digits = text.lstrip('+-').lstrip('0') or '0'
            if len(digits) > 19:
                rt.fail(expr, '输入整数溢出')
            value = int(digits) * (-1 if text.startswith('-') else 1)
        else:
            value = float(text)
        if cell.type == 'bool' and value not in (0, 1):
            rt.fail(expr, 'cin 的 bool 输入应为 0 或 1')
        rt.write(ref, value, expr)
    rt.input_position += len(text)
