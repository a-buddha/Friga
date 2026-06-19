""" Talking to ADB to find connected Android devices.
``adb devices`` can block, so the scan runs on a worker thread and 
reports back over signals. The GUI never shells out on the main thread """

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from enum import Enum

from PyQt6.QtCore import QObject, QThread, pyqtSignal

from .resources import is_windows, resolve_adb

# To stop any subprocess flashing windows 
_CREATE_NO_WINDOW = 0x08000000 if is_windows() else 0

# To not let a device hang forever
_ADB_TIMEOUT = 15


class DeviceStatus(str, Enum):
    CONNECTED = "device"
    UNAUTHORIZED = "unauthorized"
    OFFLINE = "offline"
    UNKNOWN = "unknown"

    @classmethod
    def from_adb(cls, raw: str) -> "DeviceStatus":
        try:
            return cls(raw)
        except ValueError:
            return cls.UNKNOWN

    @property
    def label(self) -> str:
        return {
            DeviceStatus.CONNECTED: "Connected",
            DeviceStatus.UNAUTHORIZED: "Unauthorised",
            DeviceStatus.OFFLINE: "Offline",
            DeviceStatus.UNKNOWN: "Unknown",
        }[self]


@dataclass
class Device:
    serial: str
    status: DeviceStatus
    model: str = "—"
    android_version: str = "—"

    @property
    def is_usable(self) -> bool:
        return self.status is DeviceStatus.CONNECTED


def run_adb(
    args: list[str],
    serial: str | None = None,
    timeout: int = _ADB_TIMEOUT,
) -> subprocess.CompletedProcess[str]:
    cmd = [resolve_adb()]
    if serial:
        cmd += ["-s", serial]
    cmd += args
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=timeout,
        creationflags=_CREATE_NO_WINDOW,
    )


def parse_devices(output: str) -> list[tuple[str, DeviceStatus]]:
    devices: list[tuple[str, DeviceStatus]] = []
    for line in output.splitlines():
        line = line.strip()
        if not line or line.startswith("List of devices") or "* daemon" in line:
            continue
        parts = line.split()
        if len(parts) < 2:
            continue
        serial, raw_status = parts[0], parts[1]
        devices.append((serial, DeviceStatus.from_adb(raw_status)))
    return devices


def _query_prop(serial: str, prop: str) -> str:
    try:
        result = run_adb(["shell", "getprop", prop], serial=serial)
        return result.stdout.strip() or "—"
    except (subprocess.SubprocessError, OSError):
        return "—"


class DeviceScanWorker(QThread):
    scanned = pyqtSignal(list)  
    log = pyqtSignal(str, str)  
    failed = pyqtSignal(str)

    def run(self) -> None:
        try:
            result = run_adb(["devices"])
        except FileNotFoundError as exc:
            self.failed.emit(str(exc))
            return
        except subprocess.TimeoutExpired:
            self.failed.emit("ADB timed out while listing devices.")
            return
        except (subprocess.SubprocessError, OSError) as exc:
            self.failed.emit(f"Failed to run ADB: {exc}")
            return

        if result.returncode != 0:
            self.failed.emit(
                result.stderr.strip() or "ADB returned a non-zero exit code."
            )
            return

        devices: list[Device] = []
        for serial, status in parse_devices(result.stdout):
            device = Device(serial=serial, status=status)
            if status is DeviceStatus.CONNECTED:
                device.model = _query_prop(serial, "ro.product.model")
                device.android_version = _query_prop(
                    serial, "ro.build.version.release"
                )
            devices.append(device)

        self.log.emit(f"ADB scan complete: {len(devices)} device(s) found.", "info")
        self.scanned.emit(devices)


class AdbManager(QObject):

    devices_updated = pyqtSignal(list)
    log = pyqtSignal(str, str)          
    error = pyqtSignal(str)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._devices: list[Device] = []
        self._worker: DeviceScanWorker | None = None

    @property
    def devices(self) -> list[Device]:
        return list(self._devices)

    def refresh(self) -> None:
        if self._worker is not None and self._worker.isRunning():
            return

        self.log.emit("Scanning for connected devices…", "info")
        worker = DeviceScanWorker()
        worker.scanned.connect(self._on_scanned)
        worker.log.connect(self.log)
        worker.failed.connect(self._on_failed)
        worker.finished.connect(self._clear_worker)
        self._worker = worker
        worker.start()

    def _on_scanned(self, devices: list[Device]) -> None:
        self._devices = devices
        self.devices_updated.emit(devices)

    def _on_failed(self, message: str) -> None:
        self.error.emit(message)
        self.log.emit(message, "error")

    def _clear_worker(self) -> None:
        self._worker = None
