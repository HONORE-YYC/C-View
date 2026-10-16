from PySide6.QtGui import QTextCursor

from cvisualizer.editor import CodeEditor
from cvisualizer.engine import Engine
from cvisualizer.views import MemoryView
from cvisualizer.window import MainWindow


def test_array_position_stays_fixed_as_scalars_enter_and_leave_scope(app):
    view = MemoryView()
    view.resize(600, 650)
    view.show()
    app.processEvents()
    code = 'int a[3]={0}; {\n' + '\n'.join(f'int v{i}={i};' for i in range(20)) + '\n}\na[0]=1;'
    engine = Engine(code)
    positions = []
    while engine.peek():
        event = engine.step()
        view.render(engine.runtime.snapshot(), [], event, animate=False)
        app.processEvents()
        cell = next(item for (name, index, _), item in view.boxes.items() if name == 'a' and index == 0)
        positions.append(cell.sceneBoundingRect().top())
    assert max(positions) - min(positions) < 1
    view.close()


def test_scalar_scrolling_does_not_move_arrays_and_is_retained(app):
    view = MemoryView()
    view.resize(600, 650)
    view.show()
    engine = Engine('int a[30]={0};' + ''.join(f'int v{i}={i};' for i in range(24)) + 'v23++;')
    for _ in range(25):
        event = engine.step()
    view.render(engine.runtime.snapshot(), [], event, animate=False)
    app.processEvents()
    scalar = next(item for (name, _, _), item in view.boxes.items() if name == 'v23')
    array = next(item for (name, index, _), item in view.boxes.items() if name == 'a' and index == 0)
    scalar_y, array_y = scalar.sceneBoundingRect().top(), array.sceneBoundingRect().top()
    assert view.scalar_scroll.maximum() > 0
    view.scalar_scroll.setValue(view.scalar_scroll.maximum())
    assert scalar.sceneBoundingRect().top() < scalar_y
    assert array.sceneBoundingRect().top() == array_y
    offset = view.scalar_scroll.value()
    event = engine.step()
    view.render(engine.runtime.snapshot(), [], event, animate=False)
    assert view.scalar_scroll.value() == offset
    assert view.array_scroll.maximum() > 0
    view.close()


def test_execution_highlight_preserves_editor_selection_and_scroll(app):
    editor = CodeEditor()
    editor.resize(400, 250)
    editor.setPlainText('\n'.join(f'int v{i}={i};' for i in range(100)))
    editor.show()
    cursor = editor.textCursor()
    cursor.setPosition(2)
    cursor.setPosition(8, QTextCursor.MoveMode.KeepAnchor)
    editor.setTextCursor(cursor)
    app.processEvents()
    scroll = editor.verticalScrollBar().value()
    editor.mark(90, 5)
    assert editor.verticalScrollBar().value() == scroll
    assert editor.textCursor().selectedText() == cursor.selectedText()
    assert editor.extraSelections()[0].cursor.blockNumber() == 89
    editor.close()


def test_jump_button_only_navigates_when_clicked_and_resets(app):
    window = MainWindow()
    window.show()
    window.load_code('\n'.join(['// padding'] * 90 + ['int x=1;', 'x++;']), [])
    app.processEvents()
    assert not window.jump_button.isEnabled()
    before = window.editor.verticalScrollBar().value()
    window.step()
    assert window.editor.verticalScrollBar().value() == before
    assert window.jump_button.isEnabled()
    count = window.controller.engine.count
    window.jump_button.click()
    assert window.editor.textCursor().blockNumber() == 90
    assert window.editor.verticalScrollBar().value() > before
    assert window.controller.engine.count == count
    window.reset()
    assert not window.jump_button.isEnabled()
    window.close()


def test_scrolled_scalar_transfer_uses_visible_positions(app):
    view = MemoryView()
    view.resize(600, 800)
    view.show()
    app.processEvents()
    engine = Engine('int a[2]={0};' + ''.join(f'int v{i}={i};' for i in range(20)) + 'a[0]=v19;')
    for _ in range(21):
        event = engine.step()
    view.render(engine.runtime.snapshot(), [], event, animate=False)
    view.scalar_scroll.setValue(view.scalar_scroll.maximum())
    event = engine.step()
    view.render(engine.runtime.snapshot(), [], event)
    assert len(view.motion.arrows) == 1
    source = next(item for (name, _, _), item in view.boxes.items() if name == 'v19')
    assert abs(view.motion.arrows[0].route.pointAtPercent(0).y() - source.mapRectToScene(source.rect()).bottom() - 2) < 1
    view.close()


def test_array_scroll_keeps_pointer_attached_and_stays_on_next_step(app):
    view = MemoryView()
    view.resize(600, 650)
    view.show()
    engine = Engine('int a[30]={0}; int i=0; a[i]=1; i=1;')
    for _ in range(3):
        event = engine.step()
    view.render(engine.runtime.snapshot(), [], event, pointers=engine.index_markers(), animate=False)
    pointer = next(iter(view.motion.pointers.values()))
    before = pointer.scenePos().y()
    view.array_scroll.setValue(50)
    assert pointer.scenePos().y() == before-50
    event = engine.step()
    view.render(engine.runtime.snapshot(), [], event, pointers=engine.index_markers())
    view.motion.finish()
    assert view.array_scroll.value() == 50
    pointer = next(iter(view.motion.pointers.values()))
    cell = next(item for (name, index, _), item in view.boxes.items() if name == 'a' and index == 1)
    assert pointer.scenePos().y() == cell.mapRectToScene(cell.rect()).top()-4
    view.close()


def test_loop_index_declarations_do_not_shift_array_layout(app):
    window = MainWindow()
    window.show()
    app.processEvents()
    window.load_code('int a[3]={0}; int i=0; int j=1; a[i]=2; a[j]=3;', [])
    positions = []
    for _ in range(5):
        window.step()
        window.visuals.motion.finish()
        cell = next(item for (name, index, _), item in window.visuals.boxes.items() if name == 'a' and index == 0)
        positions.append(cell.sceneBoundingRect().top())
    assert max(positions)-min(positions) < 1
    window.close()
