""" frida-server panel
One button: detect the device's architecture, push the matching frida-server, start
it as root and confirm it's running. The user just picks a device and clicks Deploy """

from __future__ import annotations

from PyQt6.QtWidgets import (
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from core.server_deployer import ServerDeployer


class ServerPanel(QWidget):
    def __init__(self, deployer: ServerDeployer, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._deployer = deployer
        self._serial: str | None = None

        self._device_value = QLabel("None selected")
        self._status_value = QLabel("Not deployed")
        self._set_status_colour("#9b9b9b")

        info_box = QGroupBox("frida-server")
        info_layout = QVBoxLayout(info_box)
        info_layout.addWidget(self._labelled_row("Device:", self._device_value))
        info_layout.addWidget(self._labelled_row("Status:", self._status_value))

        self._deploy_btn = QPushButton("Deploy frida-server")
        self._deploy_btn.clicked.connect(self._on_deploy)

        self._stop_btn = QPushButton("Stop")
        self._stop_btn.clicked.connect(self._on_stop)

        button_row = QHBoxLayout()
        button_row.addWidget(self._deploy_btn)
        button_row.addWidget(self._stop_btn)
        button_row.addStretch()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.addWidget(info_box)
        layout.addLayout(button_row)
        layout.addStretch()

        self._deployer.busy_changed.connect(self._on_busy_changed)
        self._deployer.deployed.connect(self._on_deployed)
        self._deployer.error.connect(self._on_error)

        self._update_enabled()

    def set_device(self, serial: str | None) -> None:
        self._serial = serial
        self._device_value.setText(serial or "None selected")
        self._status_value.setText("Not deployed")
        self._set_status_colour("#9b9b9b")
        self._update_enabled()

    def _on_deploy(self) -> None:
        if self._serial:
            self._deployer.deploy(self._serial)

    def _on_stop(self) -> None:
        if self._serial:
            self._deployer.stop(self._serial)
            self._status_value.setText("Stopped")
            self._set_status_colour("#9b9b9b")

    def _on_busy_changed(self, busy: bool) -> None:
        if busy:
            self._status_value.setText("Deploying…")
            self._set_status_colour("#dcdcaa")
        self._update_enabled(busy)

    def _on_deployed(self, pid: str) -> None:
        self._status_value.setText(f"Running (PID {pid})")
        self._set_status_colour("#4ec9b0")

    def _on_error(self, _message: str) -> None:
        self._status_value.setText("Failed")
        self._set_status_colour("#f44747")

    def _update_enabled(self, busy: bool | None = None) -> None:
        if busy is None:
            busy = self._deployer.is_busy
        enabled = bool(self._serial) and not busy
        self._deploy_btn.setEnabled(enabled)
        self._stop_btn.setEnabled(enabled)

    def _set_status_colour(self, colour: str) -> None:
        self._status_value.setStyleSheet(f"color: {colour}; font-weight: 600;")

    @staticmethod
    def _labelled_row(label: str, value_widget: QLabel) -> QWidget:
        row = QWidget()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        key = QLabel(label)
        key.setStyleSheet("color: #9cdcfe;")
        key.setFixedWidth(60)
        layout.addWidget(key)
        layout.addWidget(value_widget)
        layout.addStretch()
        return row
