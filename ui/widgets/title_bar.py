""" Custom title bar for the frameless window.

Carries the brand mark, the window title, the project actions (New / Open / Save)
and the min / max / close controls, and drives window move + double-click-maximise
by talking to the top-level window it belongs to.
"""

from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QToolButton, QWidget

from ui import icons, theme


class TitleBar(QWidget):
    newProject = pyqtSignal()
    openProject = pyqtSignal()
    saveProject = pyqtSignal()

    def __init__(self, window: QWidget, frameless: bool = True) -> None:
        super().__init__(window)
        self.setObjectName("titleBar")
        self._window = window
        self._frameless = frameless
        self._press_pos = None

        mark = QLabel("◉")  # ◉ stands in if qtawesome has no coloured glyph here
        mark.setObjectName("appMark")
        title = QLabel("Friga")
        title.setObjectName("appTitle")

        row = QHBoxLayout(self)
        row.setContentsMargins(12, 6, 8, 6)
        row.setSpacing(8)
        row.addWidget(mark)
        row.addWidget(title)
        row.addSpacing(12)

        # project actions — kept from the old menu/toolbar so nothing is lost
        self._action_btns: list[tuple[QToolButton, str]] = []
        for name, tip, signal in (
            ("new", "New project", self.newProject),
            ("open", "Open project…", self.openProject),
            ("save", "Save project", self.saveProject),
        ):
            btn = self._tool(name, tip)
            btn.clicked.connect(signal)
            row.addWidget(btn)
            self._action_btns.append((btn, name))

        row.addStretch(1)

        self._win_btns: list[tuple[QToolButton, str]] = []
        if frameless:
            self._min = self._win_button("minimize", "Minimize", self._window.showMinimized)
            self._max = self._win_button("maximize", "Maximize", self._toggle_max)
            self._close = self._win_button("close", "Close", self._window.close, close=True)
            row.addWidget(self._min)
            row.addWidget(self._max)
            row.addWidget(self._close)
            self._win_btns = [(self._min, "minimize"), (self._max, "maximize"),
                              (self._close, "close")]

        theme.bus.changed.connect(self._on_theme_changed)

    def _on_theme_changed(self, _name: str) -> None:
        for btn, name in self._action_btns:
            btn.setIcon(icons.icon(name))
        for btn, name in self._win_btns:
            # keep the maximise/restore glyph as-is (its state is tracked elsewhere)
            glyph = name if not (name == "maximize" and self._window.isMaximized()) else "restore"
            btn.setIcon(icons.icon(glyph, color=theme.FG))

    def _tool(self, icon_name: str, tip: str) -> QToolButton:
        btn = QToolButton(self)
        btn.setObjectName("winBtn")
        btn.setIcon(icons.icon(icon_name))
        btn.setToolTip(tip)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        return btn

    def _win_button(self, icon_name: str, tip: str, slot, close: bool = False) -> QToolButton:
        btn = QToolButton(self)
        btn.setObjectName("winClose" if close else "winBtn")
        btn.setIcon(icons.icon(icon_name, color=theme.FG))
        btn.setToolTip(tip)
        btn.clicked.connect(slot)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        return btn

    def _toggle_max(self) -> None:
        if self._window.isMaximized():
            self._window.showNormal()
            self._max.setIcon(icons.icon("maximize", color=theme.FG))
        else:
            self._window.showMaximized()
            self._max.setIcon(icons.icon("restore", color=theme.FG))

    # --- drag to move -------------------------------------------------------
    # A press only records the start point; the actual drag is handed to the OS
    # (startSystemMove) once the pointer moves past a small threshold. Deferring it
    # keeps double-click-to-maximise working (startSystemMove would otherwise grab
    # the mouse before the second click), and the native move is what enables Aero
    # Snap — dragging to an edge tiles, dragging to the top maximises.
    def mousePressEvent(self, event) -> None:
        if self._frameless and event.button() == Qt.MouseButton.LeftButton:
            self._press_pos = event.position().toPoint()
        else:
            self._press_pos = None
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if (
            self._frameless
            and self._press_pos is not None
            and event.buttons() & Qt.MouseButton.LeftButton
        ):
            moved = (event.position().toPoint() - self._press_pos).manhattanLength()
            if moved > 6:
                handle = self._window.windowHandle()
                self._press_pos = None
                if handle is not None:
                    handle.startSystemMove()
                    return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        self._press_pos = None
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event) -> None:
        if self._frameless:
            self._toggle_max()
        super().mouseDoubleClickEvent(event)
