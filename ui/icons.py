""" Icons, via qtawesome (Font Awesome as QIcons).

Every icon the UI needs is referenced by a semantic name here, so the actual glyph
set is swappable in one place. If qtawesome isn't installed the helpers return an
empty QIcon rather than raising — the app stays usable, just text-only.
"""

from __future__ import annotations

from PyQt6.QtGui import QIcon

from ui import theme

try:
    import qtawesome as qta
    _HAVE_QTA = True
except ImportError:  # pragma: no cover - depends on the environment
    qta = None
    _HAVE_QTA = False

# semantic name -> Font Awesome 5 solid glyph
_GLYPHS = {
    "devices": "fa5s.mobile-alt",
    "server": "fa5s.server",
    "target": "fa5s.crosshairs",
    "script": "fa5s.code",
    "patcher": "fa5s.syringe",       # injecting the gadget
    "settings": "fa5s.cog",
    "about": "fa5s.info-circle",
    "brand": "fa5s.user-secret",     # red-team mark
    "run": "fa5s.play",
    "stop": "fa5s.stop",
    "save": "fa5s.save",
    "open": "fa5s.folder-open",
    "new": "fa5s.file",
    "delete": "fa5s.trash-alt",
    "refresh": "fa5s.sync-alt",
    "detach": "fa5s.unlink",
    "deploy": "fa5s.upload",
    "search": "fa5s.search",
    "chip": "fa5s.microchip",
    "minimize": "fa5s.window-minimize",
    "maximize": "fa5s.window-maximize",
    "restore": "fa5s.window-restore",
    "close": "fa5s.times",
}


def available() -> bool:
    return _HAVE_QTA


def icon(name: str, color: str | None = None) -> QIcon:
    """A themed QIcon for a semantic name (empty QIcon if qtawesome is absent)."""
    if not _HAVE_QTA:
        return QIcon()
    glyph = _GLYPHS.get(name)
    if glyph is None:
        return QIcon()
    return qta.icon(glyph, color=color or theme.FG_MUTED)
