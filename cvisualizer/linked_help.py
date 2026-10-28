"""Startup guidance for automatically recognized structures and templates."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPlainTextEdit, QPushButton


TEMPLATE = """typedef int ElemType;
typedef struct LNode {
    ElemType data;
    struct LNode *next;
} LNode, *LinkList;"""

STACK_TEMPLATE = """typedef int SElemType;
typedef struct {
    SElemType *base;
    SElemType *top;
    int stacksize;
} SqStack;"""


class LinkedListNotice(QDialog):
    def __init__(self, window):
        super().__init__(window)
        self.setWindowTitle('标准模板与数据结构识别说明')
        self.setWindowModality(Qt.WindowModality.WindowModal)
        self.setMinimumWidth(560)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 20, 22, 20)
        layout.setSpacing(14)
        self.description = QLabel(
            '主题切换按钮旁的“标准模板”可一键导入具有特殊演示效果的标准代码。'
            '目前提供单链表构建和顺序栈构建，导入代码区后可自由编辑。\n\n'
            '单链表节点请使用下方标准格式：恰好包含一个数值数据成员，'
            '以及一个指向自身结构体的指针成员。\n'
            '顺序栈依次定义两个同类型数值指针（栈底、栈顶）和一个 int 容量字段。\n\n'
            '结构体名、类型别名、成员名和变量名均可自定义，修改后需保持引用一致。'
            '不符合对应格式的结构体不能自动识别为该数据结构，会按普通结构体展示。')
        self.description.setWordWrap(True)
        layout.addWidget(self.description)
        preview = QPlainTextEdit('// 单链表\n'+TEMPLATE+'\n\n// 顺序栈\n'+STACK_TEMPLATE)
        preview.setReadOnly(True)
        preview.setMinimumHeight(210)
        layout.addWidget(preview)
        hint = QLabel('每种节点类型最先声明的链表指针作为头指针。\n'
                      '关闭本提示后代码区保持空白；需要时再从“标准模板”或示例菜单导入代码。')
        hint.setWordWrap(True)
        layout.addWidget(hint)
        buttons = QHBoxLayout()
        buttons.addStretch()
        close = QPushButton('知道了')
        close.clicked.connect(self.accept)
        buttons.addWidget(close)
        example = QPushButton('导入单链表模板')
        example.setObjectName('primary')
        example.clicked.connect(self.open_example)
        buttons.addWidget(example)
        stack = QPushButton('导入顺序栈模板')
        stack.clicked.connect(self.open_stack)
        buttons.addWidget(stack)
        layout.addLayout(buttons)

    def open_example(self):
        window = self.parentWidget()
        if window.open_template():
            self.accept()

    def open_stack(self):
        if self.parentWidget().open_template('sequential_stack.cpp'):
            self.accept()
