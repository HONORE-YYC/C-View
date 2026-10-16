import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PySide6.QtWidgets import QGraphicsRectItem
from cvisualizer.views import MemoryView
from cvisualizer.engine import Engine
from cvisualizer.structures import Binding


def boxes(view):
    return {item.data(0): item for item in view.scene().items()
            if isinstance(item, QGraphicsRectItem) and item.data(0)}


def texts(view):
    return [item.toPlainText() for item in view.scene().items() if hasattr(item, 'toPlainText')]


def test_scalar_gray_then_green_and_operations_keep_green_fill(app):
    e = Engine('int x; x=3; x+=2;')
    view = MemoryView()
    event = e.step()
    view.render(event.variables, [], event)
    assert boxes(view)['x'].brush().color().name() == '#e5e7eb'
    assert 'x' in texts(view)
    event = e.step()
    view.render(event.variables, [], event)
    assert boxes(view)['x'].brush().color().name() == '#dcfce7'
    assert 'x = 3' in texts(view)
    event = e.step()
    view.render(event.variables, [], event)
    assert boxes(view)['x'].brush().color().name() == '#dcfce7'
    assert 'x = 5' in texts(view)
    assert boxes(view)['x'].pen().color().name() == '#f59e0b'
    view.close()


def test_array_assignment_color_is_independent_of_structure_active_range(app):
    e = Engine('int a[3]; int n=0; a[1]=7;')
    while e.peek():
        e.step()
    view = MemoryView()
    view.render(e.runtime.snapshot(), [Binding('a', 'list', length='n')], e.last)
    cells = boxes(view)
    assert cells['a[0]'].brush().color().name() == '#e5e7eb'
    assert cells['a[1]'].brush().color().name() == '#dcfce7'
    assert cells['a[2]'].brush().color().name() == '#e5e7eb'
    assert 'a[0]' in texts(view)
    assert 'a[1] = 7' in texts(view)
    view.close()
