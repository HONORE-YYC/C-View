"""The complete desktop workflow. C execution stays in controller/engine."""
from pathlib import Path

from PySide6.QtCore import Qt, QTimer, QAbstractAnimation
from PySide6.QtGui import QColor, QFont, QAction, QKeySequence
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QComboBox, QSlider, QSplitter, QPlainTextEdit, QTableWidget, QTableWidgetItem,
    QHeaderView, QFileDialog, QMessageBox, QDialog, QFrame, QAbstractItemView,
)

from .bindings import BindingDialog, read_bindings, write_bindings
from .controller import Controller
from .editor import CodeEditor
from .language import CError
from .views import MemoryView, display


EXAMPLES = Path(__file__).parent / 'examples'
STATES = {'ready': '准备就绪', 'running': '演示中', 'paused': '已暂停', 'seeking': '定位中',
          'stopped': '已停止', 'finished': '已完成', 'error': '执行错误'}
STYLE = '''
QMainWindow, QDialog { background: #f3f6fa; }
QWidget { color: #26354d; font-family: "Microsoft YaHei UI", "Noto Sans CJK SC", sans-serif; font-size: 12px; }
QFrame#panel { background: white; border: 1px solid #dce3ed; border-radius: 9px; }
QLabel#heading { color: #12243c; font-size: 15px; font-weight: 700; padding: 4px 0; }
QLabel#muted { color: #718096; font-size: 11px; }
QPushButton { background: white; border: 1px solid #cdd8e4; border-radius: 6px; padding: 8px 12px; }
QPushButton:hover { background: #edf5f5; border-color: #0f766e; }
QPushButton:disabled { color: #a0aabd; background: #f2f5f8; border-color: #e0e6ed; }
QPushButton#primary { color: white; background: #0f766e; border-color: #0f766e; font-weight: 700; }
QPushButton#primary:hover { background: #115e59; }
QComboBox { background: white; border: 1px solid #cdd8e4; border-radius: 5px; padding: 7px; }
QPlainTextEdit, QGraphicsView, QTableWidget { background: white; border: none; selection-background-color: #cceae7; }
QPlainTextEdit { font-family: "Consolas", "Microsoft YaHei UI", monospace; font-size: 13px; }
QHeaderView::section { background: #f1f5f9; color: #64748b; padding: 5px; border: none; }
QTableWidget { gridline-color: #edf1f5; }
QSplitter::handle { background: #e5ebf1; }
QSlider::groove:horizontal { height: 5px; background: #dce5ed; border-radius: 2px; }
QSlider::handle:horizontal { background: #0f766e; width: 13px; margin: -4px 0; border-radius: 6px; }
'''


