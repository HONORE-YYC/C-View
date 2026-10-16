import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QTextCursor
from PySide6.QtTest import QTest
from cvisualizer.editor import CodeEditor


@pytest.fixture
def editor(app):
    widget = CodeEditor()
    yield widget
    widget.close()


@pytest.mark.parametrize('opening,closing', [('(', ')'), ('[', ']'), ('{', '}'), ('"', '"'), ("'", "'")])
def test_pairs_and_skip_existing_closer(editor, opening, closing):
    QTest.keyClicks(editor, opening)
    assert editor.toPlainText() == opening+closing
    assert editor.textCursor().position() == 1
    QTest.keyClicks(editor, closing)
    assert editor.toPlainText() == opening+closing
    assert editor.textCursor().position() == 2


def test_wrap_selection_and_undo_as_one_operation(editor):
    editor.setPlainText('x + 1')
    editor.selectAll()
    QTest.keyClicks(editor, '(')
    assert editor.toPlainText() == '(x + 1)'
    editor.undo()
    assert editor.toPlainText() == 'x + 1'


def test_backspace_empty_pair(editor):
    QTest.keyClicks(editor, '(')
    QTest.keyClick(editor, Qt.Key.Key_Backspace)
    assert editor.toPlainText() == ''


def test_braces_newline_indent_and_undo(editor):
    QTest.keyClicks(editor, 'if (1) {')
    QTest.keyClick(editor, Qt.Key.Key_Return)
    assert editor.toPlainText() == 'if (1) {\n    \n}'
    assert editor.textCursor().blockNumber() == 1
    assert editor.textCursor().positionInBlock() == 4
    editor.undo()
    assert editor.toPlainText() == 'if (1) {}'


def test_enter_keeps_indent_and_closing_brace_dedents(editor):
    editor.setPlainText('if (1) {\n    int x;')
    editor.moveCursor(QTextCursor.MoveOperation.End)
    QTest.keyClick(editor, Qt.Key.Key_Return)
    assert editor.toPlainText().endswith('\n    ')
    QTest.keyClicks(editor, '}')
    assert editor.toPlainText().endswith('\n}')


def test_tab_shift_tab_multiline(editor):
    editor.setPlainText('int x;\nint y;')
    editor.selectAll()
    QTest.keyClick(editor, Qt.Key.Key_Tab)
    assert editor.toPlainText() == '    int x;\n    int y;'
    QTest.keyClick(editor, Qt.Key.Key_Backtab)
    assert editor.toPlainText() == 'int x;\nint y;'


def test_no_pairing_in_comments_strings_or_after_escape(editor):
    QTest.keyClicks(editor, '// (')
    assert editor.toPlainText() == '// ('
    editor.setPlainText('')
    QTest.keyClicks(editor, '"(')
    assert editor.toPlainText() == '"("'
    QTest.keyClicks(editor, '\\"')
    assert editor.toPlainText() == '"(\\""'


def test_readonly_cannot_be_modified_by_auto_edit(editor):
    editor.setPlainText('int x;')
    editor.setReadOnly(True)
    QTest.keyClicks(editor, '(')
    QTest.keyClick(editor, Qt.Key.Key_Return)
    assert editor.toPlainText() == 'int x;'


def test_unindent_single_line_keeps_cursor_relative_to_code(editor):
    editor.setPlainText('    int x;')
    editor.moveCursor(QTextCursor.MoveOperation.End)
    QTest.keyClick(editor, Qt.Key.Key_Backtab)
    assert editor.toPlainText() == 'int x;'
    assert editor.textCursor().position() == 6


def test_unicode_prefix_keeps_pairing_cursor_and_comments(editor):
    editor.setPlainText('// 中文😀\n')
    editor.moveCursor(QTextCursor.MoveOperation.End)
    QTest.keyClicks(editor, '(')
    assert editor.toPlainText().endswith('()')
    QTest.keyClicks(editor, ')')
    assert editor.toPlainText().endswith('()')
    assert editor.textCursor().atEnd()


def test_existing_closing_brace_on_indented_line_dedents(editor):
    editor.setPlainText('if (1) {\n    }')
    cursor = editor.textCursor()
    cursor.movePosition(QTextCursor.MoveOperation.End)
    cursor.movePosition(QTextCursor.MoveOperation.Left)
    editor.setTextCursor(cursor)
    QTest.keyClicks(editor, '}')
    assert editor.toPlainText() == 'if (1) {\n}'


def test_unindent_does_not_move_cursor_to_following_line(editor):
    editor.setPlainText('    int x;\nint y;')
    cursor = editor.textCursor()
    cursor.setPosition(7)
    editor.setTextCursor(cursor)
    QTest.keyClick(editor, Qt.Key.Key_Backtab)
    assert editor.textCursor().position() == 3
    QTest.keyClicks(editor, ' z')
    assert editor.toPlainText() == 'int z x;\nint y;'


def test_reverse_selection_uses_context_before_selected_text(editor):
    editor.setPlainText('int x = 1; // note')
    cursor = editor.textCursor()
    cursor.setPosition(18)
    cursor.setPosition(14, QTextCursor.MoveMode.KeepAnchor)
    editor.setTextCursor(cursor)
    QTest.keyClicks(editor, '(')
    assert editor.toPlainText() == 'int x = 1; // ('
