""" Process panel
Lists the running processes on the selected device (through frida), lets you filter
them by name, and attach to one or spawn an app fresh. Shows the active session """

from __future__ import annotations

from PyQt6.QtWidgets import (
    QAbstractItemView,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from core.frida_manager import FridaManager, ProcessInfo, SessionInfo


class ProcessPanel(QWidget):
    def __init__(self, frida_manager: FridaManager, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._frida = frida_manager
        self._serial: str | None = None
        self._processes: list[ProcessInfo] = []

        self._search = QLineEdit()
        self._search.setPlaceholderText("Filter processes by name…")
        self._search.textChanged.connect(self._apply_filter)

        self._refresh_btn = QPushButton("Refresh")
        self._refresh_btn.clicked.connect(self._on_refresh)

        search_row = QHBoxLayout()
        search_row.addWidget(self._search)
        search_row.addWidget(self._refresh_btn)

        self._table = QTableWidget(0, 2)
        self._table.setHorizontalHeaderLabels(["PID", "Name"])
        self._table.verticalHeader().setVisible(False)
        self._table.setAlternatingRowColors(True)
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        header = self._table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self._table.itemSelectionChanged.connect(self._update_enabled)
        self._table.doubleClicked.connect(self._on_attach)

        self._attach_btn = QPushButton("Attach")
        self._attach_btn.clicked.connect(self._on_attach)

        self._spawn_input = QLineEdit()
        self._spawn_input.setPlaceholderText("Package identifier, e.g. com.example.app")
        self._spawn_input.textChanged.connect(self._update_enabled)
        self._spawn_btn = QPushButton("Spawn")
        self._spawn_btn.clicked.connect(self._on_spawn)

        spawn_box = QGroupBox("Spawn an app")
        spawn_layout = QHBoxLayout(spawn_box)
        spawn_layout.addWidget(self._spawn_input)
        spawn_layout.addWidget(self._spawn_btn)

        self._session_value = QLabel("No active session")
        self._session_value.setStyleSheet("color: #9b9b9b;")
        self._detach_btn = QPushButton("Detach")
        self._detach_btn.clicked.connect(self._frida.detach)

        session_box = QGroupBox("Active session")
        session_layout = QHBoxLayout(session_box)
        session_layout.addWidget(self._session_value)
        session_layout.addStretch()
        session_layout.addWidget(self._detach_btn)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.addLayout(search_row)
        layout.addWidget(self._table)
        layout.addWidget(self._attach_btn)
        layout.addWidget(spawn_box)
        layout.addWidget(session_box)

        self._frida.processes_listed.connect(self._on_processes)
        self._frida.session_started.connect(self._on_session_started)
        self._frida.session_stopped.connect(self._on_session_stopped)
        self._frida.busy_changed.connect(lambda _b: self._update_enabled())

        self._update_enabled()

    def set_device(self, serial: str | None) -> None:
        self._serial = serial
        self._processes = []
        self._table.setRowCount(0)
        self._update_enabled()

    def refresh(self) -> None:
        self._on_refresh()

    def _on_refresh(self) -> None:
        if self._serial:
            self._frida.list_processes(self._serial)

    def _on_processes(self, processes: list[ProcessInfo]) -> None:
        self._processes = sorted(processes, key=lambda p: p.name.lower())
        self._apply_filter()

    def _apply_filter(self) -> None:
        term = self._search.text().strip().lower()
        rows = [p for p in self._processes if term in p.name.lower()] if term else self._processes
        self._table.setRowCount(len(rows))
        for row, proc in enumerate(rows):
            self._table.setItem(row, 0, QTableWidgetItem(str(proc.pid)))
            self._table.setItem(row, 1, QTableWidgetItem(proc.name))
        self._update_enabled()

    def _selected_process(self) -> tuple[int, str] | None:
        row = self._table.currentRow()
        if row < 0 or self._table.item(row, 0) is None:
            return None
        return int(self._table.item(row, 0).text()), self._table.item(row, 1).text()

    def _on_attach(self) -> None:
        target = self._selected_process()
        if target and self._serial:
            pid, name = target
            self._frida.attach(self._serial, pid, name)

    def _on_spawn(self) -> None:
        identifier = self._spawn_input.text().strip()
        if identifier and self._serial:
            self._frida.spawn(self._serial, identifier)

    def _on_session_started(self, info: SessionInfo) -> None:
        self._session_value.setText(f"{info.name}  (PID {info.pid})  on {info.serial}")
        self._session_value.setStyleSheet("color: #4ec9b0; font-weight: 600;")
        self._update_enabled()

    def _on_session_stopped(self, _reason: str) -> None:
        self._session_value.setText("No active session")
        self._session_value.setStyleSheet("color: #9b9b9b;")
        self._update_enabled()

    def _update_enabled(self) -> None:
        have_device = bool(self._serial)
        busy = self._frida.busy
        self._refresh_btn.setEnabled(have_device and not busy)
        self._attach_btn.setEnabled(
            have_device and not busy and self._selected_process() is not None
        )
        self._spawn_btn.setEnabled(
            have_device and not busy and bool(self._spawn_input.text().strip())
        )
        self._detach_btn.setEnabled(self._frida.has_session)
