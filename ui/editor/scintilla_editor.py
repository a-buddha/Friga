""" QScintilla script editor — the fallback when QtWebEngine isn't available.

This is the editor Friga shipped before Monaco. It stays in the tree because a
frozen build that failed to package QtWebEngine would otherwise show a blank pane
instead of a working, if plainer, editor. It exposes the same surface as
MonacoEditor so ScriptEditorPanel never has to know which one it got.
"""

from __future__ import annotations

from PyQt6.Qsci import QsciLexerJavaScript, QsciScintilla
from PyQt6.QtCore import pyqtSignal
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import QVBoxLayout, QWidget

from ui.fonts import editor_font

_TOKEN_COLOURS = {
    "Default": "#d4d4d4",
    "Comment": "#6a9955",
    "CommentLine": "#6a9955",
    "CommentDoc": "#6a9955",
    "Keyword": "#569cd6",
    "DoubleQuotedString": "#ce9178",
    "SingleQuotedString": "#ce9178",
    "Number": "#b5cea8",
    "Operator": "#d4d4d4",
    "Identifier": "#9cdcfe",
    "GlobalClass": "#4ec9b0",
}


def _colour_tokens(lexer: QsciLexerJavaScript) -> None:
    for name, colour in _TOKEN_COLOURS.items():
        style = getattr(lexer, name, None)
        if style is not None:
            try:
                lexer.setColor(QColor(colour), int(style))
            except (TypeError, ValueError):
                pass


def _build_editor() -> QsciScintilla:
    editor = QsciScintilla()
    font = editor_font(11)
    editor.setFont(font)
    editor.setUtf8(True)
    # The app-wide QSS puts a proportional font on every QWidget; pin monospace on
    # the editor itself so the default style and line-number margin stay aligned.
    editor.setStyleSheet(
        'QsciScintilla { font-family: "JetBrains Mono", "DejaVu Sans Mono", '
        '"Ubuntu Mono", "Consolas", monospace; }'
    )

    editor.setMarginType(0, QsciScintilla.MarginType.NumberMargin)
    editor.setMarginWidth(0, "0000")
    editor.setMarginsFont(font)
    editor.setMarginsBackgroundColor(QColor("#1e1e1e"))
    editor.setMarginsForegroundColor(QColor("#6b6b6b"))

    editor.setFolding(QsciScintilla.FoldStyle.BoxedTreeFoldStyle)
    editor.setAutoIndent(True)
    editor.setIndentationsUseTabs(False)
    editor.setIndentationWidth(2)
    editor.setTabWidth(2)
    editor.setBraceMatching(QsciScintilla.BraceMatch.SloppyBraceMatch)
    editor.setCaretLineVisible(True)
    editor.setCaretLineBackgroundColor(QColor("#2a2a2b"))
    editor.setCaretForegroundColor(QColor("#d4d4d4"))
    editor.setSelectionBackgroundColor(QColor("#094771"))

    lexer = QsciLexerJavaScript(editor)
    lexer.setDefaultPaper(QColor("#181818"))
    lexer.setDefaultColor(QColor("#d4d4d4"))
    lexer.setFont(font)
    for style in range(128):
        lexer.setPaper(QColor("#181818"), style)
        lexer.setFont(font, style)
    _colour_tokens(lexer)
    editor.setLexer(lexer)
    return editor


class ScintillaEditor(QWidget):
    textChanged = pyqtSignal()
    runRequested = pyqtSignal()
    saveRequested = pyqtSignal()
    ready = pyqtSignal()
    cursorMoved = pyqtSignal(int, int)

    def __init__(self, initial_text: str = "", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._editor = _build_editor()
        self._editor.setText(initial_text)
        self._editor.textChanged.connect(self.textChanged)
        self._editor.cursorPositionChanged.connect(
            lambda line, index: self.cursorMoved.emit(line + 1, index + 1)
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._editor)

    # --- text ---
    def text(self) -> str:
        return self._editor.text()

    def set_text(self, text: str) -> None:
        self._editor.setText(text)

    def reset_text(self, text: str) -> None:
        self._editor.setText(text)

    def read_text(self, callback) -> None:
        # Synchronous here, but the callback shape matches MonacoEditor.
        callback(self._editor.text())

    # --- misc controls ---
    def insert_text(self, text: str) -> None:
        self._editor.insert(text)

    def set_read_only(self, flag: bool) -> None:
        self._editor.setReadOnly(bool(flag))

    def focus_editor(self) -> None:
        self._editor.setFocus()

    def reveal_line(self, line: int) -> None:
        self._editor.setCursorPosition(max(0, line - 1), 0)
        self._editor.ensureLineVisible(max(0, line - 1))

    def set_error_markers(self, errors: list[dict], line_offset: int = 0) -> None:
        # QScintilla has indicators, but no gutter diagnostics worth the wiring for
        # a fallback path — surfacing the line is enough to be useful.
        for error in errors[:1]:
            self.reveal_line(max(1, int(error.get("line", 1)) - line_offset))

    def clear_error_markers(self) -> None:
        pass
