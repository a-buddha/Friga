""" Monaco-backed script editor.

Monaco is VS Code's editor, so this buys three things QScintilla could not: real
type-aware completion over the Frida API (the bundled .d.ts files are fed to its
TypeScript service), squiggles on the right line, and a look that matches the rest
of a dark UI for free.

Two structural notes:

* The page is served over a custom ``friga://`` scheme rather than ``file://`` or a
  localhost HTTP server. Monaco spins its language service up in a web worker built
  from a Blob URL, which ``file://`` forbids outright; a localhost server would work
  but means opening a listening socket inside a security tool, which is a bad trade.
  The scheme has to be registered before QApplication exists — see register_scheme().

* Reading the editor is asynchronous (it lives in another process), but callers like
  MainWindow._write_project expect a plain string back. So every keystroke is pushed
  from JS into a Python-side mirror, and text() returns that. The Run path does not
  trust the mirror — it re-reads from the editor first, since a user can hit Run
  within the debounce window.
"""

from __future__ import annotations

import json
from pathlib import Path

from PyQt6.QtCore import (
    QBuffer,
    QByteArray,
    QIODevice,
    QObject,
    Qt,
    QUrl,
    pyqtSignal,
    pyqtSlot,
)
from PyQt6.QtWebChannel import QWebChannel
from PyQt6.QtWebEngineCore import (
    QWebEngineProfile,
    QWebEngineUrlRequestJob,
    QWebEngineUrlScheme,
    QWebEngineUrlSchemeHandler,
)
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWidgets import QVBoxLayout, QWidget

from core.resources import resolve_monaco_root
from ui import theme

SCHEME_NAME = b"friga"
_HOST = "editor"
_BASE_URL = "friga://editor/index.html"

# Served from Qt's own resources rather than vendored, so it can never drift from
# the installed QtWebChannel version.
_QWEBCHANNEL_RESOURCE = ":/qtwebchannel/qwebchannel.js"

_MIME = {
    ".html": b"text/html",
    ".js": b"application/javascript",
    ".css": b"text/css",
    ".json": b"application/json",
    ".svg": b"image/svg+xml",
    ".ttf": b"font/ttf",
    ".woff": b"font/woff",
    ".woff2": b"font/woff2",
    ".map": b"application/json",
}

# Order matters: the shim's `import ... from "frida-java-bridge"` needs the bridge's
# ambient module declaration to already be known to the TS service.
_TYPINGS = (
    ("frida-gum.d.ts", "file:///node_modules/@types/frida-gum/index.d.ts"),
    ("frida-java-bridge.d.ts", "file:///node_modules/frida-java-bridge/index.d.ts"),
    ("friga-globals.d.ts", "file:///friga-globals.d.ts"),
)


def register_scheme() -> None:
    """Register friga:// — must run before the QApplication is constructed."""
    if bytes(QWebEngineUrlScheme.schemeByName(SCHEME_NAME).name()) == SCHEME_NAME:
        return  # already registered (e.g. a second window, or a re-entrant import)

    scheme = QWebEngineUrlScheme(SCHEME_NAME)
    scheme.setSyntax(QWebEngineUrlScheme.Syntax.Host)
    scheme.setFlags(
        QWebEngineUrlScheme.Flag.SecureScheme
        | QWebEngineUrlScheme.Flag.LocalAccessAllowed
        | QWebEngineUrlScheme.Flag.CorsEnabled
        | QWebEngineUrlScheme.Flag.FetchApiAllowed
    )
    QWebEngineUrlScheme.registerScheme(scheme)


