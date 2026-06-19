""" The main window """

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QDockWidget, QMainWindow

from core.adb_manager import AdbManager
from core.log_manager import LogLevel, LogManager
from ui.console_panel import ConsolePanel
from ui.device_panel import DevicePanel

_minsize = (1280, 720)


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Friga")
        self.setMinimumSize(*_minsize)

        # Core managers
        self.log_manager = LogManager(self)
        self.adb_manager = AdbManager(self)
        self.adb_manager.log.connect(self._on_core_log)
        self.adb_manager.error.connect(
            lambda msg: self.statusBar().showMessage(msg, 8000)
        )

        # Device list 
        self.device_panel = DevicePanel(self.adb_manager)
        device_dock = QDockWidget("Device Manager", self)
        device_dock.setWidget(self.device_panel)
        device_dock.setAllowedAreas(
            Qt.DockWidgetArea.LeftDockWidgetArea | Qt.DockWidgetArea.RightDockWidgetArea
        )
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, device_dock)

        # Output console at the bottom
        self.console_panel = ConsolePanel(self.log_manager)
        console_dock = QDockWidget("Output Console", self)
        console_dock.setWidget(self.console_panel)
        self.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, console_dock)

        self.statusBar().showMessage("Ready")
        self.log_manager.info("Friga started.")

        # Scan once on launch
        self.adb_manager.refresh()

    def _on_core_log(self, message: str, level_value: str) -> None:
        try:
            level = LogLevel(level_value)
        except ValueError:
            level = LogLevel.INFO
        self.log_manager.log(message, level)
