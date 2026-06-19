
from __future__ import annotations

import sys

from PyQt6.QtWidgets import QApplication

from ui.main_window import MainWindow
from ui.theme import DARK_QSS


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("Friga")
    app.setStyleSheet(DARK_QSS)

    window = MainWindow()
    window.show()

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
