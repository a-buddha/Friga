""" The main window — a launcher-style shell.

Layout: a custom title bar on top; a left nav rail that switches a stack of pages
(Devices / Target / Script / Patcher / Settings); a persistent console below the
pages; and a status strip along the bottom. The old dock layout is gone — the same
panels now live inside cards on their pages, and the managers wire together exactly
as before (device selection drives the server/process/patcher panels; everything
logs to the console).
"""

from __future__ import annotations

import json
import os

from PyQt6.QtCore import QByteArray, QSettings, Qt, QTimer
from PyQt6.QtGui import QKeySequence, QShortcut
from PyQt6.QtWidgets import (
    QApplication,
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QSplitter,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from core.adb_manager import AdbManager
from core.frida_manager import FridaManager, SessionInfo
from core.log_manager import LogLevel, LogManager
from core.patcher import Patcher
from core.server_deployer import ServerDeployer
from ui import theme
from ui.apk_patcher_panel import ApkPatcherPanel
from ui.console_panel import ConsolePanel
from ui.device_panel import DevicePanel
from ui.ipa_patcher_panel import IpaPatcherPanel
from ui.process_panel import ProcessPanel
from ui.script_editor import ScriptEditorPanel
from ui.server_panel import ServerPanel
from ui.widgets.card import Card
from ui.widgets.frameless import FramelessWindow
from ui.widgets.nav_rail import NavRail
from ui.widgets.title_bar import TitleBar

_MINSIZE = (1120, 720)
_PROJECT_EXT = "frigaproj"
_PROJECT_FILTER = f"Friga Project (*.{_PROJECT_EXT})"
_PROJECT_TAG = "frigaproj"


class MainWindow(FramelessWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Friga")
        self.setMinimumSize(*_MINSIZE)
        self._project_path: str | None = None

        # --- core managers --------------------------------------------------
        self.log_manager = LogManager(self)
        self.adb_manager = AdbManager(self)
        self.server_deployer = ServerDeployer(self)
        self.frida_manager = FridaManager(self)
        self.patcher = Patcher(self)
        for mgr in (self.adb_manager, self.server_deployer, self.frida_manager, self.patcher):
            mgr.log.connect(self._on_core_log)
            mgr.error.connect(self._flash_status)
        self.frida_manager.message.connect(self._on_core_log)

        # --- panels ---------------------------------------------------------
        self.device_panel = DevicePanel(self.adb_manager)
        self.server_panel = ServerPanel(self.server_deployer)
        self.process_panel = ProcessPanel(self.frida_manager)
        self.script_editor = ScriptEditorPanel(self.frida_manager)
        self.script_editor.log.connect(self._on_core_log)
        self.apk_patcher_panel = ApkPatcherPanel(self.patcher)
        self.ipa_patcher_panel = IpaPatcherPanel()
        self.console_panel = ConsolePanel(self.log_manager)

        # selected device drives the dependent panels (unchanged behaviour)
        self.device_panel.device_selected.connect(self.server_panel.set_device)
        self.device_panel.device_selected.connect(self.process_panel.set_device)
        self.device_panel.device_selected.connect(self.apk_patcher_panel.set_device)
        self.server_deployer.deployed.connect(lambda _pid: self.process_panel.refresh())
        # Spawn pulls the current editor script and injects it before startup.
        self.process_panel.spawnRequested.connect(self._on_spawn_requested)

        # --- assemble the shell --------------------------------------------
        self._build_title_bar()
        self._build_body()
        self._build_status_strip()
        self._install_shortcuts()

        # status strip reacts to the same manager signals
        self.device_panel.device_selected.connect(self._on_device_status)
        self.server_deployer.deployed.connect(self._on_server_status)
        self.server_deployer.error.connect(lambda _m: self._set_status("srv", "error", theme.ERROR))
        self.frida_manager.session_started.connect(self._on_session_started)
        self.frida_manager.session_stopped.connect(self._on_session_stopped)
        self.frida_manager.script_state_changed.connect(self._on_script_state)

        self._restore_window()
        self._update_title()
        self._flash_status("Ready")
        self.log_manager.info("Friga started.")
        self.adb_manager.refresh()

    # --- shell construction -------------------------------------------------
    def _build_title_bar(self) -> None:
        self.title_bar = TitleBar(self, frameless=self._frameless)
        self.title_bar.newProject.connect(self._new_project)
        self.title_bar.openProject.connect(self._open_project)
        self.title_bar.saveProject.connect(self._save_project)
        self.root_layout.addWidget(self.title_bar)

    def _build_body(self) -> None:
        self.nav = NavRail()
        self._pages = QStackedWidget()
        self._nav_devices = self.nav.add_item("devices", "Devices")
        self._pages.addWidget(self._page_devices())
        self.nav.add_item("target", "Target")
        self._pages.addWidget(self._page_target())
        self.nav.add_item("script", "Script")
        self._pages.addWidget(self._page_script())
        self.nav.add_item("patcher", "Patcher")
        self._pages.addWidget(self._page_patcher())
        self.nav.add_stretch()
        self.nav.add_item("settings", "Settings")
        self._pages.addWidget(self._page_settings())
        self.nav.currentChanged.connect(self._pages.setCurrentIndex)

        # pages on top, console below, resizable
        self._content_split = QSplitter(Qt.Orientation.Vertical)
        self._content_split.addWidget(self._pages)
        console_wrap = QWidget()
        cw = QVBoxLayout(console_wrap)
        cw.setContentsMargins(16, 0, 16, 12)
        cw.addWidget(self.console_panel)
        self._content_split.addWidget(console_wrap)
        self._content_split.setStretchFactor(0, 3)
        self._content_split.setStretchFactor(1, 1)
        self._content_split.setSizes([520, 220])

        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)
        body.addWidget(self.nav)
        body.addWidget(self._content_split, 1)
        self.root_layout.addLayout(body, 1)

    def _page(self, title: str) -> tuple[QWidget, QVBoxLayout]:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(12)
        heading = QLabel(title)
        heading.setObjectName("pageTitle")
        layout.addWidget(heading)
        return page, layout

    def _page_devices(self) -> QWidget:
        page, layout = self._page("Devices")
        row = QHBoxLayout()
        row.setSpacing(12)
        dev_card = Card("Connected devices", "Android devices ADB can currently see.")
        dev_card.add(self.device_panel, 1)
        srv_card = Card("frida-server", "Deploy the matching server to the selected device.")
        srv_card.add(self.server_panel, 1)
        row.addWidget(dev_card, 2)
        row.addWidget(srv_card, 1)
        layout.addLayout(row, 1)
        return page

    def _page_target(self) -> QWidget:
        page, layout = self._page("Target")
        card = Card("Processes", "Attach to a running process or spawn an app under Frida.")
        card.add(self.process_panel, 1)
        layout.addWidget(card, 1)
        return page

    def _page_script(self) -> QWidget:
        page, layout = self._page("Script")
        card = Card()
        card.add(self.script_editor, 1)
        layout.addWidget(card, 1)
        return page

    def _page_patcher(self) -> QWidget:
        page, layout = self._page("Patcher")
        apk_card = Card("APK patcher", "Inject frida-gadget into an APK for non-rooted testing.")
        apk_card.add(self.apk_patcher_panel)
        ipa_card = Card("IPA patcher", "iOS — design preview only.")
        ipa_card.add(self.ipa_patcher_panel)
        layout.addWidget(apk_card)
        layout.addWidget(ipa_card)
        layout.addStretch(1)
        return page

    def _page_settings(self) -> QWidget:
        page, layout = self._page("Settings")

        appearance = Card("Appearance", "Switch the colour theme. Applies instantly.")
        theme_row = QHBoxLayout()
        theme_label = QLabel("Theme")
        theme_label.setObjectName("cardSub")
        self._theme_combo = QComboBox()
        self._theme_combo.addItems(theme.names())
        self._theme_combo.setCurrentText(theme.current().name)
        self._theme_combo.currentTextChanged.connect(self._on_theme_selected)
        theme_row.addWidget(theme_label)
        theme_row.addWidget(self._theme_combo, 1)
        theme_row.addStretch(1)
        appearance.add_layout(theme_row)
        layout.addWidget(appearance)

        card = Card("About Friga")
        about = QLabel(
            "<b>Friga</b> — a desktop front-end for Frida, for Android mobile-security "
            "testing without the command line.<br><br>"
            "Device discovery · frida-server deployment · process attach/spawn · a "
            "Monaco script editor with the Frida API typed in · one-click APK "
            "gadget-patching · log search."
        )
        about.setWordWrap(True)
        about.setObjectName("cardSub")
        card.add(about)
        layout.addWidget(card)
        layout.addStretch(1)
        return page

    def _on_theme_selected(self, name: str) -> None:
        app = QApplication.instance()
        if app is not None:
            theme.apply(app, name)

    def _build_status_strip(self) -> None:
        self.status_strip = QWidget()
        self.status_strip.setObjectName("statusStrip")
        row = QHBoxLayout(self.status_strip)
        row.setContentsMargins(14, 6, 14, 6)
        row.setSpacing(16)

        self._status_msg = QLabel("Ready")
        self._status_msg.setObjectName("statusItem")
        row.addWidget(self._status_msg)
        row.addStretch(1)

        self._status_labels: dict[str, QLabel] = {}
        for key, text in (("dev", "no device"), ("srv", "server: off"),
                          ("ses", "no session"), ("scr", "no script")):
            label = QLabel(text)
            label.setObjectName("statusItem")
            self._status_labels[key] = label
            row.addWidget(label)
        self.root_layout.addWidget(self.status_strip)

    def _install_shortcuts(self) -> None:
        # Ctrl+S stays with the editor (save script); project actions take the
        # shifted variants so the two don't collide.
        for seq, slot in (
            ("Ctrl+Shift+N", self._new_project),
            ("Ctrl+O", self._open_project),
            ("Ctrl+Shift+S", self._save_project),
        ):
            QShortcut(QKeySequence(seq), self, activated=slot)

    # --- status strip -------------------------------------------------------
    def _set_status(self, key: str, text: str, colour: str = theme.FG_MUTED) -> None:
        label = self._status_labels.get(key)
        if label is not None:
            label.setText(text)
            label.setStyleSheet(f"color: {colour};")

    def _flash_status(self, message: str) -> None:
        self._status_msg.setText(message)
        self._status_msg.setStyleSheet(f"color: {theme.FG};")
        QTimer.singleShot(8000, lambda: self._status_msg.setText(""))

    def _on_device_status(self, serial: object) -> None:
        if serial:
            self._set_status("dev", str(serial), theme.SUCCESS)
        else:
            self._set_status("dev", "no device", theme.FG_MUTED)

    def _on_server_status(self, pid: str) -> None:
        self._set_status("srv", f"server: PID {pid}", theme.SUCCESS)

    def _on_session_started(self, info: SessionInfo) -> None:
        self._set_status("ses", f"{info.name} (PID {info.pid})", theme.SUCCESS)

    def _on_session_stopped(self, _reason: str) -> None:
        self._set_status("ses", "no session", theme.FG_MUTED)

    def _on_spawn_requested(self, serial: str, identifier: str) -> None:
        # Grab the current editor script (async) and spawn with it, so the script is
        # injected before the app starts. Empty editor -> just launches the app.
        inject = self.script_editor.inject_java_enabled()

        def go(source: str) -> None:
            self.frida_manager.spawn_and_run(serial, identifier, source, inject)

        self.script_editor.read_source(go)

    def _on_script_state(self, loaded: bool) -> None:
        if loaded:
            self._set_status("scr", "script running", theme.SUCCESS)
        else:
            self._set_status("scr", "no script", theme.FG_MUTED)

    # --- projects -----------------------------------------------------------
    def _new_project(self) -> None:
        if QMessageBox.question(
            self, "New Project", "Reset the workspace and clear the editor?"
        ) != QMessageBox.StandardButton.Yes:
            return
        self.script_editor.set_script_text("")
        self._project_path = None
        self._update_title()

    def _open_project(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Open Project", "", _PROJECT_FILTER)
        if path:
            self._load_project(path)

    def _save_project(self) -> None:
        if self._project_path is None:
            self._save_project_as()
        else:
            self._write_project(self._project_path)

    def _save_project_as(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "Save Project", "", _PROJECT_FILTER)
        if not path:
            return
        if not path.lower().endswith("." + _PROJECT_EXT):
            path += "." + _PROJECT_EXT
        self._write_project(path)

    def _write_project(self, path: str) -> None:
        data = {
            "format": _PROJECT_TAG,
            "version": 2,
            "script": self.script_editor.script_text(),
            "device": self.device_panel.selected_serial,
            "page": self._pages.currentIndex(),
        }
        try:
            with open(path, "w", encoding="utf-8") as handle:
                json.dump(data, handle, indent=2)
        except OSError as exc:
            QMessageBox.warning(self, "Save failed", str(exc))
            return
        self._project_path = path
        self._update_title()
        self._flash_status(f"Saved project to {path}")

    def _load_project(self, path: str) -> None:
        try:
            with open(path, encoding="utf-8") as handle:
                data = json.load(handle)
        except (OSError, json.JSONDecodeError) as exc:
            QMessageBox.warning(self, "Open failed", f"Could not read project:\n{exc}")
            return
        if not isinstance(data, dict) or data.get("format") != _PROJECT_TAG:
            QMessageBox.warning(self, "Open failed", "This is not a Friga project file.")
            return
        self.script_editor.set_script_text(str(data.get("script", "")))
        self.device_panel.select_serial(data.get("device"))
        page = data.get("page")
        if isinstance(page, int) and 0 <= page < self._pages.count():
            self.nav.set_current(page)
        self._project_path = path
        self._update_title()
        self._flash_status(f"Opened project {path}")

    # --- window state -------------------------------------------------------
    def _restore_window(self) -> None:
        settings = QSettings()
        geometry = settings.value("main_window/geometry")
        if isinstance(geometry, QByteArray):
            self.restoreGeometry(geometry)
        page = settings.value("main_window/page")
        try:
            page = int(page)
        except (TypeError, ValueError):
            page = 0
        self.nav.set_current(page if 0 <= page < self._pages.count() else 0)

    def closeEvent(self, event) -> None:
        settings = QSettings()
        settings.setValue("main_window/geometry", self.saveGeometry())
        settings.setValue("main_window/page", self._pages.currentIndex())
        super().closeEvent(event)

    def _update_title(self) -> None:
        name = os.path.basename(self._project_path) if self._project_path else None
        self.setWindowTitle(f"Friga — {name}" if name else "Friga")

    def _on_core_log(self, message: str, level_value: str) -> None:
        try:
            level = LogLevel(level_value)
        except ValueError:
            level = LogLevel.INFO
        self.log_manager.log(message, level)
