""" Dark theme for the application """

from __future__ import annotations

from core.log_manager import LogLevel

CONSOLE_COLOURS: dict[LogLevel, str] = {
    LogLevel.SUCCESS: "#4ec9b0",
    LogLevel.ERROR: "#f44747",
    LogLevel.WARNING: "#dcdcaa",
    LogLevel.INFO: "#d4d4d4",
}

DARK_QSS = """
QMainWindow, QWidget {
    background-color: #1e1e1e;
    color: #d4d4d4;
    font-family: "Segoe UI", "Ubuntu", sans-serif;
    font-size: 13px;
}
QDockWidget {
    titlebar-close-icon: none;
    border: 1px solid #2d2d2d;
}
QDockWidget::title {
    background-color: #252526;
    padding: 6px 8px;
    font-weight: 600;
}
QPushButton {
    background-color: #0e639c;
    color: #ffffff;
    border: none;
    border-radius: 3px;
    padding: 6px 14px;
}
QPushButton:hover { background-color: #1177bb; }
QPushButton:pressed { background-color: #0d5689; }
QPushButton:disabled {
    background-color: #2d2d2d;
    color: #6b6b6b;
}
QTableWidget {
    background-color: #252526;
    alternate-background-color: #2a2a2b;
    gridline-color: #3c3c3c;
    selection-background-color: #094771;
    border: 1px solid #3c3c3c;
}
QHeaderView::section {
    background-color: #2d2d2d;
    color: #d4d4d4;
    padding: 4px;
    border: none;
    border-right: 1px solid #3c3c3c;
}
QTextEdit, QPlainTextEdit {
    background-color: #181818;
    color: #d4d4d4;
    border: 1px solid #3c3c3c;
    font-family: "Cascadia Mono", "Consolas", "Ubuntu Mono", monospace;
}
QStatusBar {
    background-color: #007acc;
    color: #ffffff;
}
"""
