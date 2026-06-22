
from __future__ import annotations

import sys

from PyQt6.QtWidgets import QApplication

from ui.fonts import register_bundled_fonts
from ui.main_window import MainWindow
from ui.theme import DARK_QSS


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("Friga")
    app.setStyleSheet(DARK_QSS)
    register_bundled_fonts()

    window = MainWindow()
    window.show()

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
