import sys


def main():
    from PySide6.QtWidgets import QApplication
    from PySide6.QtGui import QFont
    from PySide6.QtCore import QTimer
    from .window import MainWindow

    app = QApplication(sys.argv)
    app.setApplicationName('C View')
    app.setFont(QFont('Microsoft YaHei UI', 10))
    window = MainWindow()
    window.show()
    QTimer.singleShot(0, window.show_linked_list_notice)
    return app.exec()


if __name__ == '__main__':
    sys.exit(main())
