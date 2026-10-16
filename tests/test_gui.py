import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

import pytest
from PySide6.QtWidgets import QApplication
from cvisualizer.window import MainWindow


@pytest.fixture(scope='module')
def app():
    return QApplication.instance() or QApplication([])


def test_window_steps_highlights_and_renders_arrays(app, tmp_path):
    w = MainWindow()
    w.load_code('int a[3]={1,2,3};\nint top=1;\na[top]++;', [])
    w.step()
    assert w.controller.engine.count == 1
    assert w.editor.isReadOnly()
    assert len(w.visuals.scene().items()) > 0
    w.play()
    w.pause()
    assert w.controller.state == 'paused'
    w.stop()
    assert not w.editor.isReadOnly()
    assert w.controller.state == 'stopped'
    path = tmp_path / 'demo.c'
    w.save_to(path)
    assert path.read_text(encoding='utf-8').startswith('int a')
    assert path.with_suffix('.cview.json').exists()
    w.reset()
    assert w.controller is None
    w.close()


def test_timer_callbacks_finish_and_report_errors(app):
    w = MainWindow()
    w.load_code('int x=1;\nx=1/0;', [])
    w.play()
    w.on_tick()
    w.on_tick()
    assert w.controller.state == 'error'
    assert '除零' in w.status.text()
    assert not w.timer.isActive()
    w.editor.document().setModified(False)
    w.close()


def test_editor_line_numbers_target_selection_and_snapshot(app, tmp_path):
    w = MainWindow()
    w.resize(1440, 900)
    w.show()
    w.load_code('int x=0;\nwhile(x<3){\n x++;\n}', [])
    w.prepare_targets()
    i = next(i for i in range(w.targets.count()) if w.targets.itemData(i).line == 3)
    w.targets.setCurrentIndex(i)
    w.seek()
    w.on_tick()
    assert w.controller.state == 'paused'
    assert w.controller.engine.runtime.snapshot()['x']['value'] == 0
    app.processEvents()
    image = w.grab()
    assert image.width() == 1440
    assert image.save(str(tmp_path / 'window.png'))
    w.editor.document().setModified(False)
    w.close()


def test_leaving_shadowed_array_scope_does_not_crash_display(app):
    w = MainWindow()
    w.load_code('int a[1]={0}; {int a[2]={0}; a[1]=2;}', [])
    w.step()
    w.step()
    w.step()
    assert w.controller.state == 'finished'
    assert w.controller.engine.runtime.snapshot()['a']['value'] == [0]
    assert w.controller.engine.last.variables['a']['value'] == [0, 2]
    w.close()
