""" The main window """

from __future__ import annotations

import json
import os

from PyQt6.QtCore import QByteArray, QSettings, Qt
from PyQt6.QtGui import QAction, QCloseEvent, QKeySequence
from PyQt6.QtWidgets import (
    QDockWidget,
    QFileDialog,
    QMainWindow,
    QMessageBox,
    QToolBar,
)

from core.adb_manager import AdbManager
from core.frida_manager import FridaManager
from core.log_manager import LogLevel, LogManager
from core.patcher import Patcher
from core.server_deployer import ServerDeployer
from ui.apk_patcher_panel import ApkPatcherPanel
from ui.console_panel import ConsolePanel
from ui.device_panel import DevicePanel
from ui.ipa_patcher_panel import IpaPatcherPanel
from ui.process_panel import ProcessPanel
from ui.script_editor import ScriptEditorPanel
from ui.server_panel import ServerPanel

_minsize = (1280, 720)

# a .frigaproj is just a small JSON of the workspace + session
_PROJECT_EXT = "frigaproj"
_PROJECT_FILTER = f"Friga Project (*.{_PROJECT_EXT})"
_PROJECT_TAG = "frigaproj"


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Friga")
        self.setMinimumSize(*_minsize)

        # Core managers
        self.log_manager = LogManager(self)
        self.adb_manager = AdbManager(self)
        self.server_deployer = ServerDeployer(self)
        self.frida_manager = FridaManager(self)
        self.patcher = Patcher(self)
        for mgr in (self.adb_manager, self.server_deployer, self.frida_manager, self.patcher):
            mgr.log.connect(self._on_core_log)
            mgr.error.connect(lambda msg: self.statusBar().showMessage(msg, 8000))
        # Script output goes to the console too.
        self.frida_manager.message.connect(self._on_core_log)

        # Script editor in the middle
        self.script_editor = ScriptEditorPanel(self.frida_manager)
        self.setCentralWidget(self.script_editor)

        # keep every dock so the View menu + saveState/restoreState can find them
        self._docks: list[QDockWidget] = []

        # Device list
        self.device_panel = DevicePanel(self.adb_manager)
        device_dock = self._add_dock(
            "Device Manager", "dock_device", self.device_panel,
            Qt.DockWidgetArea.LeftDockWidgetArea,
        )
        device_dock.setAllowedAreas(
            Qt.DockWidgetArea.LeftDockWidgetArea | Qt.DockWidgetArea.RightDockWidgetArea
        )

        # frida-server panel under the device list
        self.server_panel = ServerPanel(self.server_deployer)
        self._add_dock(
            "frida-server", "dock_server", self.server_panel,
            Qt.DockWidgetArea.LeftDockWidgetArea,
        )

        # Process / attach panel on the right
        self.process_panel = ProcessPanel(self.frida_manager)
        self._add_dock(
            "Processes", "dock_process", self.process_panel,
            Qt.DockWidgetArea.RightDockWidgetArea,
        )

        # APK patcher (non-rooted path) under the process panel
        self.apk_patcher_panel = ApkPatcherPanel(self.patcher)
        patcher_dock = self._add_dock(
            "APK Patcher", "dock_apk", self.apk_patcher_panel,
            Qt.DockWidgetArea.RightDockWidgetArea,
        )

        # IPA patcher — design preview only (iOS out of scope), tabbed with the APK one
        self.ipa_patcher_panel = IpaPatcherPanel()
        ipa_dock = self._add_dock(
            "IPA Patcher", "dock_ipa", self.ipa_patcher_panel,
            Qt.DockWidgetArea.RightDockWidgetArea,
        )
        self.tabifyDockWidget(patcher_dock, ipa_dock)
        patcher_dock.raise_()

        # The selected device drives the server + process + patcher panels
        self.device_panel.device_selected.connect(self.server_panel.set_device)
        self.device_panel.device_selected.connect(self.process_panel.set_device)
        self.device_panel.device_selected.connect(self.apk_patcher_panel.set_device)
        # After a deploy, list the processes automatically
        self.server_deployer.deployed.connect(lambda _pid: self.process_panel.refresh())

        # Output console at the bottom
        self.console_panel = ConsolePanel(self.log_manager)
        self._add_dock(
            "Output Console", "dock_console", self.console_panel,
            Qt.DockWidgetArea.BottomDockWidgetArea,
        )

        # menu bar + toolbar + project handling
        self._project_path: str | None = None
        self._build_actions()
        self._build_menu_bar()
        self._build_tool_bar()

        # remember the default layout for "Reset Layout", then load last run's
        self._default_geometry = self.saveGeometry()
        self._default_state = self.saveState()
        self._restore_layout()
        self._update_title()

        self.statusBar().showMessage("Ready")
        self.log_manager.info("Friga started.")

        # Scan once on launch
        self.adb_manager.refresh()

    def _add_dock(self, title, object_name, widget, area) -> QDockWidget:
        # objectName is needed so saveState/restoreState can match docks by name
        dock = QDockWidget(title, self)
        dock.setObjectName(object_name)
        dock.setWidget(widget)
        self.addDockWidget(area, dock)
        self._docks.append(dock)
        return dock

    def _build_actions(self) -> None:
        # one set of actions, reused by the menu and the toolbar
        self.act_new_project = QAction("New Project", self)
        self.act_new_project.triggered.connect(self._new_project)

        self.act_open_project = QAction("Open Project…", self)
        self.act_open_project.setShortcut(QKeySequence.StandardKey.Open)
        self.act_open_project.triggered.connect(self._open_project)

        self.act_save_project = QAction("Save Project", self)
        self.act_save_project.setShortcut(QKeySequence.StandardKey.Save)
        self.act_save_project.triggered.connect(self._save_project)

        self.act_save_project_as = QAction("Save Project As…", self)
        self.act_save_project_as.setShortcut(QKeySequence.StandardKey.SaveAs)
        self.act_save_project_as.triggered.connect(self._save_project_as)

        self.act_reset_layout = QAction("Reset Layout", self)
        self.act_reset_layout.triggered.connect(self._reset_layout)

        self.act_quit = QAction("Exit", self)
        self.act_quit.setShortcut(QKeySequence.StandardKey.Quit)
        self.act_quit.triggered.connect(self.close)

        self.act_about = QAction("About Friga", self)
        self.act_about.triggered.connect(self._show_about)

    def _build_menu_bar(self) -> None:
        menu = self.menuBar()

        file_menu = menu.addMenu("&File")
        file_menu.addAction(self.act_new_project)
        file_menu.addAction(self.act_open_project)
        file_menu.addAction(self.act_save_project)
        file_menu.addAction(self.act_save_project_as)
        file_menu.addSeparator()
        file_menu.addAction(self.act_quit)

        # View menu = each dock's own show/hide action
        view_menu = menu.addMenu("&View")
        for dock in self._docks:
            view_menu.addAction(dock.toggleViewAction())
        view_menu.addSeparator()
        view_menu.addAction(self.act_reset_layout)

        help_menu = menu.addMenu("&Help")
        help_menu.addAction(self.act_about)

    def _build_tool_bar(self) -> None:
        toolbar = QToolBar("Main Toolbar", self)
        toolbar.setObjectName("main_toolbar")  # needed for saveState/restoreState
        toolbar.addAction(self.act_new_project)
        toolbar.addAction(self.act_open_project)
        toolbar.addAction(self.act_save_project)
        self.addToolBar(toolbar)

    # --- projects ---
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
            "version": 1,
            "script": self.script_editor.script_text(),
            "device": self.device_panel.selected_serial,
            "geometry": _encode(self.saveGeometry()),
            "state": _encode(self.saveState()),
        }
        try:
            with open(path, "w", encoding="utf-8") as handle:
                json.dump(data, handle, indent=2)
        except OSError as exc:
            QMessageBox.warning(self, "Save failed", str(exc))
            return
        self._project_path = path
        self._update_title()
        self.statusBar().showMessage(f"Saved project to {path}", 5000)

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
        geometry = data.get("geometry")
        state = data.get("state")
        if geometry:
            self.restoreGeometry(_decode(geometry))
        if state:
            self.restoreState(_decode(state))
        self.device_panel.select_serial(data.get("device"))  # best-effort

        self._project_path = path
        self._update_title()
        self.statusBar().showMessage(f"Opened project {path}", 5000)

    # --- layout ---
    def _reset_layout(self) -> None:
        self.restoreState(self._default_state)
        self.restoreGeometry(self._default_geometry)

    def _restore_layout(self) -> None:
        # reapply last run's window layout if we saved one
        settings = QSettings()
        geometry = settings.value("main_window/geometry")
        state = settings.value("main_window/state")
        if isinstance(geometry, QByteArray):
            self.restoreGeometry(geometry)
        if isinstance(state, QByteArray):
            self.restoreState(state)

    def closeEvent(self, event: QCloseEvent) -> None:
        settings = QSettings()
        settings.setValue("main_window/geometry", self.saveGeometry())
        settings.setValue("main_window/state", self.saveState())
        super().closeEvent(event)

    def _update_title(self) -> None:
        if self._project_path:
            self.setWindowTitle(f"Friga — {os.path.basename(self._project_path)}")
        else:
            self.setWindowTitle("Friga")

    def _show_about(self) -> None:
        QMessageBox.about(
            self,
            "About Friga",
            "<b>Friga</b><br>A desktop front-end for Frida, for Android "
            "mobile-security testing without the command line."
            "<br><br>BSc (Hons) Computer Science (Cybersecurity) FYP, APU.",
        )

    def _on_core_log(self, message: str, level_value: str) -> None:
        try:
            level = LogLevel(level_value)
        except ValueError:
            level = LogLevel.INFO
        self.log_manager.log(message, level)


def _encode(data: QByteArray) -> str:
    # base64 a QByteArray (window geometry/state) so it fits in JSON
    return bytes(data.toBase64()).decode("ascii")


def _decode(text: str) -> QByteArray:
    return QByteArray.fromBase64(text.encode("ascii"))
