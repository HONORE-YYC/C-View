"""C editor with a line-number gutter and execution highlighting."""
import re

from PySide6.QtCore import Qt, QRect, QSize, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QSyntaxHighlighter, QTextCharFormat, QTextCursor
from PySide6.QtWidgets import QPlainTextEdit, QWidget, QTextEdit
from .editing import context, escaped


class CHighlighter(QSyntaxHighlighter):
    def highlightBlock(self, text):
        rules = [
            (r'\b(?:int|float|double|void|if|else|for|while|break|continue|return)\b', '#7c3aed'),
            (r'\b(?:0x[0-9a-fA-F]+|\d+(?:\.\d+)?)\b', '#b45309'),
            (r'\b(?:printf|abs|rand|srand)\b', '#0369a1'),
            (r'^\s*#\s*(?:include|define|undef)\b.*', '#0369a1'),
            (r'"(?:\\.|[^"\\])*"', '#047857'),
            (r'//.*$', '#7b8a9e'),
        ]
        for pattern, color in rules:
            for match in re.finditer(pattern, text):
                self.setFormat(match.start(), len(match[0]), QColor(color))
        self.setCurrentBlockState(0)
        start = 0 if self.previousBlockState() == 1 else text.find('/*')
        while start >= 0:
            end = text.find('*/', start + (0 if self.previousBlockState() == 1 and start == 0 else 2))
            if end < 0:
                self.setFormat(start, len(text)-start, QColor('#7b8a9e'))
                self.setCurrentBlockState(1)
                break
            self.setFormat(start, end + 2-start, QColor('#7b8a9e'))
            start = text.find('/*', end+2)


class Gutter(QWidget):
    def __init__(self, editor):
        super().__init__(editor)
        self.editor = editor

    def sizeHint(self):
        return QSize(self.editor.gutter_width(), 0)

    def paintEvent(self, event):
        self.editor.paint_gutter(event)


