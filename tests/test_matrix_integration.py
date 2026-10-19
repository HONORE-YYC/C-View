from copy import deepcopy

from cvisualizer.arrays import Array
from cvisualizer.array_folding import FoldedArray, Fold


def test_outer_folding_distinguishes_empty_and_equal_whole_rows():
    # Exercise the outer sparse-array contract independently of the interpreter.
    rows = Array(100, Array(3))
    rows.columns = 3
    first = Array(3)
    first[0] = 1
    rows[0] = first
    layout = list(FoldedArray(rows))
    assert layout[0] == 0 and layout[1] == Fold(1, 100, None)
    assert len(FoldedArray(Array(11, Array(3)))) == 1  # Ordinary nested values.
    empty = Array(1000000000, Array(3))
    empty.columns = 3
    assert len(FoldedArray(empty)) == 1000000000  # Leading empty rows stay visible.
    same = Array(1000000000, Array(3, 7))
    same.columns = 3
    assert len(FoldedArray(same)) == 1
    changed = deepcopy(same.default)
    changed[2] = 8
    same[50] = changed
    assert [item if isinstance(item, int) else (item.start, item.end)
            for item in FoldedArray(same)] == [(0, 50), 50, (51, 1000000000)]


def test_equal_rows_fold_despite_different_sparse_defaults():
    rows = Array(12, Array(2, 3))
    rows.columns = 2
    explicit = Array(2)
    explicit[0] = explicit[1] = 3
    rows[5] = explicit
    assert len(FoldedArray(rows)) == 1


def test_matrix_loop_markers_follow_both_axes_and_row_pointers():
    from cvisualizer.engine import Engine
    engine = Engine('int a[2][3]={0};int i=0;int j=1;a[i][j]=4;int *p=a[1];p[j]=5;i=1;j=2;')
    while engine.peek():
        engine.step()
    markers = engine.index_markers()
    assert any(key[2] == 'i' and index == 1 for key, index in markers.items())
    assert any(key[2] == 'j[列]' and index == (1, 2) for key, index in markers.items())
    assert any(key[2] == 'j' and index == (1, 2) for key, index in markers.items())


def test_matrix_binding_keeps_two_dimensional_array_view():
    from cvisualizer.engine import Engine
    from cvisualizer.structures import Binding, describe
    engine = Engine('int a[2][3]={0};int top=1;')
    while engine.peek():
        engine.step()
    model = describe(Binding('a', 'stack', top='top'), engine.runtime.snapshot())
    assert model.kind == 'array'
    assert '二维' in model.error
