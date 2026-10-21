from PySide6.QtWidgets import QPlainTextEdit, QPushButton
from cvisualizer.window import MainWindow


def test_startup_notice_explains_fallback_and_opens_editable_template(app):
    window = MainWindow()
    window.show_linked_list_notice()
    dialog = window.linked_list_notice
    assert dialog.isVisible()
    assert '普通结构体' in dialog.description.text()
    assert '自定义' in dialog.description.text()
    preview = dialog.findChild(QPlainTextEdit)
    assert 'struct LNode *next;' in preview.toPlainText()
    buttons = {button.text(): button for button in dialog.findChildren(QPushButton)}
    buttons['导入单链表模板'].click()
    assert not dialog.isVisible()
    assert 'CreateList_H' in window.editor.toPlainText()
    assert 'cin >> p->data' in window.editor.toPlainText()
    assert not window.editor.isReadOnly()
    assert window.path is None
    window.close()


def test_notice_close_keeps_current_code(app):
    window = MainWindow()
    before = window.editor.toPlainText()
    window.show_linked_list_notice()
    window.linked_list_notice.reject()
    assert window.editor.toPlainText() == before
    window.close()


def test_heap_addresses_are_not_visible_value_labels():
    from cvisualizer.value_format import display
    from cvisualizer.pointers import Pointer
    heap_pointer = Pointer(17, None, 'struct N', '堆#17')
    assert display(heap_pointer) == '指向节点'
    assert str(heap_pointer) == '&堆#17'
    assert display(Pointer(None, None, 'struct N', '')) == 'NULL'
    assert display(Pointer(1, None, 'int', 'x')) == '&x'
