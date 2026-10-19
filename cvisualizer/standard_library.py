"""String and numeric library operations on interpreter-owned typed addresses."""
import re
from .pointers import Pointer
from .numeric import Long


FUNCTIONS = {'labs': 1, 'atoi': 1, 'atol': 1, 'atof': 1, 'strlen': 1,
             'strcpy': 2, 'strncpy': 3, 'strcat': 2, 'strncat': 3,
             'strcmp': 2, 'strncmp': 3, 'strchr': 2, 'strrchr': 2, 'strstr': 2}


def execute(rt, node):
    name = node.name.name
    expressions = node.args.exprs if node.args else []
    if len(expressions) != FUNCTIONS[name]:
        rt.fail(node, f'{name} 需要 {FUNCTIONS[name]} 个参数')
    args = [rt.evaluate(expr) for expr in expressions]
    location = rt.program.location(node)

    def count(value):
        if not isinstance(value, int) or value < 0:
            rt.fail(node, '字符数量必须为非负整数')
        return value

    def pointer(value, write=False):
        if not isinstance(value, Pointer) or value.base_type != 'char':
            rt.fail(node, f'{name} 需要 char 数组或指针')
        ref = rt.pointer_ref(value, node)
        if write:
            rt.check_writable(ref, node)
        return value

    def ref_at(p, i):
        rt.consume(location)
        return rt.pointer_ref(rt.pointer_offset(p, i, node), node)

    def read(p, i):
        return rt.read(ref_at(p, i), node)

    def string(p, limit=None):
        pointer(p)
        chars = []
        i = 0
        while limit is None or i < limit:
            value = read(p, i)
            if not value:
                break
            chars.append(chr(value))
            i += 1
        return ''.join(chars)

    def overlap(dest, source, dest_start, dest_count, source_count):
        if dest.identity == source.identity and dest.row == source.row:
            a, b = (dest.index or 0)+dest_start, source.index or 0
            if a < b+source_count and b < a+dest_count:
                rt.fail(node, f'{name} 的源和目标区域不能重叠')

    if name == 'labs':
        if not isinstance(args[0], int):
            rt.fail(node, 'labs 需要整数')
        return rt.convert(abs(args[0]), 'long', node)
    if name in ('atoi', 'atol', 'atof'):
        text = string(args[0]).lstrip()
        pattern = r'[+-]?\d+' if name != 'atof' else r'[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?'
        match = re.match(pattern, text, re.ASCII)
        if not match:
            return 0.0 if name == 'atof' else Long(0) if name == 'atol' else 0
        value = match[0]
        if name == 'atof':
            return rt.convert(float(value), 'double', node)
        digits = value.lstrip('+-').lstrip('0') or '0'
        if len(digits) > 19:
            rt.fail(node, f'{name} 整数转换溢出')
        return rt.convert(int(digits)*(-1 if value.startswith('-') else 1), 'long' if name == 'atol' else 'int', node)
    if name == 'strlen':
        return Long(len(string(args[0])))
    if name in ('strcmp', 'strncmp'):
        a, b = pointer(args[0]), pointer(args[1])
        maximum = count(args[2]) if name == 'strncmp' else None
        i = 0
        while maximum is None or i < maximum:
            x, y = read(a,i), read(b,i)
            if x != y:
                return -1 if x < y else 1
            if x == 0:
                return 0
            i += 1
        return 0
    if name in ('strchr', 'strrchr', 'strstr'):
        p = pointer(args[0])
        text = string(p)
        if name == 'strstr':
            index = text.find(string(args[1]))
        else:
            if not isinstance(args[1], int):
                rt.fail(node, '查找字符需要整数或字符')
            char = chr(args[1] % 256)
            index = (text+'\0').find(char) if name == 'strchr' else (text+'\0').rfind(char)
        return rt.pointer_offset(p, index, node) if index >= 0 else Pointer(None, None, 'char', '', p.readonly)

    dest, source = pointer(args[0], write=True), pointer(args[1])
    maximum = count(args[2]) if name in ('strncpy', 'strncat') else None
    text = string(source, maximum)
    start = len(string(dest)) if name in ('strcat', 'strncat') else 0
    total = maximum if name == 'strncpy' else len(text)+1
    source_count = len(text)+(1 if maximum is None or len(text) < maximum else 0)
    overlap(dest, source, start, total, source_count)
    if total:
        # Validate the final write before changing any byte.
        rt.pointer_ref(rt.pointer_offset(dest, start+total-1, node), node)
    for i in range(total):
        target = ref_at(dest, start+i)
        value = ord(text[i]) if i < len(text) else 0
        origins = ()
        if i < source_count:
            src = rt.pointer_ref(rt.pointer_offset(source, i, node), node)
            origins = ((src[0], src[2], src[1].identity),)
        rt.write(target, value, node, origins)
    return dest
