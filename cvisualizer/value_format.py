"""Shared value labels for memory cells and transient demonstrations."""
from .numeric import Char
from .pointers import Pointer
import re


def display_name(name):
    """Storage identities belong in hover details, not teaching labels."""
    return re.sub(r'^堆#\d+', '节点', name)


def display(value):
    if value is None:
        return '?'
    if isinstance(value, Pointer) and value.identity is not None and value.name.startswith('堆#'):
        return '指向节点'
    if isinstance(value, Char):
        return repr(chr(value))
    if isinstance(value, bool):
        return 'true' if value else 'false'
    if isinstance(value, (list, tuple)):
        values = ', '.join(display(item) for item in value[:6])
        return '[' + values + (', …' if len(value) > 6 else '') + ']'
    if isinstance(value, float):
        return f'{value:.6g}'
    return str(value)
