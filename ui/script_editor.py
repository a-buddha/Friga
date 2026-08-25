""" Script editor panel
Wraps whichever editor backend is available (Monaco, or QScintilla as a fallback)
with a small library to save/load/delete scripts and a Run button that injects the
editor's contents into the active frida session.

The editor itself may live in another process, so reading it is asynchronous: Run
goes through read_text() rather than trusting the mirrored copy, which can be a
keystroke behind.
"""

from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
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
from ui import theme
from ui.editor import create_editor

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


class ScriptEditorPanel(QWidget):
    log = pyqtSignal(str, str)

    def __init__(
        self,
        frida_manager: FridaManager,
        store: ScriptStore | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._frida = frida_manager
        self._store = store or ScriptStore()
        self._current_name: str | None = None
        self._dirty = False

        self._editor, fallback_reason = create_editor(_TEMPLATE)
        self._fallback_reason = fallback_reason
        self._editor.textChanged.connect(self._on_text_changed)
        self._editor.runRequested.connect(self._on_run)
        self._editor.saveRequested.connect(self._on_save)

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
        self._run_btn.setToolTip("Run the script in the attached process (F5)")
        self._save_btn.setToolTip("Save to the script library (Ctrl+S)")

        # Frida 17 dropped the global Java bridge; prepend the bundled one so
        # Java.perform works. Off = pure-native scripts / unshifted line numbers.
        self._inject_java = QCheckBox("Inject Java bridge")
        self._inject_java.setChecked(True)
        self._inject_java.setToolTip(
            "Prepend the bundled Java bridge so Java.perform / Java.use are defined."
        )

        self._status = QLabel()
        self._status.setStyleSheet(f"color: {theme.FG_MUTED};")

        toolbar = QHBoxLayout()
        toolbar.addWidget(self._new_btn)
        toolbar.addWidget(self._save_btn)
        toolbar.addWidget(self._delete_btn)
        toolbar.addWidget(self._status, 1)
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
        self._frida.script_error.connect(self._on_script_error)

        self._refresh_library()
        self._update_status()
        self._update_enabled()

        if fallback_reason:
            self.log.emit(fallback_reason, "warning")

    # --- library ---
    def _refresh_library(self) -> None:
        self._library.clear()
        self._library.addItems(self._store.list_scripts())

    def _selected_name(self) -> str | None:
        item = self._library.currentItem()
        return item.text() if item is not None else None

    def _confirm_discard(self, action: str) -> bool:
        """Ask before throwing away unsaved edits. True = go ahead."""
        if not self._dirty:
            return True
        return QMessageBox.question(
            self,
            "Unsaved changes",
            f"The current script has unsaved changes.\n\n{action}",
        ) == QMessageBox.StandardButton.Yes

    def _on_load_selected(self) -> None:
        name = self._selected_name()
        if not name:
            return
        if not self._confirm_discard(f"Load '{name}' and discard them?"):
            return
        try:
            self._editor.set_text(self._store.load(name))
        except ScriptStoreError as exc:
            QMessageBox.warning(self, "Load failed", str(exc))
            return
        self._current_name = name
        self._dirty = False
        self._update_status()

    def _on_save(self) -> None:
        suggested = self._current_name or self._selected_name() or ""
        name, ok = QInputDialog.getText(
            self, "Save Script", "Script name:", text=suggested
        )
        if not ok or not name.strip():
            return
        if (
            name != self._current_name
            and self._store.exists(name)
            and QMessageBox.question(
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
        self._current_name = name
        self._dirty = False
        self._refresh_library()
        self._select_in_library(name)
        self._update_status()
        self.log.emit(f"Saved script '{name}'.", "success")

    def _on_new(self) -> None:
        if not self._confirm_discard("Start a new script and discard them?"):
            return
        self._editor.reset_text(_TEMPLATE)
        self._library.clearSelection()
        self._current_name = None
        self._dirty = False
        self._update_status()

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
        if self._current_name == name:
            self._current_name = None
            self._update_status()
        self._refresh_library()

    def _select_in_library(self, name: str) -> None:
        matches = self._library.findItems(name, Qt.MatchFlag.MatchExactly)
        if matches:
            self._library.setCurrentItem(matches[0])

    def editor(self) -> QWidget:
        """The active editor backend (Monaco or the QScintilla fallback)."""
        return self._editor

    # --- used by MainWindow for .frigaproj save/load ---
    def script_text(self) -> str:
        return self._editor.text()

    def set_script_text(self, text: str) -> None:
        self._editor.set_text(text)
        self._current_name = None
        self._dirty = False
        self._update_status()

    # --- running ---
    def inject_java_enabled(self) -> bool:
        return self._inject_java.isChecked()

    def read_source(self, callback) -> None:
        """Fetch the live editor contents (async) — used to spawn with a script."""
        self._editor.clear_error_markers()
        self._editor.read_text(callback)

    def _on_run(self) -> None:
        inject = self._inject_java.isChecked()
        self._editor.clear_error_markers()

        def run(text: str) -> None:
            self._frida.run_script(text, inject_java=inject)

        # Read through the editor rather than the mirror: Run can be triggered
        # (F5, or a click) inside the change-push debounce window.
        self._editor.read_text(run)

    def _on_script_error(self, line: int, column: int, message: str, offset: int) -> None:
        # Put a squiggle on the offending line. The editor subtracts the offset so
        # the marker lands on the user's line, not one shifted by the Java bridge.
        self._editor.set_error_markers(
            [{"line": line, "column": column, "message": message}],
            line_offset=offset,
        )

    # --- state ---
    def _on_text_changed(self) -> None:
        if not self._dirty:
            self._dirty = True
            self._update_status()
        self._update_enabled()

    def _update_status(self) -> None:
        name = self._current_name or "Untitled"
        self._status.setText(f"{name}{' •' if self._dirty else ''}")

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
