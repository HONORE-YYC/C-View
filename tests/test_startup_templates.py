from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QMessageBox, QPushButton
from cvisualizer.window import MainWindow
from cvisualizer.engine import Engine


def test_startup_editor_is_empty_and_notice_does_not_load_code(app):
    window = MainWindow()
    assert window.editor.toPlainText() == ''
    assert window.path is None and window.controller is None
    assert not window.editor.document().isModified()
    window.show_linked_list_notice()
    assert '标准模板' in window.linked_list_notice.description.text()
    window.linked_list_notice.accept()
    assert window.editor.toPlainText() == ''
    window.close()


def test_theme_saved_and_restored_across_windows(app, tmp_path, monkeypatch):
    import cvisualizer.window as module
    path = str(tmp_path / 'restart.ini')
    monkeypatch.setattr(module, 'QSettings', lambda *args: QSettings(path, QSettings.Format.IniFormat))
    first = MainWindow()
    first.theme_button.click()
    assert first.dark_mode
    first.close()
    second = MainWindow()
    assert second.dark_mode and second.theme_button.isChecked()
    assert second.visuals.backgroundBrush().color().name() == '#000000'
    assert second.editor.toPlainText() == ''
    second.theme_button.click()
    second.close()
    third = MainWindow()
    assert not third.dark_mode
    assert third.visuals.backgroundBrush().color().name() == '#ffffff'
    third.close()


def test_template_menu_imports_runnable_editable_linked_list(app):
    window = MainWindow()
    action = window.template_button.menu().actions()[0]
    assert '单链表' in action.text()
    action.trigger()
    code = window.editor.toPlainText()
    assert 'CreateList_H' in code and 'cin' in code
    assert not window.editor.isReadOnly() and window.path is None
    engine = Engine(code)
    engine.runtime.input_provider = lambda prompt: '1 2 3'
    while engine.peek():
        engine.step()
    assert '3 2 1' in engine.runtime.output
    assert len(engine.program.linked_types) == 1
    window.close()


def test_template_import_cancel_preserves_unsaved_code(app, monkeypatch):
    window = MainWindow()
    window.editor.setPlainText('int keep=7;')
    window.editor.document().setModified(True)
    monkeypatch.setattr(QMessageBox, 'question', lambda *args: QMessageBox.StandardButton.Cancel)
    window.template_button.menu().actions()[0].trigger()
    assert window.editor.toPlainText() == 'int keep=7;'
    assert window.editor.document().isModified()
    window.editor.document().setModified(False)
    window.close()


def test_stack_template_is_available_from_menu_and_startup_notice(app):
    window = MainWindow()
    action = next((a for a in window.template_button.menu().actions() if '顺序栈' in a.text()), None)
    assert action is not None
    action.trigger()
    assert 'SqStack' in window.editor.toPlainText()
    assert 'new SElemType[MAXSIZE]' in window.editor.toPlainText()
    assert not window.editor.isReadOnly() and window.path is None
    window.show_linked_list_notice()
    assert '顺序栈' in window.linked_list_notice.description.text()
    window.linked_list_notice.accept()
    window.close()