def panel(title, subtitle=''):
    widget = QFrame()
    widget.setObjectName('panel')
    layout = QVBoxLayout(widget)
    layout.setContentsMargins(14, 12, 14, 12)
    heading = QLabel(title)
    heading.setObjectName('heading')
    layout.addWidget(heading)
    if subtitle:
        label = QLabel(subtitle)
        label.setObjectName('muted')
        label.setWordWrap(True)
        layout.addWidget(label)
    return widget, layout


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle('C View · C 语言与数据结构可视化')
        self.resize(1480, 920)
        self.setMinimumSize(1060, 700)
        self.setStyleSheet(STYLE)
        self.controller = None
        self.bindings = []
        self.path = None
        self._loading = False
        self._bindings_dirty = False
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.on_tick)
        central = QWidget()
        root = QVBoxLayout(central)
        root.setContentsMargins(18, 14, 18, 12)
        root.setSpacing(12)
        self.setCentralWidget(central)

        header = QHBoxLayout()
        title = QLabel('C View')
        title.setStyleSheet('font-size: 26px; font-weight: 800; color: #0f766e;')
        header.addWidget(title)
        subtitle = QLabel('代码执行，看得见  /  C 语言与数据结构学习')
        subtitle.setObjectName('muted')
        header.addWidget(subtitle)
        header.addStretch()
        self.examples = QComboBox()
        self.examples.setMinimumWidth(180)
        self.examples.addItem('选择可编辑示例…', None)
        for filename, label in [('basics.c', '01 变量、运算与循环'), ('list.c', '02 顺序表插入与删除'),
                                ('stack.c', '03 栈的入栈与出栈'), ('queue.c', '04 循环队列与回绕'),
                                ('mixed.c', '05 同一程序，多种结构'), ('macros.c', '06 宏与随机数'),
                                ('animation.c', '07 赋值与下标动画')]:
            self.examples.addItem(label, filename)
        self.examples.activated.connect(self.open_example)
        header.addWidget(self.examples)
        for label, callback in [('新建', self.new_file), ('打开', self.open_file), ('保存', self.save_file)]:
            button = QPushButton(label)
            button.clicked.connect(callback)
            header.addWidget(button)
        root.addLayout(header)

        controls = QHBoxLayout()
        self.buttons = {}
        for key, text, callback in [('play', '完整演示', self.play), ('pause', '暂停', self.pause),
                                    ('stop', '停止', self.stop), ('step', '单步 →', self.step),
                                    ('reset', '重置', self.reset)]:
            button = QPushButton(text)
            button.clicked.connect(callback)
            if key == 'play':
                button.setObjectName('primary')
            self.buttons[key] = button
            controls.addWidget(button)
        self.locate_button = QPushButton('定位光标所在语句')
        self.locate_button.clicked.connect(self.locate_cursor)
        controls.addWidget(self.locate_button)
        controls.addStretch()
        self.speed_label = QLabel('间隔 600 ms')
        self.speed = QSlider(Qt.Orientation.Horizontal)
        self.speed.setRange(100, 2000)
        self.speed.setValue(600)
        self.speed.setFixedWidth(120)
        self.speed.valueChanged.connect(self.speed_changed)
        controls.addWidget(self.speed_label)
        controls.addWidget(self.speed)
        root.addLayout(controls)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)
        left, left_layout = panel('01 / C 代码', '输入 C 代码，逐步观察变量与数据结构的变化')
        self.editor = CodeEditor()
        self.editor.textChanged.connect(self.code_changed)
        self.jump_button = QPushButton('跳转到当前执行位置')
        self.jump_button.setEnabled(False)
        self.jump_button.setToolTip('查看当前高亮的代码，不执行语句或改变演示进度')
        self.jump_button.clicked.connect(self.editor.jump_to_execution)
        self.editor.markChanged.connect(self.jump_button.setEnabled)
        left_layout.addWidget(self.jump_button)
        left_layout.addWidget(self.editor, 1)
        self.filename_label = QLabel('未保存的代码')
        self.filename_label.setObjectName('muted')
        left_layout.addWidget(self.filename_label)
        splitter.addWidget(left)

        middle, middle_layout = panel('02 / 运行状态', '灰框：未赋值  绿框：已赋值  蓝边：读取  橙边：写入')
        self.variables = QTableWidget(0, 3)
        self.variables.setHorizontalHeaderLabels(['变量', '类型', '当前值'])
        self.variables.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.variables.verticalHeader().hide()
        self.variables.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.variables.setFixedHeight(112)
        self.variables.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        middle_layout.addWidget(self.variables)
        binding_row = QHBoxLayout()
        binding_row.addWidget(QLabel('变量、数组与数据结构'))
        binding_row.addStretch()
        self.binding_button = QPushButton('结构绑定')
        self.binding_button.clicked.connect(self.edit_bindings)
        binding_row.addWidget(self.binding_button)
        middle_layout.addLayout(binding_row)
        self.visuals = MemoryView()
        middle_layout.addWidget(self.visuals, 1)
        splitter.addWidget(middle)

        right, right_layout = panel('03 / 执行过程', '定位会先执行前置代码，到目标之前暂停。')
        self.step_label = QLabel('STEP 0000')
        self.step_label.setStyleSheet('color: #0f766e; font-size: 18px; font-weight: 700;')
        right_layout.addWidget(self.step_label)
        self.explanation = QLabel('点击「完整演示」自动播放，或点击「单步」观察每一次状态变化。')
        self.explanation.setWordWrap(True)
        self.explanation.setMinimumHeight(75)
        self.explanation.setTextFormat(Qt.TextFormat.PlainText)
        right_layout.addWidget(self.explanation)
        self.next_label = QLabel('尚未开始')
        self.next_label.setWordWrap(True)
        self.next_label.setTextFormat(Qt.TextFormat.PlainText)
        self.next_label.setObjectName('muted')
        right_layout.addWidget(self.next_label)
        right_layout.addWidget(QLabel('指定语句（同一行可选择不同语句）'))
        self.targets = QComboBox()
        self.targets.setMinimumWidth(180)
        self.targets.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        right_layout.addWidget(self.targets)
        target_row = QHBoxLayout()
        refresh = QPushButton('刷新语句')
        refresh.clicked.connect(self.prepare_targets)
        self.seek_button = QPushButton('运行到此处')
        self.seek_button.clicked.connect(self.seek)
        target_row.addWidget(refresh)
        target_row.addWidget(self.seek_button)
        right_layout.addLayout(target_row)
        right_layout.addWidget(QLabel('程序输出'))
        self.output = QPlainTextEdit()
        self.output.setReadOnly(True)
        self.output.setMaximumHeight(125)
        self.output.setPlaceholderText('printf 的输出会出现在这里')
        right_layout.addWidget(self.output)
        right_layout.addWidget(QLabel('步骤记录（最近 300 行）'))
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumBlockCount(300)
        right_layout.addWidget(self.log, 1)
        splitter.addWidget(right)
        splitter.setSizes([450, 620, 330])
        root.addWidget(splitter, 1)

        self.status = QLabel('准备就绪')
        self.status.setTextFormat(Qt.TextFormat.PlainText)
        self.status.setWordWrap(True)
        root.addWidget(self.status)
        footer = QLabel('教学子集：变量、数组、循环、#define、printf、abs/rand/srand。兼容 cstdlib / stdlib.h；暂不支持指针与 struct，浮点按宿主精度近似。')
        footer.setObjectName('muted')
        footer.setWordWrap(True)
        root.addWidget(footer)

        for key, callback in [(QKeySequence.StandardKey.Open, self.open_file),
                              (QKeySequence.StandardKey.Save, self.save_file)]:
            action = QAction(self)
            action.setShortcut(key)
            action.triggered.connect(callback)
            self.addAction(action)
        self.visuals.motion.settled.connect(self.refresh)
        start = EXAMPLES / 'basics.c'
        self.load_code(start.read_text(encoding='utf-8') if start.exists() else 'int x = 1;\nx = x + 2;\n', [])

    def load_code(self, code, bindings, path=None):
        self.timer.stop()
        self.controller = None
        self.bindings, self.path = list(bindings), Path(path) if path else None
        self._loading = True
        self.editor.setReadOnly(False)
        self.editor.setPlainText(code)
        self.editor.document().setModified(False)
        self._loading = False
        self._bindings_dirty = False
        self.reset()
        self.filename_label.setText(str(self.path) if self.path else '未保存的代码')

    def code_changed(self):
        if self._loading:
            return
        self.timer.stop()
        self.controller = None
        self.clear_display()
        self.status.setText('代码已修改，运行时将从头开始')
        self.refresh()

    def clear_display(self):
        self.editor.mark()
        self.targets.clear()
        self.log.clear()
        self.output.clear()
        self.variables.setRowCount(0)
        self.visuals.render({}, self.bindings)
        self.step_label.setText('STEP 0000')
        self.explanation.setText('点击「完整演示」或「单步」开始。')
        self.next_label.setText('尚未开始')

    def ensure_controller(self):
        if self.controller is not None:
            return True
        try:
            self.controller = Controller(self.editor.toPlainText())
            self.targets.clear()
            for loc in self.controller.targets:
                one_line = loc.text.replace('\n', ' ')
                self.targets.addItem(f'{loc.line}:{loc.column}  {one_line[:70]}', loc)
        except CError as error:
            self.status.setText(str(error))
            self.editor.mark(error.line, error.column or 1, '#fee2e2')
            return False
        return True

    def prepare_targets(self):
        return self.ensure_controller()

    def prepare_restart(self):
        if self.controller and self.controller.state in ('finished', 'stopped', 'error'):
            self.visuals.render({}, self.bindings)
            self.log.clear()
            self.output.clear()

    def play(self):
        if self.ensure_controller():
            if self.visuals.motion.busy and self.controller.state == 'finished':
                self.visuals.motion.resume()
                self.refresh()
                return
            self.prepare_restart()
            self.visuals.motion.resume()
            self.controller.play()
            self.refresh()

    def pause(self):
        if self.controller:
            self.visuals.motion.pause()
            self.controller.pause()
            self.refresh()

    def stop(self):
        if self.controller:
            self.visuals.motion.finish()
            self.controller.stop()
            self.refresh()

    def step(self):
        if self.visuals.motion.busy:
            return
        if self.ensure_controller():
            self.prepare_restart()
            event = self.controller.step()
            self.record([event] if event else [])
            self.refresh()

    def reset(self):
        self.timer.stop()
        self.controller = None
        self.clear_display()
        self.status.setText('已重置 · 代码与结构绑定保留')
        self.refresh()

    def seek(self):
        if self.ensure_controller() and self.targets.currentData() is not None:
            self.visuals.motion.finish()
            self.prepare_restart()
            self.controller.seek(self.targets.currentData())
            self.refresh()

    def locate_cursor(self):
        line = self.editor.textCursor().blockNumber() + 1
        column = self.editor.textCursor().positionInBlock() + 1
        if not self.ensure_controller():
            return
        candidates = [(i, self.targets.itemData(i)) for i in range(self.targets.count())
                      if self.targets.itemData(i).line == line]
        if not candidates:
            self.status.setText('当前行没有可执行语句，请将光标放在声明、运算或循环条件所在行。')
            return
        preceding = [(i, loc) for i, loc in candidates if loc.column <= column]
        index = max(preceding, key=lambda pair: pair[1].column)[0] if preceding else candidates[0][0]
        self.targets.setCurrentIndex(index)
        self.seek()

    def speed_changed(self, value):
        self.speed_label.setText(f'间隔 {value} ms')
        if self.timer.isActive() and self.controller.state == 'running':
            self.timer.setInterval(value)

    def on_tick(self):
        if self.controller:
            if self.visuals.motion.busy:
                return
            seeking = self.controller.state == 'seeking'
            self.record(self.controller.tick())
            self.refresh(animate=not seeking)

    def record(self, events):
        for event in events:
            self.log.appendPlainText(f'{event.number:04d}  L{event.line}:{event.column}  {event.message[:240]}')

    def refresh(self, animate=True):
        c = self.controller
        state = c.state if c else 'ready'
        active = state in ('running', 'seeking')
        self.editor.setReadOnly(state in ('running', 'seeking', 'paused'))
        busy = self.visuals.motion.busy
        animation_paused = self.visuals.motion.animation.state() == QAbstractAnimation.State.Paused
        self.buttons['pause'].setEnabled(active or busy)
        self.buttons['stop'].setEnabled(state in ('running', 'seeking', 'paused') or busy)
        self.buttons['step'].setEnabled(not active and not busy)
        self.buttons['play'].setEnabled(not active and (not busy or state == 'paused' or animation_paused))
        self.buttons['play'].setText('继续演示' if state == 'paused' or animation_paused else '完整演示')
        self.locate_button.setEnabled(not active)
        self.seek_button.setEnabled(not active)
        if active:
            interval = 10 if state == 'seeking' else self.speed.value()
            if not self.timer.isActive() or self.timer.interval() != interval:
                self.timer.start(interval)
        else:
            self.timer.stop()
        if not c:
            return
        self.status.setText(f'{STATES[state]}  ·  {c.message}')
        event = c.engine.last
        snapshot = c.engine.runtime.snapshot()
        rows = [(name, cell) for name, cell in snapshot.items() if not isinstance(cell['value'], list)]
        self.variables.setRowCount(len(rows))
        for row, (name, cell) in enumerate(rows):
            same_cell = event and event.variables.get(name, {}).get('identity') == cell['identity']
            for col, value in enumerate([name, cell['type'], display(cell['value'])]):
                item = QTableWidgetItem(value)
                if same_cell and (name, None) in event.writes:
                    item.setBackground(QColor('#fef3c7'))
                elif same_cell and (name, None) in event.reads:
                    item.setBackground(QColor('#dbeafe'))
                self.variables.setItem(row, col, item)
        self.visuals.render(snapshot, self.bindings, event, pointers=c.engine.index_markers(),
                            index_lanes=c.engine.index_lanes,
                            duration=max(320, min(1100, int(self.speed.value()*.85))), animate=animate)
        if self.visuals.motion.busy:
            self.buttons['step'].setEnabled(False)
            self.buttons['pause'].setEnabled(True)
            self.buttons['stop'].setEnabled(True)
            self.buttons['play'].setEnabled(not active and (state == 'paused' or animation_paused))
        if event:
            self.step_label.setText(f'STEP {event.number:04d}')
            changes = []
            for name, index in dict.fromkeys(event.writes):
                value = event.variables.get(name, {}).get('value')
                if index is not None and isinstance(value, list):
                    value = value[index]
                text = f'{name}' + (f'[{index}]' if index is not None else '')
                if not isinstance(value, list):
                    changes.append(f'{text} = {display(value)}')
            self.explanation.setText(f'第 {event.line} 行 · {event.message[:320]}' +
                                     ('\n\n'+'\n'.join(changes[:8]) if changes else ''))
            self.output.setPlainText(c.engine.runtime.output)
            self.editor.mark(event.line, event.column)
        pending = c.engine.peek() if state != 'error' else None
        if pending:
            self.next_label.setText(f'下一步 {pending.line}:{pending.column}  {pending.location.text[:180]}')
            if state == 'paused' and '尚未执行' in c.message:
                self.editor.mark(pending.line, pending.column, '#dbeafe')
        elif state == 'finished':
            self.next_label.setText('执行结束。再次播放或单步将从头开始。')
        if c.error:
            self.editor.mark(c.error.line, c.error.column or 1, '#fee2e2')

    def edit_bindings(self):
        self.pause()
        dialog = BindingDialog(self.bindings, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.bindings = dialog.result_bindings()
            self._bindings_dirty = True
            self.refresh()

    def can_discard(self):
        if not self.editor.document().isModified() and not self._bindings_dirty:
            return True
        result = QMessageBox.question(self, '保存修改', '当前代码或绑定尚未保存，是否先保存？',
                                      QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard |
                                      QMessageBox.StandardButton.Cancel)
        if result == QMessageBox.StandardButton.Cancel:
            return False
        return self.save_file() if result == QMessageBox.StandardButton.Save else True

    def new_file(self):
        self.pause()
        if self.can_discard():
            self.load_code('', [])

    def open_example(self, index):
        filename = self.examples.itemData(index)
        if not filename:
            return
        self.pause()
        if self.can_discard():
            self.read_file(EXAMPLES / filename, example=True)

    def open_file(self):
        self.pause()
        if not self.can_discard():
            return
        filename, _ = QFileDialog.getOpenFileName(self, '打开 C 代码', '', 'C 代码 (*.c);;所有文件 (*)')
        if filename:
            self.read_file(Path(filename))

    def read_file(self, path, example=False):
        try:
            if path.stat().st_size > 256000:
                raise ValueError('代码文件过大；请使用小型教学示例')
            code = path.read_text(encoding='utf-8-sig')
            bindings = read_bindings(path.with_suffix('.cview.json'))
        except (OSError, UnicodeError, ValueError) as error:
            QMessageBox.warning(self, '无法打开文件', str(error))
            return
        self.load_code(code, bindings, None if example else path)

    def save_to(self, path):
        path = Path(path)
        path.write_text(self.editor.toPlainText(), encoding='utf-8')
        write_bindings(path.with_suffix('.cview.json'), self.bindings)
        self.path = path
        self.editor.document().setModified(False)
        self._bindings_dirty = False
        self.filename_label.setText(str(path))

    def save_file(self):
        filename = str(self.path) if self.path else ''
        if not filename:
            filename, _ = QFileDialog.getSaveFileName(self, '保存 C 代码和结构绑定', 'demo.c', 'C 代码 (*.c)')
        if not filename:
            return False
        try:
            self.save_to(filename)
        except (OSError, ValueError) as error:
            QMessageBox.warning(self, '保存失败', str(error))
            return False
        self.status.setText('已保存 C 代码与同名 .cview.json 结构绑定')
        return True

    def closeEvent(self, event):
        self.pause()
        if self.can_discard():
            self.timer.stop()
            self.visuals.motion.clear()
            event.accept()
        else:
            event.ignore()
