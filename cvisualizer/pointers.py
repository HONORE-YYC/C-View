"""Immutable typed addresses. Identity, never a variable name, determines storage."""
from dataclasses import dataclass


@dataclass(frozen=True)
class Pointer:
    identity: int | None
    index: int | None
    base_type: str
    name: str

    def __str__(self):
        if self.identity is None:
            return 'NULL'
        return f'&{self.name}' + (f'[{self.index}]' if self.index is not None else '')
