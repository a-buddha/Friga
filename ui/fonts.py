""" Picking the editor font.
QScintilla lays text out on fixed cells, so it needs a real monospace font or the
glyphs overlap and clicks land on the wrong character. I bundle JetBrains Mono so
the editor looks the same everywhere, and fall back to whatever monospace is
installed if the bundled file isn't there. Call these after the QApplication exists """

from __future__ import annotations

from PyQt6.QtGui import QFont, QFontDatabase

from core.resources import APP_ROOT

_FONTS_DIR = APP_ROOT / "assets" / "fonts"
_PREFERRED = "JetBrains Mono"
_FALLBACKS = (
    "DejaVu Sans Mono",
    "Ubuntu Mono",
    "Consolas",
    "Cascadia Mono",
    "Liberation Mono",
    "Monospace",
)

_registered = False


def register_bundled_fonts() -> None:
    global _registered
    if _registered:
        return
    if _FONTS_DIR.is_dir():
        for ttf in _FONTS_DIR.glob("*.ttf"):
            QFontDatabase.addApplicationFont(str(ttf))
    _registered = True


def editor_font(point_size: int = 11) -> QFont:
    register_bundled_fonts()
    families = set(QFontDatabase.families())
    chosen = _PREFERRED if _PREFERRED in families else next(
        (f for f in _FALLBACKS if f in families), None
    )
    font = QFont(chosen) if chosen else QFont()
    font.setPointSize(point_size)
    font.setFixedPitch(True)
    font.setStyleHint(QFont.StyleHint.Monospace)
    return font
