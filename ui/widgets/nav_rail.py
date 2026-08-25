""" Left navigation rail — the launcher's section switcher.

Each item is a checkable icon+label button; selection is exclusive and drives a
QStackedWidget in the main window. The active item's icon is re-tinted to the
accent to match its text (qtawesome bakes colour into the QIcon, so there's no
:checked selector for it — we swap the icon on toggle instead).
"""

from __future__ import annotations

from PyQt6.QtCore import QSize, Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QButtonGroup,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from ui import icons, theme

_RAIL_WIDTH = 188


class NavRail(QWidget):
    currentChanged = pyqtSignal(int)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("navRail")
        self.setFixedWidth(_RAIL_WIDTH)

        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        self._buttons: list[QToolButton] = []
        self._icon_names: list[str] = []

        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 8, 0, 8)
        self._layout.setSpacing(2)

        self._group.idClicked.connect(self.currentChanged)
        theme.bus.changed.connect(self._on_theme_changed)

    def _on_theme_changed(self, _name: str) -> None:
        for i, btn in enumerate(self._buttons):
            self._retint(i, btn.isChecked())

    def add_item(self, icon_name: str, label: str) -> int:
        index = len(self._buttons)
        btn = QToolButton(self)
        btn.setObjectName("navItem")
        btn.setCheckable(True)
        btn.setText("  " + label)
        btn.setIcon(icons.icon(icon_name, color=theme.FG_MUTED))
        btn.setIconSize(QSize(18, 18))
        btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        btn.toggled.connect(lambda on, i=index: self._retint(i, on))

        self._group.addButton(btn, index)
        self._buttons.append(btn)
        self._icon_names.append(icon_name)
        self._layout.addWidget(btn)
        return index

    def add_stretch(self) -> None:
        self._layout.addStretch(1)

    def set_current(self, index: int) -> None:
        if 0 <= index < len(self._buttons):
            self._buttons[index].setChecked(True)
            self.currentChanged.emit(index)

    def _retint(self, index: int, on: bool) -> None:
        colour = theme.ACCENT if on else theme.FG_MUTED
        self._buttons[index].setIcon(icons.icon(self._icon_names[index], color=colour))
