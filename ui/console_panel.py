""" The output console
A read-only, always-visible panel that displays the session log with a colour
per level. It only ever reads from the LogManager so it doesn't keep any log
state of its own, and it never clears unless the user asks it to """

from __future__ import annotations

import html

from PyQt6.QtGui import QTextCursor
from PyQt6.QtWidgets import QHBoxLayout, QPushButton, QTextEdit, QVBoxLayout, QWidget

from core.log_manager import LogEntry, LogManager
from ui.theme import CONSOLE_COLOURS


class ConsolePanel(QWidget):
    def __init__(self, log_manager: LogManager, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._log_manager = log_manager

        self._text = QTextEdit()
        self._text.setReadOnly(True)
        self._text.setLineWrapMode(QTextEdit.LineWrapMode.NoWrap)

        clear_button = QPushButton("Clear Log")
        clear_button.clicked.connect(self._log_manager.clear)

        button_row = QHBoxLayout()
        button_row.addStretch()
        button_row.addWidget(clear_button)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.addWidget(self._text)
        layout.addLayout(button_row)

        for entry in self._log_manager.entries:
            self._append(entry)

        self._log_manager.entry_added.connect(self._append)
        self._log_manager.cleared.connect(self._text.clear)

    def _append(self, entry: LogEntry) -> None:
        colour = CONSOLE_COLOURS.get(entry.level, "#d4d4d4")
        safe_text = html.escape(entry.text)
        line = (
            f'<span style="color:#6b6b6b">[{entry.time_str}]</span> '
            f'<span style="color:{colour}">{safe_text}</span>'
        )
        self._text.append(line)
        self._text.moveCursor(QTextCursor.MoveOperation.End)
