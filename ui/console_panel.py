""" The output console + log search
Read-only, always-visible panel that shows the session log with a colour per level.
It only ever reads from the LogManager. The search box and sensitive-keyword buttons
above it filter the visible lines by keyword, which is handy for going back through a
session afterwards to see what got captured """

from __future__ import annotations

import html

from PyQt6.QtGui import QTextCursor
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from core.log_manager import LogEntry, LogManager
from ui.theme import CONSOLE_COLOURS

_KEYWORDS = ("password", "token", "username", "email", "credentials")


class ConsolePanel(QWidget):
    def __init__(self, log_manager: LogManager, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._log_manager = log_manager
        self._filter = ""

        self._search = QLineEdit()
        self._search.setPlaceholderText("Filter the log by keyword…")
        self._search.textChanged.connect(self._on_search)
        show_all = QPushButton("Show All")
        show_all.clicked.connect(self._show_all)

        search_row = QHBoxLayout()
        search_row.addWidget(QLabel("Filter:"))
        search_row.addWidget(self._search, 1)
        search_row.addWidget(show_all)

        # One-tap filters for the usual sensitive values.
        kw_row = QHBoxLayout()
        kw_row.addWidget(QLabel("Sensitive:"))
        for kw in _KEYWORDS:
            btn = QPushButton(kw)
            btn.clicked.connect(lambda _checked=False, k=kw: self._search.setText(k))
            kw_row.addWidget(btn)
        kw_row.addStretch()

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
        layout.addLayout(search_row)
        layout.addLayout(kw_row)
        layout.addWidget(self._text)
        layout.addLayout(button_row)

        self._render_all()
        self._log_manager.entry_added.connect(self._on_entry)
        self._log_manager.cleared.connect(self._text.clear)

    def _matches(self, entry: LogEntry) -> bool:
        return not self._filter or self._filter in entry.text.lower()

    def _line(self, entry: LogEntry) -> str:
        colour = CONSOLE_COLOURS.get(entry.level, "#d4d4d4")
        safe = html.escape(entry.text)
        return (
            f'<span style="color:#6b6b6b">[{entry.time_str}]</span> '
            f'<span style="color:{colour}">{safe}</span>'
        )

    def _append(self, entry: LogEntry) -> None:
        # moveCursor(End) drags the horizontal scrollbar back to make the (short) new
        # line visible, even if you'd scrolled right to read a long one — save/restore
        # it so new output doesn't yank your place away.
        hbar = self._text.horizontalScrollBar()
        h_pos = hbar.value()
        self._text.append(self._line(entry))
        self._text.moveCursor(QTextCursor.MoveOperation.End)
        hbar.setValue(h_pos)

    def _on_entry(self, entry: LogEntry) -> None:
        if self._matches(entry):
            self._append(entry)

    def _render_all(self) -> None:
        self._text.clear()
        for entry in self._log_manager.entries:
            if self._matches(entry):
                self._append(entry)

    def _on_search(self, text: str) -> None:
        self._filter = text.strip().lower()
        self._render_all()

    def _show_all(self) -> None:
        self._search.clear()  # triggers _on_search -> filter cleared
