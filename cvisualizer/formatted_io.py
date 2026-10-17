"""Bounded C formatted I/O, independent of Qt. Input providers return one line."""
import ast
import re

from .errors import CError
from .pointers import Pointer


class InputCancelled(CError):
    pass


def format_args(rt, node):
    args = node.args.exprs if node.args else []
    if not args or getattr(args[0], 'type', None) != 'string':
        rt.fail(node, f'{node.name.name} 第一个参数必须为字符串常量')
    try:
        return ast.literal_eval(args[0].value), args[1:]
    except (ValueError, SyntaxError):
        rt.fail(node, '字符串转义格式不受支持')


def tokens(rt, node, fmt, scanning=False):
    pattern = r'%(?:(\d+)?(ld|lf|d|f|c|s)|(%))' if scanning else r'%(?:(ld|lf|d|f|c|s)|(%))'
    pieces = []
    i = 0
    while i < len(fmt):
        if fmt[i] != '%':
            pieces.append(fmt[i])
            i += 1
            continue
        match = re.match(pattern, fmt[i:])
        if not match:
            rt.fail(node, '格式仅支持 %d、%ld、%f、%lf、%c、%s、%%（scanf 可指定宽度）')
        if scanning:
            width, kind, percent = match.groups()
            if width and len(width) > 6:
                rt.fail(node, '输入字段宽度必须在 1–100000 之间')
            width = int(width) if width else None
            if width is not None and not 1 <= width <= 100000:
                rt.fail(node, '输入字段宽度必须在 1–100000 之间')
        else:
            kind, percent = match.groups()
            width = None
        pieces.append('%' if percent else (kind, width))
        i += len(match[0])
    return pieces


def c_string(rt, pointer, node):
    if not isinstance(pointer, Pointer) or pointer.base_type != 'char':
        rt.fail(node, '%s 需要 char 数组或指针')
    chars = []
    _, cell, index = rt.pointer_ref(pointer, node)
    capacity = len(cell.value) - index if isinstance(cell.value, list) else 1
    for offset in range(capacity):
        if rt.consume:
            rt.consume(rt.program.location(node))
        value = rt.read(rt.pointer_ref(rt.pointer_offset(pointer, offset, node), node), node)
        if value == 0:
            return ''.join(chars)
        chars.append(chr(value))
    rt.fail(node, '字符串缺少结束符或超过容量')


def printf(rt, node):
    fmt, args = format_args(rt, node)
    parts = tokens(rt, node, fmt)
    specs = [p for p in parts if isinstance(p, tuple)]
    if len(specs) != len(args):
        rt.fail(node, 'printf 格式与参数数量不一致')
    arguments = iter(args)
    rendered = []
    for part in parts:
        if isinstance(part, str):
            rendered.append(part)
            continue
        kind, _ = part
        expr = next(arguments)
        value = rt.evaluate(expr)
        if kind == 's':
            text = c_string(rt, value, expr)
        elif kind in ('d', 'ld', 'c'):
            if not isinstance(value, int):
                rt.fail(expr, f'printf %{kind} 与参数类型不匹配')
            text = chr(value % 256) if kind == 'c' else str(value)
        else:
            if not isinstance(value, float):
                rt.fail(expr, f'printf %{kind} 与参数类型不匹配')
            text = f'{value:f}'
        rendered.append(text)
    text = ''.join(rendered)
    if len(rt.output) + len(text) > 100000:
        rt.fail(node, '输出超过 100000 字符上限')
    rt.output += text
    return len(text)


def scanf(rt, node):
    fmt, args = format_args(rt, node)
    parts = tokens(rt, node, fmt, scanning=True)
    specs = [p for p in parts if isinstance(p, tuple)]
    if len(specs) != len(args):
        rt.fail(node, 'scanf 格式与参数数量不一致')
    targets = []
    for (kind, width), expr in zip(specs, args):
        pointer = rt.evaluate(expr)
        expected = {'d': 'int', 'ld': 'long', 'f': 'float', 'lf': 'double', 'c': 'char', 's': 'char'}[kind]
        if not isinstance(pointer, Pointer) or pointer.base_type != expected:
            rt.fail(expr, f'scanf %{kind} 需要 {expected} 类型的地址')
        rt.check_writable(rt.pointer_ref(pointer, expr), expr)
        targets.append(pointer)

    def ensure():
        if rt.input_position < len(rt.input_text):
            return
        if rt.input_provider is None:
            raise InputCancelled('等待 scanf 输入', rt.program.location(node).line)
        line = rt.input_provider({'format': fmt, 'line': rt.program.location(node).line,
                                  'statement': rt.program.location(node).text, 'output': rt.output})
        if line is None:
            raise InputCancelled('已取消输入；可继续或单步重试', rt.program.location(node).line)
        if len(line) > 100000 or len(rt.input_text) + len(line) > 1000000:
            rt.fail(node, '输入超过容量限制')
        rt.input_text += line + '\n'

    def skip_space():
        while True:
            ensure()
            if not rt.input_text[rt.input_position].isspace():
                break
            rt.input_position += 1

    assigned = 0
    targets = iter(targets)
    for part in parts:
        if isinstance(part, str):
            if part.isspace():
                skip_space()
            else:
                ensure()
                if rt.input_text[rt.input_position] != part:
                    return assigned
                rt.input_position += 1
            continue
        kind, width = part
        pointer = next(targets)
        if kind != 'c':
            skip_space()
        ensure()
        remaining = rt.input_text[rt.input_position:]
        if width:
            remaining = remaining[:width]
        if kind in ('d', 'ld'):
            match = re.match(r'[+-]?\d+', remaining, re.ASCII)
        elif kind in ('f', 'lf'):
            match = re.match(r'[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?', remaining, re.ASCII)
        elif kind == 's':
            match = re.match(r'\S+', remaining)
        else:
            count = width or 1
            while len(rt.input_text) - rt.input_position < count:
                # Request another line without discarding the partial character field.
                position = rt.input_position
                rt.input_position = len(rt.input_text)
                try:
                    ensure()
                finally:
                    rt.input_position = position
            match = None
            text = rt.input_text[rt.input_position:rt.input_position + count]
        if kind != 'c':
            if match is None:
                return assigned
            text = match[0]
        if kind in ('c', 's'):
            values = [ord(ch) for ch in text] + ([0] if kind == 's' else [])
            _, cell, index = rt.pointer_ref(pointer, node)
            available = len(cell.value) - index if isinstance(cell.value, list) else 1
            if len(values) > available:
                rt.fail(node, 'scanf 写入超过字符数组容量；请增大数组或限制 %s 宽度')
            if any(value > 255 for value in values):
                rt.fail(node, 'char 支持 0–255 的单字节字符，不能存储该字符')
            for offset, value in enumerate(values):
                rt.write(rt.pointer_ref(rt.pointer_offset(pointer, offset, node), node), value, node)
        else:
            if kind in ('d', 'ld') and len(text.lstrip('+-').lstrip('0')) > 19:
                rt.fail(node, '输入整数溢出')
            if kind in ('d', 'ld'):
                # Avoid Python's decimal digit limit even for very long leading zeros.
                magnitude = int(text.lstrip('+-').lstrip('0') or '0')
                value = -magnitude if text.startswith('-') else magnitude
            else:
                value = float(text)
            rt.write(rt.pointer_ref(pointer, node), value, node)
        rt.input_position += len(text)
        assigned += 1
    return assigned
