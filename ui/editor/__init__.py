""" Script editor backends.

Monaco (VS Code's editor, running in a QWebEngineView) is the real one; QScintilla
stays as a fallback so a build that shipped without QtWebEngine still gets a usable
editor rather than an empty pane. Both expose the same surface, so ScriptEditorPanel
does not care which it is handed.

The Monaco import happens *here, at module import time*, on purpose. Qt refuses to
load QtWebEngineWidgets once a QApplication exists, so importing it lazily inside
create_editor() would quietly downgrade every user to the fallback editor depending
on nothing but import order. Importing eagerly means `import ui.editor` — which
main.py does before building the QApplication — settles it once, and any entry point
that gets the order wrong gets a loud, specific reason instead of a mystery.
"""

from __future__ import annotations

from PyQt6.QtWidgets import QWidget

_MONACO_IMPORT_ERROR: str | None = None

try:
    from ui.editor.monaco_editor import MonacoEditor
    from ui.editor.monaco_editor import register_scheme as _register_scheme
except ImportError as exc:  # QtWebEngine absent, or imported too late
    MonacoEditor = None  # type: ignore[assignment]
    _register_scheme = None  # type: ignore[assignment]
    _MONACO_IMPORT_ERROR = str(exc)


def monaco_available() -> bool:
    return MonacoEditor is not None


def register_scheme() -> None:
    """Register the friga:// scheme Monaco is served over.

    Must be called before the QApplication is constructed. No-op when QtWebEngine
    isn't importable — create_editor() falls back in that case.
    """
    if _register_scheme is not None:
        _register_scheme()


def create_editor(
    initial_text: str = "", parent: QWidget | None = None
) -> tuple[QWidget, str | None]:
    """Build the best available editor.

    Returns (widget, fallback_reason). fallback_reason is None when Monaco loaded,
    otherwise a short explanation worth putting in the console.
    """
    if MonacoEditor is not None:
        try:
            return MonacoEditor(initial_text, parent), None
        except Exception as exc:  # missing assets, scheme failure, …
            reason = f"Monaco editor failed to start ({exc}) — using QScintilla."
    elif _MONACO_IMPORT_ERROR and "before a QCoreApplication" in _MONACO_IMPORT_ERROR:
        # Not an environment limitation — a startup-order bug in whatever built
        # the QApplication. Say so, rather than pretending WebEngine is missing.
        reason = (
            "QtWebEngine was imported after the QApplication was created, so the "
            "Monaco editor is unavailable — import ui.editor (or call "
            "register_scheme()) before constructing QApplication. Using QScintilla."
        )
    else:
        reason = (
            f"QtWebEngine unavailable ({_MONACO_IMPORT_ERROR}) — using the "
            "QScintilla editor."
        )

    from ui.editor.scintilla_editor import ScintillaEditor

    return ScintillaEditor(initial_text, parent), reason