class _AssetSchemeHandler(QWebEngineUrlSchemeHandler):
    """Serves assets/monaco/ over friga://editor/ ."""

    def __init__(self, root: Path, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._root = root.resolve()

    def requestStarted(self, job: QWebEngineUrlRequestJob) -> None:
        path = job.requestUrl().path().lstrip("/") or "index.html"

        if path == "qwebchannel.js":
            payload = self._read_qt_resource(_QWEBCHANNEL_RESOURCE)
            if payload is None:
                job.fail(QWebEngineUrlRequestJob.Error.UrlNotFound)
                return
            self._reply(job, payload, b"application/javascript")
            return

        target = (self._root / path).resolve()
        if not target.is_relative_to(self._root) or not target.is_file():
            job.fail(QWebEngineUrlRequestJob.Error.UrlNotFound)
            return

        mime = _MIME.get(target.suffix.lower(), b"application/octet-stream")
        self._reply(job, QByteArray(target.read_bytes()), mime)

    @staticmethod
    def _read_qt_resource(path: str) -> QByteArray | None:
        from PyQt6.QtCore import QFile

        handle = QFile(path)
        if not handle.open(QIODevice.OpenModeFlag.ReadOnly):
            return None
        try:
            return QByteArray(handle.readAll())
        finally:
            handle.close()

    @staticmethod
    def _reply(job: QWebEngineUrlRequestJob, data: QByteArray, mime: bytes) -> None:
        # Parented to the job so the buffer outlives the reply call.
        buffer = QBuffer(job)
        buffer.setData(data)
        buffer.open(QIODevice.OpenModeFlag.ReadOnly)
        job.reply(mime, buffer)


class _Bridge(QObject):
    """The object JS sees as `bridge` on the QWebChannel."""

    textChanged = pyqtSignal(str)
    editorReady = pyqtSignal()
    runRequested = pyqtSignal()
    saveRequested = pyqtSignal()
    cursorMoved = pyqtSignal(int, int)

    def __init__(self, payload: str, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._payload = payload

    @pyqtSlot(result=str)
    def get_editor_payload(self) -> str:
        return self._payload

    @pyqtSlot(str)
    def on_text_changed(self, text: str) -> None:
        self.textChanged.emit(text)

    @pyqtSlot()
    def on_ready(self) -> None:
        self.editorReady.emit()

    @pyqtSlot()
    def on_run_requested(self) -> None:
        self.runRequested.emit()

    @pyqtSlot()
    def on_save_requested(self) -> None:
        self.saveRequested.emit()

    @pyqtSlot(int, int)
    def on_cursor_changed(self, line: int, column: int) -> None:
        self.cursorMoved.emit(line, column)


class MonacoEditor(QWidget):
    """Drop-in replacement for the QScintilla editor, same public surface."""

    textChanged = pyqtSignal()
    runRequested = pyqtSignal()
    saveRequested = pyqtSignal()
    ready = pyqtSignal()
    cursorMoved = pyqtSignal(int, int)

    def __init__(self, initial_text: str = "", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._text = initial_text
        self._ready = False
        self._queued: list[str] = []

        root = resolve_monaco_root()
        payload = json.dumps({
            "text": initial_text,
            "typings": _load_typings(root / "types"),
            "theme": theme.monaco_colours(),
        })

        self._view = QWebEngineView(self)
        # Monaco supplies its own context menu; Chromium's (Reload, View Source…)
        # would be nonsense inside an editor pane.
        self._view.setContextMenuPolicy(Qt.ContextMenuPolicy.NoContextMenu)

        profile = self._view.page().profile()
        # Keep a reference: the profile does not take ownership of the handler.
        self._handler = _AssetSchemeHandler(root, self)
        if profile.urlSchemeHandler(SCHEME_NAME) is None:
            profile.installUrlSchemeHandler(SCHEME_NAME, self._handler)

        self._bridge = _Bridge(payload, self)
        self._channel = QWebChannel(self)
        self._channel.registerObject("bridge", self._bridge)
        self._view.page().setWebChannel(self._channel)

        self._bridge.textChanged.connect(self._on_text_changed)
        self._bridge.editorReady.connect(self._on_ready)
        self._bridge.runRequested.connect(self.runRequested)
        self._bridge.saveRequested.connect(self.saveRequested)
        self._bridge.cursorMoved.connect(self.cursorMoved)
        theme.bus.changed.connect(lambda _n: self.apply_theme())

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._view)

        self._view.load(QUrl(_BASE_URL))

    # --- text ---
    def text(self) -> str:
        """Last known contents. Mirrored from JS, so up to ~120 ms stale."""
        return self._text

    def set_text(self, text: str) -> None:
        """Replace the contents, keeping undo history."""
        self._text = text
        self._call(f"window.friga.setText({json.dumps(text)});")

    def reset_text(self, text: str) -> None:
        """Replace the contents and drop undo history (for 'New')."""
        self._text = text
        self._call(f"window.friga.resetText({json.dumps(text)});")

    def read_text(self, callback) -> None:
        """Fetch the live contents straight from the editor.

        Used on the Run path, where the debounced mirror could still be a
        keystroke behind.
        """
        if not self._ready:
            callback(self._text)
            return

        def done(value: object) -> None:
            text = value if isinstance(value, str) else self._text
            self._text = text
            callback(text)

        self._view.page().runJavaScript("window.friga.getText();", done)

    # --- misc controls ---
    def insert_text(self, text: str) -> None:
        self._call(f"window.friga.insertText({json.dumps(text)});")

    def apply_theme(self) -> None:
        """Recolour the editor to the active app theme."""
        self._call(f"window.friga.setTheme({json.dumps(theme.monaco_colours())});")

    def set_read_only(self, flag: bool) -> None:
        self._call(f"window.friga.setReadOnly({json.dumps(bool(flag))});")

    def focus_editor(self) -> None:
        self._call("window.friga.focusEditor();")

    def reveal_line(self, line: int) -> None:
        self._call(f"window.friga.revealLine({int(line)});")

    def set_error_markers(self, errors: list[dict], line_offset: int = 0) -> None:
        """Mark script errors in the gutter.

        ``line_offset`` is how many lines Friga prepended (the Java bridge is one
        line), so a frida-reported line maps back onto what the user actually wrote.
        """
        markers = [
            {
                "startLineNumber": max(1, int(e.get("line", 1)) - line_offset),
                "endLineNumber": max(1, int(e.get("line", 1)) - line_offset),
                "startColumn": int(e.get("column", 1)),
                "endColumn": int(e.get("column", 1)) + 1,
                "message": str(e.get("message", "Script error")),
                "severity": 8,  # monaco.MarkerSeverity.Error
            }
            for e in errors
        ]
        self._call(f"window.friga.setDiagnostics({json.dumps(markers)});")

    def clear_error_markers(self) -> None:
        self._call("window.friga.clearDiagnostics();")

    # --- internals ---
    def _call(self, script: str) -> None:
        if self._ready:
            self._view.page().runJavaScript(script)
        else:
            self._queued.append(script)

    def _on_ready(self) -> None:
        self._ready = True
        for script in self._queued:
            self._view.page().runJavaScript(script)
        self._queued.clear()
        self.ready.emit()

    def _on_text_changed(self, text: str) -> None:
        if text == self._text:
            return
        self._text = text
        self.textChanged.emit()


def _load_typings(types_dir: Path) -> list[dict]:
    libs = []
    for filename, virtual_path in _TYPINGS:
        source = types_dir / filename
        if source.is_file():
            libs.append({
                "path": virtual_path,
                "content": source.read_text(encoding="utf-8"),
            })
    return libs
