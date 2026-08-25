""" Frameless window base with rounded corners, native resize and OS snapping.

The rounded outer corners of the launcher look need a frameless, translucent
top-level: a transparent margin band around an opaque, rounded #appRoot. That band
is the resize grip — the interior is covered by #appRoot, so only the band delivers
mouse events to the window itself.

Move and resize are handed to the OS via QWindow.startSystemMove /
startSystemResize rather than moved by hand. That matters: the native operations
are what trigger Windows Aero Snap (drag-to-edge tiling, drag-to-top maximise) and
they manage the resize cursor themselves, so the window docks like a normal one and
the cursor never gets stuck.

Escape hatch: set FRIGA_FRAMELESS=0 to keep a native OS frame (square corners, OS
everything) while every internal style stays the same — a fallback for the case
where a translucent frameless top-level hosting the QWebEngineView editor misbehaves
on a given GPU/driver, which can't be verified without a real display.
"""

from __future__ import annotations

import os

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QVBoxLayout, QWidget

from ui import theme

_MARGIN = 10   # transparent band around the body (also the resize grip width)
_GRIP = 8      # how far inside the band a press still counts as an edge grab


def frameless_enabled() -> bool:
    return os.environ.get("FRIGA_FRAMELESS", "1") != "0"


class FramelessWindow(QWidget):
    """Provides an opaque, rounded content container (self.root_layout).

    Subclasses build their chrome inside root_layout. toggle_max() / minimize() /
    close() are wired to whatever title bar the subclass installs.
    """

    def __init__(self) -> None:
        super().__init__()
        self._frameless = frameless_enabled()

        outer = QVBoxLayout(self)

        self._root = QWidget(self)
        self._root.setObjectName("appRoot")
        # The interior keeps its own arrow cursor, so it never inherits the resize
        # cursor the band sets on the top-level widget (that inheritance was what
        # left the whole app stuck showing a resize cursor).
        self._root.setCursor(Qt.CursorShape.ArrowCursor)

        self.root_layout = QVBoxLayout(self._root)
        self.root_layout.setContentsMargins(0, 0, 0, 0)
        self.root_layout.setSpacing(0)

        if self._frameless:
            self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Window)
            self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
            self.setMouseTracking(True)
            outer.setContentsMargins(_MARGIN, _MARGIN, _MARGIN, _MARGIN)
        else:
            # Native frame: the rounded #appRoot border reads oddly against the OS
            # titlebar, so drop it back to a plain surface.
            self._root.setStyleSheet(
                f"QWidget#appRoot {{ background-color: {theme.BG}; border-radius: 0; border: none; }}"
            )
            outer.setContentsMargins(0, 0, 0, 0)

        outer.addWidget(self._root)

    # --- window controls (called by the title bar) --------------------------
    def minimize(self) -> None:
        self.showMinimized()

    def toggle_max(self) -> None:
        if self.isMaximized():
            self.showNormal()
        else:
            self.showMaximized()

    def changeEvent(self, event) -> None:
        # Maximised: no transparent margin (fill the work area) and square the
        # corners, since a rounded rect against screen edges looks broken.
        if self._frameless and event.type() == event.Type.WindowStateChange:
            margin = 0 if self.isMaximized() else _MARGIN
            self.layout().setContentsMargins(margin, margin, margin, margin)
            radius = 0 if self.isMaximized() else theme.WINDOW_RADIUS
            self._root.setStyleSheet(f"QWidget#appRoot {{ border-radius: {radius}px; }}")
        super().changeEvent(event)

    # --- edge resizing (delegated to the OS) --------------------------------
    def _edges_at(self, pos) -> Qt.Edge:
        if self.isMaximized():
            return Qt.Edge(0)
        rect = self.rect()
        edges = Qt.Edge(0)
        if pos.x() <= _MARGIN + _GRIP:
            edges |= Qt.Edge.LeftEdge
        if pos.x() >= rect.width() - _MARGIN - _GRIP:
            edges |= Qt.Edge.RightEdge
        if pos.y() <= _MARGIN + _GRIP:
            edges |= Qt.Edge.TopEdge
        if pos.y() >= rect.height() - _MARGIN - _GRIP:
            edges |= Qt.Edge.BottomEdge
        return edges

    @staticmethod
    def _cursor_for(edges: Qt.Edge) -> Qt.CursorShape:
        left = bool(edges & Qt.Edge.LeftEdge)
        right = bool(edges & Qt.Edge.RightEdge)
        top = bool(edges & Qt.Edge.TopEdge)
        bottom = bool(edges & Qt.Edge.BottomEdge)
        if (top and left) or (bottom and right):
            return Qt.CursorShape.SizeFDiagCursor
        if (top and right) or (bottom and left):
            return Qt.CursorShape.SizeBDiagCursor
        if left or right:
            return Qt.CursorShape.SizeHorCursor
        if top or bottom:
            return Qt.CursorShape.SizeVerCursor
        return Qt.CursorShape.ArrowCursor

    def mousePressEvent(self, event) -> None:
        if self._frameless and event.button() == Qt.MouseButton.LeftButton:
            edges = self._edges_at(event.position().toPoint())
            handle = self.windowHandle()
            if edges and handle is not None:
                # The OS runs the resize loop — this is what makes edge-snapping work.
                handle.startSystemResize(edges)
                return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        # Only ever fires over the transparent band (the interior is covered by
        # #appRoot). Show the matching resize cursor there; the band is the only
        # place the top-level cursor is visible, and #appRoot keeps its own arrow.
        if self._frameless and not self.isMaximized():
            edges = self._edges_at(event.position().toPoint())
            if edges:
                self.setCursor(self._cursor_for(edges))
            else:
                self.unsetCursor()
        super().mouseMoveEvent(event)
