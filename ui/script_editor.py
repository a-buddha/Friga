""" Script editor
A QScintilla editor with JavaScript highlighting, line numbers, folding and
auto-indent, a small library to save/load/delete scripts, and a Run button that
injects the editor's contents into the active frida session """

from __future__ import annotations

from PyQt6.Qsci import QsciLexerJavaScript, QsciScintilla
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QCheckBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QListWidget,
    QMessageBox,
    QPushButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from core.frida_manager import FridaManager
from core.script_store import ScriptStore, ScriptStoreError
from ui.fonts import editor_font

_TEMPLATE = """\
// Frida script — runs inside the target process.
// Emit output to the console with console.log(...) or send(...).
console.log("[*] Script loaded");

// Example (Android): hook a method and log calls.
// Java.perform(function () {
//   const Activity = Java.use("android.app.Activity");
//   Activity.onResume.implementation = function () {
//     console.log("[*] onResume called");
//     this.onResume();
//   };
// });
"""


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


def _colour_tokens(lexer: QsciLexerJavaScript) -> None:
    mapping = {
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
    for name, colour in mapping.items():
        style = getattr(lexer, name, None)
        if style is not None:
            try:
                lexer.setColor(QColor(colour), int(style))
            except (TypeError, ValueError):
                pass


class ScriptEditorPanel(QWidget):
    def __init__(
        self,
        frida_manager: FridaManager,
        store: ScriptStore | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._frida = frida_manager
        self._store = store or ScriptStore()

        self._editor = _build_editor()
        self._editor.setText(_TEMPLATE)
        self._editor.textChanged.connect(self._update_enabled)

        self._library = QListWidget()
        self._library.itemDoubleClicked.connect(self._on_load_selected)
        self._library.itemSelectionChanged.connect(self._update_enabled)

        lib_side = QWidget()
        lib_layout = QVBoxLayout(lib_side)
        lib_layout.setContentsMargins(0, 0, 0, 0)
        lib_layout.addWidget(QLabel("Script Library"))
        lib_layout.addWidget(self._library)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(lib_side)
        splitter.addWidget(self._editor)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([220, 760])

        self._save_btn = self._make_button("Save", self._on_save)
        self._new_btn = self._make_button("New", self._on_new)
        self._delete_btn = self._make_button("Delete", self._on_delete)
        self._unload_btn = self._make_button("Unload", self._frida.unload_script)
        self._run_btn = self._make_button("▶ Run Script", self._on_run)

        # Frida 17 dropped the global Java bridge; prepend the bundled one so
        # Java.perform works. Off = pure-native scripts / unshifted line numbers.
        self._inject_java = QCheckBox("Inject Java bridge")
        self._inject_java.setChecked(True)

        toolbar = QHBoxLayout()
        toolbar.addWidget(self._new_btn)
        toolbar.addWidget(self._save_btn)
        toolbar.addWidget(self._delete_btn)
        toolbar.addStretch()
        toolbar.addWidget(self._inject_java)
        toolbar.addWidget(self._unload_btn)
        toolbar.addWidget(self._run_btn)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.addLayout(toolbar)
        layout.addWidget(splitter)

        self._frida.session_started.connect(lambda _i: self._update_enabled())
        self._frida.session_stopped.connect(lambda _r: self._update_enabled())
        self._frida.script_state_changed.connect(lambda _s: self._update_enabled())

        self._refresh_library()
        self._update_enabled()

    def _refresh_library(self) -> None:
        self._library.clear()
        self._library.addItems(self._store.list_scripts())

    def _selected_name(self) -> str | None:
        item = self._library.currentItem()
        return item.text() if item is not None else None

    def _on_load_selected(self) -> None:
        name = self._selected_name()
        if not name:
            return
        try:
            self._editor.setText(self._store.load(name))
        except ScriptStoreError as exc:
            QMessageBox.warning(self, "Load failed", str(exc))

    def _on_save(self) -> None:
        suggested = self._selected_name() or ""
        name, ok = QInputDialog.getText(self, "Save Script", "Script name:", text=suggested)
        if not ok or not name.strip():
            return
        if self._store.exists(name) and (
            QMessageBox.question(
                self, "Overwrite?", f"A script named '{name}' already exists. Overwrite it?"
            )
            != QMessageBox.StandardButton.Yes
        ):
            return
        try:
            self._store.save(name, self._editor.text())
        except ScriptStoreError as exc:
            QMessageBox.warning(self, "Save failed", str(exc))
            return
        self._refresh_library()
        self._select_in_library(name)

    def _on_new(self) -> None:
        if (
            QMessageBox.question(self, "New Script", "Clear the editor and start a new script?")
            == QMessageBox.StandardButton.Yes
        ):
            self._editor.setText(_TEMPLATE)
            self._library.clearSelection()

    def _on_delete(self) -> None:
        name = self._selected_name()
        if not name:
            return
        if (
            QMessageBox.question(
                self, "Delete Script", f"Delete the saved script '{name}'? This cannot be undone."
            )
            != QMessageBox.StandardButton.Yes
        ):
            return
        try:
            self._store.delete(name)
        except ScriptStoreError as exc:
            QMessageBox.warning(self, "Delete failed", str(exc))
            return
        self._refresh_library()

    def _select_in_library(self, name: str) -> None:
        matches = self._library.findItems(name, Qt.MatchFlag.MatchExactly)
        if matches:
            self._library.setCurrentItem(matches[0])

    def script_text(self) -> str:
        # current editor contents, for saving a project
        return self._editor.text()

    def set_script_text(self, text: str) -> None:
        # replace editor contents, for loading a project / reset
        self._editor.setText(text)

    def _on_run(self) -> None:
        self._frida.run_script(self._editor.text(), inject_java=self._inject_java.isChecked())

    def _update_enabled(self) -> None:
        has_text = bool(self._editor.text().strip())
        self._save_btn.setEnabled(has_text)
        self._delete_btn.setEnabled(self._selected_name() is not None)
        self._run_btn.setEnabled(self._frida.has_session and has_text and not self._frida.busy)
        self._unload_btn.setEnabled(self._frida.has_script)

    def _make_button(self, text: str, slot) -> QPushButton:
        btn = QPushButton(text)
        btn.clicked.connect(slot)
        return btn
