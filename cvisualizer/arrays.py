"""Sparse fixed-size arrays with shared immutable pages for execution snapshots.

The list protocol is retained for the visualizer's existing array consumers.
Only indexed writes are supported; C arrays never resize or append.
"""
from collections.abc import Sequence


class Array(list):
    PAGE = 64

    def __init__(self, size, default=None):
        self.size, self.default, self.pages = int(size), default, {}

    def __len__(self):
        return self.size

    def __getitem__(self, index):
        if isinstance(index, slice):
            return [self[i] for i in range(*index.indices(self.size))]
        if index < 0:
            index += self.size
        if not 0 <= index < self.size:
            raise IndexError(index)
        page = self.pages.get(index // self.PAGE)
        return self.default if page is None else page[index % self.PAGE]

    def __setitem__(self, index, value):
        if not isinstance(index, int) or not 0 <= index < self.size:
            raise IndexError(index)
        key, offset = divmod(index, self.PAGE)
        if self[index] == value and type(self[index]) is type(value):
            return
        page = list(self.pages.get(key, (self.default,) * self.PAGE))
        page[offset] = value
        self.pages = {**self.pages, key: tuple(page)}

    def __iter__(self):
        return (self[i] for i in range(self.size))

    def __deepcopy__(self, memo):
        result = type(self)(self.size, self.default)
        result.pages = self.pages  # Published maps/pages are never mutated.
        memo[id(self)] = result
        return result

    def __eq__(self, other):
        if isinstance(other, Array):
            return self.size == other.size and self.default == other.default and self.pages == other.pages
        return isinstance(other, (list, tuple)) and len(other) == self.size and all(a == b for a,b in zip(self,other))

    def __ne__(self, other):
        return not self == other

    def __repr__(self):
        return repr(self[:8])[:-1] + (f', …（容量 {self.size}）]' if self.size > 8 else ']')


class Matrix(Array):
    """Sparse rows published immutably; scalar writes copy just one row/page."""
    def __init__(self, rows, columns, default=None):
        self.columns = int(columns)
        super().__init__(rows, Array(columns, default))

    def __getitem__(self, index):
        if isinstance(index, tuple):
            row, column = index
            return super().__getitem__(row)[column]
        return super().__getitem__(index)

    def __setitem__(self, index, value):
        if not isinstance(index, tuple) or len(index) != 2:
            raise TypeError('Matrix writes require (row, column)')
        row, column = index
        from copy import deepcopy
        changed = deepcopy(super().__getitem__(row))
        changed[column] = value
        super().__setitem__(row, changed)

    def __deepcopy__(self, memo):
        result = type(self)(self.size, self.columns, self.default.default)
        result.default = self.default
        result.pages = self.pages
        memo[id(self)] = result
        return result


class Indices(Sequence):
    """A contiguous or circular range, with constant-time membership checks."""
    def __init__(self, count, start=0, capacity=None):
        self.count, self.start, self.capacity = count, start, capacity

    def __len__(self):
        return self.count

    def __getitem__(self, index):
        if isinstance(index, slice):
            return [self[i] for i in range(*index.indices(self.count))]
        if index < 0:
            index += self.count
        if not 0 <= index < self.count:
            raise IndexError(index)
        value = self.start + index
        return value % self.capacity if self.capacity else value

    def __contains__(self, value):
        return (0 <= value < self.capacity and (value-self.start) % self.capacity < self.count) if self.capacity else self.start <= value < self.start+self.count

    def __eq__(self, other):
        return len(self) == len(other) and all(a == b for a,b in zip(self,other))


class OrderedValues(Sequence):
    def __init__(self, values, indices):
        self.values, self.indices = values, indices

    def __len__(self):
        return len(self.indices)

    def __getitem__(self, index):
        if isinstance(index, slice):
            return [self.values[i] for i in self.indices[index]]
        return self.values[self.indices[index]]

    def __eq__(self, other):
        return len(self) == len(other) and all(a == b for a,b in zip(self,other))
