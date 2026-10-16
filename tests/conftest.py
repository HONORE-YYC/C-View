"""Keep Qt alive until widgets and their Python callbacks are destroyed."""
import gc
import os

import pytest

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')


@pytest.fixture(scope='session')
def app():
    from PySide6.QtWidgets import QApplication
    application = QApplication.instance() or QApplication([])
    yield application
    gc.collect()


@pytest.fixture(autouse=True)
def dispose_qt_widgets(request):
    if 'app' not in request.fixturenames:
        yield
        return
    application = request.getfixturevalue('app')
    yield
    from PySide6.QtCore import QCoreApplication, QEvent
    # close() only hides a widget. Destroy C++ objects and their signal callbacks
    # while Python and QApplication are still fully alive, including on failures.
    for widget in application.topLevelWidgets():
        widget.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    gc.collect()
