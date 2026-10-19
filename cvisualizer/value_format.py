"""Shared value labels for memory cells and transient demonstrations."""
from .numeric import Char


def display(value):
    if value is None:
        return '?'
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
