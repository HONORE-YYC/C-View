from cvisualizer.arrays import Array
from cvisualizer.array_folding import FoldedArray, Fold


def test_threshold_gaps_tail_and_leading_uninitialized():
    values = [None]*12+[1]+[None]*11+[2]+[None]*10
    layout = FoldedArray(values)
    assert list(layout) == list(range(13))+[Fold(13,24,None)]+list(range(24,35))
    assert list(FoldedArray([1]+[None]*11)) == [0,Fold(1,12,None)]
    assert list(FoldedArray([None]*100)) == list(range(100))


def test_repeated_values_and_protected_target():
    assert list(FoldedArray([7]*11)) == [Fold(0,11,7)]
    assert list(FoldedArray([7]*10)) == list(range(10))
    layout = FoldedArray([7]*50, protected={20})
    assert list(layout) == [Fold(0,20,7),20,Fold(21,50,7)]


def test_billion_element_sparse_array_and_snapshots():
    values = Array(1000000000)
    values[0] = 1
    values[999999999] = 2
    assert list(FoldedArray(values)) == [0,Fold(1,999999999,None),999999999]
    assert list(FoldedArray(Array(1000000000,0))) == [Fold(0,1000000000,0)]


def test_view_bracket_counts_and_pointer_targets(app):
    from cvisualizer.engine import Engine
    from cvisualizer.views import MemoryView
    e = Engine('int a[100]={0};int *p=&a[50];')
    while e.peek():
        e.step()
    v = MemoryView()
    v.resize(650,600)
    v.show()
    v.render(e.runtime.snapshot(), [], e.last, animate=False)
    assert any(key[1] == 50 for key in v.boxes)
    labels = [item.toPlainText() for item in v.scene().items() if hasattr(item,'toPlainText')]
    assert '...' in labels
    assert any('50 个' in text for text in labels)
    assert any('49 个' in text for text in labels)
    assert any(key[0]=='address' and item.isVisible() for key,item in v.motion.pointers.items())
    v.close()


def test_list_folding_preserves_length_boundary(app):
    from cvisualizer.engine import Engine
    from cvisualizer.views import MemoryView
    from cvisualizer.structures import Binding
    e=Engine('int a[100]={0};int length=5;')
    while e.peek():
        e.step()
    v=MemoryView()
    v.resize(950,800)
    v.render(e.runtime.snapshot(),[Binding('a','list',length='length')],e.last,animate=False)
    indices={key[1] for key in v.boxes if key[0]=='a'}
    assert 4 in indices and 5 in indices
    v.close()
