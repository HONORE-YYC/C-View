import sys


def main():
    from PySide6.QtWidgets import QApplication
    from PySide6.QtGui import QFont
    from .window import MainWindow

    app = QApplication(sys.argv)
    app.setApplicationName('C View')
    app.setFont(QFont('Microsoft YaHei UI', 10))
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == '__main__':
    sys.exit(main())
