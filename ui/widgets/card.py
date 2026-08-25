""" Card — a rounded, bordered surface with an optional title/subtitle header.

The launcher look groups content into cards rather than raw panels. Card wraps an
existing panel widget so the panels themselves don't need to know about the styling.
"""

from __future__ import annotations

from PyQt6.QtWidgets import QFrame, QLabel, QVBoxLayout, QWidget


class Card(QFrame):
    def __init__(
        self,
        title: str | None = None,
        subtitle: str | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("card")

        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(16, 14, 16, 16)
        self._layout.setSpacing(10)

        if title:
            heading = QLabel(title)
            heading.setObjectName("cardTitle")
            self._layout.addWidget(heading)
        if subtitle:
            sub = QLabel(subtitle)
            sub.setObjectName("cardSub")
            sub.setWordWrap(True)
            self._layout.addWidget(sub)

    def add(self, widget: QWidget, stretch: int = 0) -> None:
        self._layout.addWidget(widget, stretch)

    def add_layout(self, layout) -> None:
        self._layout.addLayout(layout)