class CodeEditor(QPlainTextEdit):
    markChanged = Signal(bool)

    def __init__(self):
        super().__init__()
        self._execution_cursor = None
        self.setFont(QFont('Consolas', 11))
        self.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.setTabStopDistance(self.fontMetrics().horizontalAdvance(' ') * 4)
        self.gutter = Gutter(self)
        self.highlighter = CHighlighter(self.document())
        self.blockCountChanged.connect(self.update_gutter_width)
        self.updateRequest.connect(self.update_gutter)
        self.update_gutter_width()
        self.setPlaceholderText('在这里输入 C 代码，或从顶部选择可编辑示例…')

    def keyPressEvent(self, event):
        if self.isReadOnly() or event.modifiers() & (Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.AltModifier | Qt.KeyboardModifier.MetaModifier):
            super().keyPressEvent(event)
            return
        cursor = self.textCursor()
        text = self.toPlainText()
        # QTextCursor offsets are UTF-16, Python string offsets are Unicode scalars.
        left = QTextCursor(cursor)
        left.setPosition(cursor.selectionStart())
        left.setPosition(0, QTextCursor.MoveMode.KeepAnchor)
        prefix = left.selectedText().replace('\u2029', '\n')
        pos = len(prefix)
        char = event.text()
        state, braces = context(prefix)
        pairs = {'(': ')', '[': ']', '{': '}', '"': '"', "'": "'"}
        next_char = text[pos:pos+1]
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self.newline(cursor)
            return
        if event.key() in (Qt.Key.Key_Tab, Qt.Key.Key_Backtab):
            self.indent(event.key() == Qt.Key.Key_Backtab or bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier))
            return
        if event.key() == Qt.Key.Key_Backspace and not cursor.hasSelection() and pos > 0:
            prior_state, _ = context(prefix[:-1])
            if prior_state == 'code' and prefix[-1:] in pairs and pairs[prefix[-1]] == next_char:
                cursor.beginEditBlock()
                cursor.deletePreviousChar()
                cursor.deleteChar()
                cursor.endEditBlock()
                self.setTextCursor(cursor)
                return
        if char in pairs and state == 'code':
            selected = cursor.selectedText().replace('\u2029', '\n')
            cursor.beginEditBlock()
            start = cursor.selectionStart()
            cursor.insertText(char + selected + pairs[char])
            if selected:
                end = cursor.position()-1
                cursor.setPosition(start+1)
                cursor.setPosition(end, QTextCursor.MoveMode.KeepAnchor)
            else:
                cursor.movePosition(QTextCursor.MoveOperation.Left)
            cursor.endEditBlock()
            self.setTextCursor(cursor)
            return
        if char in (')', ']', '}', '"', "'") and not cursor.hasSelection():
            if char == '}' and state == 'code' and not prefix.rsplit('\n', 1)[-1].strip():
                indent = ''
                if braces:
                    opening_line = prefix[:braces[-1]].rsplit('\n', 1)[-1]
                    indent = opening_line[:len(opening_line)-len(opening_line.lstrip(' \t'))]
                cursor.beginEditBlock()
                cursor.movePosition(QTextCursor.MoveOperation.StartOfBlock, QTextCursor.MoveMode.KeepAnchor)
                cursor.insertText(indent + ('' if next_char == '}' else '}'))
                if next_char == '}':
                    cursor.movePosition(QTextCursor.MoveOperation.Right)
                cursor.endEditBlock()
                self.setTextCursor(cursor)
                return
            if next_char == char and ((state == 'code' and char in ')]}') or (state == char and not escaped(prefix))):
                cursor.movePosition(QTextCursor.MoveOperation.Right)
                self.setTextCursor(cursor)
                return
        super().keyPressEvent(event)

    def newline(self, cursor):
        cursor.beginEditBlock()
        if cursor.hasSelection():
            cursor.removeSelectedText()
        left = QTextCursor(cursor)
        left.movePosition(QTextCursor.MoveOperation.StartOfBlock, QTextCursor.MoveMode.KeepAnchor)
        before = left.selectedText()
        indentation = re.match(r'[ \t]*', before)[0]
        prefix = QTextCursor(cursor)
        prefix.setPosition(0, QTextCursor.MoveMode.KeepAnchor)
        state, _ = context(prefix.selectedText().replace('\u2029', '\n'))
        opens = state == 'code' and before.rstrip().endswith('{')
        inner = indentation + ('    ' if opens else '')
        right = QTextCursor(cursor)
        right.movePosition(QTextCursor.MoveOperation.EndOfBlock, QTextCursor.MoveMode.KeepAnchor)
        after = right.selectedText()
        if opens and after.lstrip().startswith('}'):
            whitespace = len(after)-len(after.lstrip(' \t'))
            for _ in range(whitespace):
                cursor.deleteChar()
            cursor.insertText('\n' + inner)
            destination = cursor.position()
            cursor.insertText('\n' + indentation)
            cursor.setPosition(destination)
        else:
            cursor.insertText('\n' + inner)
        cursor.endEditBlock()
        self.setTextCursor(cursor)

    def indent(self, backwards=False):
        cursor = self.textCursor()
        if not cursor.hasSelection() and not backwards:
            cursor.insertText(' ' * (4 - cursor.positionInBlock() % 4))
            self.setTextCursor(cursor)
            return
        first = self.document().findBlock(cursor.selectionStart())
        last = self.document().findBlock(cursor.selectionEnd())
        if cursor.hasSelection() and cursor.selectionEnd() == last.position() and last != first:
            last = last.previous()
        start = first.position()
        original_first = first.text()
        lines = []
        block = first
        while block.isValid():
            line = block.text()
            if backwards:
                count = 1 if line.startswith('\t') else min(4, len(line)-len(line.lstrip(' ')))
                line = line[count:]
            else:
                line = '    '+line
            lines.append(line)
            if block == last:
                break
            block = block.next()
        had_selection = cursor.hasSelection()
        old_column = cursor.positionInBlock()
        cursor.beginEditBlock()
        cursor.setPosition(start)
        cursor.setPosition(last.position()+len(last.text().encode('utf-16-le'))//2, QTextCursor.MoveMode.KeepAnchor)
        cursor.insertText('\n'.join(lines))
        end = cursor.position()
        cursor.endEditBlock()
        if had_selection:
            cursor.setPosition(start)
            cursor.setPosition(end, QTextCursor.MoveMode.KeepAnchor)
        else:
            cursor.setPosition(start + max(0, old_column - (len(original_first)-len(lines[0]))))
        self.setTextCursor(cursor)

    def gutter_width(self):
        return 18 + self.fontMetrics().horizontalAdvance('9') * max(2, len(str(self.blockCount())))

    def update_gutter_width(self, *_):
        self.setViewportMargins(self.gutter_width(), 0, 0, 0)

    def update_gutter(self, rect, dy):
        if dy:
            self.gutter.scroll(0, dy)
        else:
            self.gutter.update(0, rect.y(), self.gutter.width(), rect.height())
        if rect.contains(self.viewport().rect()):
            self.update_gutter_width()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        rect = self.contentsRect()
        self.gutter.setGeometry(QRect(rect.left(), rect.top(), self.gutter_width(), rect.height()))

    def paint_gutter(self, event):
        painter = QPainter(self.gutter)
        painter.fillRect(event.rect(), QColor('#f3f6fa'))
        block = self.firstVisibleBlock()
        number = block.blockNumber()
        top = round(self.blockBoundingGeometry(block).translated(self.contentOffset()).top())
        while block.isValid() and top <= event.rect().bottom():
            height = round(self.blockBoundingRect(block).height())
            if block.isVisible() and top + height >= event.rect().top():
                painter.setPen(QColor('#8794a7'))
                painter.drawText(0, top, self.gutter.width()-9, height, Qt.AlignmentFlag.AlignRight, str(number+1))
            top += height
            block = block.next()
            number += 1

    def mark(self, line=0, column=1, color='#fef3c7'):
        block = self.document().findBlockByNumber(line-1)
        if line <= 0 or not block.isValid():
            self._execution_cursor = None
            self.setExtraSelections([])
            self.markChanged.emit(False)
            return
        selection = QTextEdit.ExtraSelection()
        selection.format.setBackground(QColor(color))
        selection.format.setProperty(QTextCharFormat.Property.FullWidthSelection, True)
        selection.cursor = QTextCursor(block)
        selection.cursor.clearSelection()
        cursor = QTextCursor(block)
        cursor.movePosition(QTextCursor.MoveOperation.Right, QTextCursor.MoveMode.MoveAnchor,
                            min(column-1, max(0, block.length()-1)))
        self._execution_cursor = cursor
        self.setExtraSelections([selection])
        self.markChanged.emit(True)

    def jump_to_execution(self):
        if self._execution_cursor is None:
            return
        self.setTextCursor(self._execution_cursor)
        self.ensureCursorVisible()
        self.setFocus()
