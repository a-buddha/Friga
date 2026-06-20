""" The main window """

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QDockWidget, QMainWindow

from core.adb_manager import AdbManager
from core.frida_manager import FridaManager
from core.log_manager import LogLevel, LogManager
from core.server_deployer import ServerDeployer
from ui.console_panel import ConsolePanel
from ui.device_panel import DevicePanel
from ui.process_panel import ProcessPanel
from ui.server_panel import ServerPanel

_minsize = (1280, 720)


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
        for mgr in (self.adb_manager, self.server_deployer, self.frida_manager):
            mgr.log.connect(self._on_core_log)
            mgr.error.connect(lambda msg: self.statusBar().showMessage(msg, 8000))

        # frida-server panel under  the device list
        self.server_panel = ServerPanel(self.server_deployer)
        server_dock = QDockWidget("frida-server", self)
        server_dock.setWidget(self.server_panel)
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, server_dock)

        # Process / attach panel on the right
        self.process_panel = ProcessPanel(self.frida_manager)
        process_dock = QDockWidget("Processes", self)
        process_dock.setWidget(self.process_panel)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, process_dock)

        # The selected device drives the server & process panels
        self.device_panel.device_selected.connect(self.server_panel.set_device)
        self.device_panel.device_selected.connect(self.process_panel.set_device)
        # After a deploy, list the processes automatically
        self.server_deployer.deployed.connect(lambda _pid: self.process_panel.refresh())
        
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
