"""Map logical array positions to compact display slots, without expanding gaps."""
from bisect import bisect_right
from collections.abc import Sequence
from dataclasses import dataclass
from .arrays import Array


@dataclass(frozen=True)
class Fold:
    start: int
    end: int  # Exclusive.
    value: object


def value_runs(values):
    def chunks():
        if not isinstance(values, Array):
            for i, value in enumerate(values):
                yield i, i+1, value
            return
        cursor = 0
        for page_index, page in sorted(values.pages.items()):
            start = page_index*values.PAGE
            if start > cursor:
                yield cursor, start, values.default
            end = min(len(values),start+values.PAGE)
            for i in range(start,end):
                yield i,i+1,page[i-start]
            cursor = end
        if cursor < len(values):
            yield cursor,len(values),values.default
    pending = None
    for start,end,value in chunks():
        if pending is not None and pending[2] == value:
            pending = (pending[0],end,value)
        else:
            if pending is not None:
                yield pending
            pending = (start,end,value)
    if pending is not None:
        yield pending


class FoldedArray(Sequence):
    def __init__(self, values, protected=()):
        self.spans, self.ends = [], []
        keep = sorted(set(i for i in protected if 0 <= i < len(values)))
        total = 0
        def add(start,end,value,foldable):
            nonlocal total
            if start == end:
                return
            folded = foldable and end-start > 10
            self.spans.append(Fold(start,end,value) if folded else range(start,end))
            total += 1 if folded else end-start
            self.ends.append(total)
        for start,end,value in value_runs(values):
            foldable = value is not None or start > 0
            cursor = start
            left, right = bisect_right(keep,start-1), bisect_right(keep,end-1)
            for index in keep[left:right]:
                add(cursor,index,value,foldable)
                add(index,index+1,value,False)
                cursor = index+1
            add(cursor,end,value,foldable)

    def __len__(self):
        return self.ends[-1] if self.ends else 0

    def __getitem__(self, index):
        if isinstance(index,slice):
            return [self[i] for i in range(*index.indices(len(self)))]
        if index < 0:
            index += len(self)
        if not 0 <= index < len(self):
            raise IndexError(index)
        pos = bisect_right(self.ends,index)
        span = self.spans[pos]
        return span if isinstance(span,Fold) else span[index-(self.ends[pos-1] if pos else 0)]
