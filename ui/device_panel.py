""" Device list panel
Shows the Android devices ADB can see including their serial, model, version, status, with a
button to rescan. Highlights the selected serial so the rest of the app knows which
device is the active one """

from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from core.adb_manager import AdbManager, Device, DeviceStatus

_STATUS_COLOURS = {
    DeviceStatus.CONNECTED: "#4ec9b0",
    DeviceStatus.UNAUTHORIZED: "#dcdcaa",
    DeviceStatus.OFFLINE: "#f44747",
    DeviceStatus.UNKNOWN: "#9b9b9b",
}

_HEADERS = ["Serial", "Model", "Android", "Status"]


class DevicePanel(QWidget):
    # The selected serial, or None when nothing is selected.
    device_selected = pyqtSignal(object)

    def __init__(self, adb_manager: AdbManager, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._adb = adb_manager
        self._devices: list[Device] = []

        self._table = QTableWidget(0, len(_HEADERS))
        self._table.setHorizontalHeaderLabels(_HEADERS)
        self._table.verticalHeader().setVisible(False)
        self._table.setAlternatingRowColors(True)
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        header = self._table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)

        self._summary = QLabel("No devices found.")
        self._summary.setStyleSheet("color: #9b9b9b;")

        self._refresh_button = QPushButton("Rescan Devices")
        self._refresh_button.clicked.connect(self._adb.refresh)

        top_row = QHBoxLayout()
        top_row.addWidget(self._summary)
        top_row.addStretch()
        top_row.addWidget(self._refresh_button)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.addLayout(top_row)
        layout.addWidget(self._table)

        self._table.itemSelectionChanged.connect(self._on_selection_changed)
        self._adb.devices_updated.connect(self._populate)

    @property
    def selected_serial(self) -> str | None:
        row = self._table.currentRow()
        if 0 <= row < len(self._devices):
            return self._devices[row].serial
        return None

    def _populate(self, devices: list[Device]) -> None:
        previous = self.selected_serial
        self._devices = devices
        self._table.setRowCount(len(devices))
        for row, device in enumerate(devices):
            self._set_cell(row, 0, device.serial)
            self._set_cell(row, 1, device.model)
            self._set_cell(row, 2, device.android_version)

            status_item = QTableWidgetItem(device.status.label)
            colour = _STATUS_COLOURS.get(device.status, "#d4d4d4")
            status_item.setForeground(QColor(colour))
            self._table.setItem(row, 3, status_item)

        usable = sum(1 for d in devices if d.is_usable)
        if not devices:
            self._summary.setText("No devices found.")
        else:
            self._summary.setText(f"{len(devices)} device(s) — {usable} ready to use.")

        self._restore_or_autoselect(previous)

    def _restore_or_autoselect(self, previous: str | None) -> None:
        target_row = -1
        if previous is not None:
            target_row = next(
                (i for i, d in enumerate(self._devices) if d.serial == previous), -1
            )
        if target_row < 0:
            target_row = next(
                (i for i, d in enumerate(self._devices) if d.is_usable), -1
            )
        if target_row >= 0:
            self._table.selectRow(target_row)
        else:
            self.device_selected.emit(None)

    def _on_selection_changed(self) -> None:
        self.device_selected.emit(self.selected_serial)

    def _set_cell(self, row: int, col: int, text: str) -> None:
        self._table.setItem(row, col, QTableWidgetItem(text))
