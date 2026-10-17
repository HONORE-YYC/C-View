import pytest
from PySide6.QtCore import QEvent, QPoint, Qt
from PySide6.QtGui import QTextCursor
from PySide6.QtTest import QTest

from cvisualizer.editor import CodeEditor


@pytest.fixture
def editor(app):
    widget = CodeEditor()
    widget.resize(420, 220)
    widget.setPlainText('\n'.join(f'int value_{i} = {i};' for i in range(100)))
    widget.show()
    app.processEvents()
    yield widget
    widget.close()


def line_point(editor, line):
    block = editor.document().findBlockByNumber(line - 1)
    rect = editor.blockBoundingGeometry(block).translated(editor.contentOffset())
    return QPoint(editor.gutter.width() // 2, int(rect.center().y()))


def test_hover_replaces_number_click_preserves_selection_and_scroll(editor, app):
    assert hasattr(editor, 'playLineRequested'), 'Editor must expose gutter playback requests'
    editor.set_playable_lines([3])
    requests = []
    editor.playLineRequested.connect(requests.append)
    cursor = editor.textCursor()
    cursor.setPosition(8)
    cursor.setPosition(2, QTextCursor.MoveMode.KeepAnchor)
    editor.setTextCursor(cursor)
    state = (cursor.position(), cursor.anchor(), editor.verticalScrollBar().value())
    app.sendEvent(editor.gutter, QEvent(QEvent.Type.Leave))
    before = editor.gutter.grab().toImage()
    point = line_point(editor, 3)
    QTest.mouseMove(editor.gutter, point)
    app.processEvents()
    assert editor.gutter.cursor().shape() == Qt.CursorShape.PointingHandCursor
    assert editor.gutter.toolTip() == '播放当前语句'
    assert editor.gutter.grab().toImage() != before
    QTest.mouseClick(editor.gutter, Qt.MouseButton.LeftButton, pos=point)
    assert requests == [3]
    cursor = editor.textCursor()
    assert (cursor.position(), cursor.anchor(), editor.verticalScrollBar().value()) == state
    app.sendEvent(editor.gutter, QEvent(QEvent.Type.Leave))
    assert editor.gutter.grab().toImage() == before
    assert editor.gutter.toolTip() == ''


def test_gutter_resolves_visible_block_after_scroll_without_moving_mouse(editor, app):
    assert hasattr(editor, 'set_playable_lines'), 'Executable lines must be configurable'
    editor.set_playable_lines(range(1, 101))
    requests = []
    editor.playLineRequested.connect(requests.append)
    point = line_point(editor, 3)
    QTest.mouseMove(editor.gutter, point)
    editor.verticalScrollBar().setValue(40)
    app.processEvents()
    expected_line = editor.cursorForPosition(point).blockNumber() + 1
    assert expected_line > 3
    scroll = editor.verticalScrollBar().value()
    QTest.mouseClick(editor.gutter, Qt.MouseButton.LeftButton, pos=point)
    assert requests == [expected_line]
    assert editor.verticalScrollBar().value() == scroll


def test_disabled_nonexecutable_and_right_click_do_not_play(editor, app):
    assert hasattr(editor, 'set_play_enabled'), 'Playback availability must be configurable'
    editor.set_playable_lines([3])
    requests = []
    editor.playLineRequested.connect(requests.append)
    QTest.mouseMove(editor.gutter, line_point(editor, 2))
    QTest.mouseClick(editor.gutter, Qt.MouseButton.LeftButton, pos=line_point(editor, 2))
    assert editor.gutter.cursor().shape() != Qt.CursorShape.PointingHandCursor
    point = line_point(editor, 3)
    QTest.mouseMove(editor.gutter, point)
    QTest.mouseClick(editor.gutter, Qt.MouseButton.RightButton, pos=point)
    editor.set_play_enabled(False)
    QTest.mouseClick(editor.gutter, Qt.MouseButton.LeftButton, pos=point)
    assert editor.gutter.cursor().shape() != Qt.CursorShape.PointingHandCursor
    assert editor.gutter.toolTip() == ''
    assert requests == []
    editor.set_play_enabled(True)
    QTest.mouseClick(editor.gutter, Qt.MouseButton.LeftButton, pos=point)
    assert requests == [3]
    editor.set_playable_lines([])
    QTest.mouseClick(editor.gutter, Qt.MouseButton.LeftButton, pos=point)
    assert requests == [3]
