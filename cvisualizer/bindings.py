"""Editable, portable structure bindings and their JSON sidecar format."""
from dataclasses import asdict
import json
from pathlib import Path

from PySide6.QtWidgets import (QDialog, QVBoxLayout, QLabel, QTableWidget, QTableWidgetItem,
                               QComboBox, QPushButton, QDialogButtonBox, QHBoxLayout, QMessageBox)

from .structures import Binding, KINDS


def read_bindings(path):
    path = Path(path)
    if not path.exists():
        return []
    if path.stat().st_size > 64000:
        raise ValueError('绑定文件超过 64000 字节')
    data = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(data, list) or len(data) > 64:
        raise ValueError('绑定文件必须为最多 64 项的 JSON 列表')
    result = []
    for item in data:
        if not isinstance(item, dict) or not all(isinstance(v, str) for v in item.values()):
            raise ValueError('绑定字段必须是字符串')
        try:
            binding = Binding(**item)
        except TypeError as error:
            raise ValueError('绑定文件字段不正确') from error
        if binding.kind not in KINDS or not binding.array or any(b.array == binding.array for b in result):
            raise ValueError('绑定类型、数组名或重复数组配置不正确')
        result.append(binding)
    return result


def write_bindings(path, bindings):
    Path(path).write_text(json.dumps([asdict(b) for b in bindings], ensure_ascii=False, indent=2), encoding='utf-8')


class BindingDialog(QDialog):
    def __init__(self, bindings, parent=None):
        super().__init__(parent)
        self.setWindowTitle('结构绑定 · 同一程序可显示多个结构')
        self.resize(860, 380)
        layout = QVBoxLayout(self)
        hint = QLabel('输入代码中的变量名。顺序表：长度；栈：top=-1 为空；队列：front 指向队头，rear 指向下个入队位置，预留一个空位。')
        hint.setWordWrap(True)
        layout.addWidget(hint)
        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(['数组名', '显示类型', '长度变量', 'top 变量', 'front 变量', 'rear 变量'])
        self.table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.table)
        row = QHBoxLayout()
        add = QPushButton('添加绑定')
        remove = QPushButton('删除选中绑定')
        add.clicked.connect(lambda: self.add_row(Binding('')))
        remove.clicked.connect(lambda: self.table.removeRow(self.table.currentRow()))
        row.addWidget(add)
        row.addWidget(remove)
        row.addStretch()
        layout.addLayout(row)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.validate)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        for binding in bindings:
            self.add_row(binding)

    def add_row(self, binding):
        row = self.table.rowCount()
        self.table.insertRow(row)
        for col, text in enumerate([binding.array, '', binding.length, binding.top, binding.front, binding.rear]):
            self.table.setItem(row, col, QTableWidgetItem(text))
        combo = QComboBox()
        for kind, label in KINDS.items():
            combo.addItem(label, kind)
        combo.setCurrentIndex(list(KINDS).index(binding.kind))
        self.table.setCellWidget(row, 1, combo)

    def result_bindings(self):
        result = []
        for row in range(self.table.rowCount()):
            values = [self.table.item(row, col).text().strip() for col in (0, 2, 3, 4, 5)]
            if values[0]:
                result.append(Binding(values[0], self.table.cellWidget(row, 1).currentData(), *values[1:]))
        return result

    def validate(self):
        result = self.result_bindings()
        names = [b.array for b in result]
        if len(names) != len(set(names)):
            QMessageBox.warning(self, '重复绑定', '同一个数组只能绑定一种显示类型。')
            return
        self.accept()
