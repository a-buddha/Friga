""" Getting frida-server onto a device.
Works out the device's CPU architecture, pushes the matching bundled frida-server
binary to /data/local/tmp, starts it as root and checks it came up. It all runs on a
worker thread so the UI stays responsive — the user just clicks one button """

from __future__ import annotations

import subprocess
import time

from PyQt6.QtCore import QObject, QThread, pyqtSignal

from .adb_manager import run_adb
from .resources import frida_arch_for_abi, is_windows, resolve_frida_server

_CREATE_NO_WINDOW = 0x08000000 if is_windows() else 0

_REMOTE_PATH = "/data/local/tmp/frida-server"
_PUSH_TIMEOUT = 180  # the binaries are big (~50-110 MB)
_VERIFY_ATTEMPTS = 6
_VERIFY_DELAY = 0.5


class DeviceArch:
    def __init__(self, abi: str, frida_arch: str) -> None:
        self.abi = abi
        self.frida_arch = frida_arch


def detect_arch(serial: str) -> DeviceArch:
    result = run_adb(["shell", "getprop", "ro.product.cpu.abi"], serial=serial)
    abi = (result.stdout or "").strip()
    if not abi:
        raise RuntimeError("Could not read device CPU ABI via ADB.")
    arch = frida_arch_for_abi(abi)
    if arch is None:
        raise RuntimeError(f"Unsupported device ABI '{abi}' — no matching frida-server.")
    return DeviceArch(abi=abi, frida_arch=arch)


def _server_pid(serial: str) -> str | None:
    try:
        result = run_adb(["shell", "pidof", "frida-server"], serial=serial)
    except (subprocess.SubprocessError, OSError):
        return None
    pid = (result.stdout or "").strip()
    return pid or None


def _root_prefix(serial: str) -> list[str] | None:
    # Magisk / userdebug 'su'
    try:
        result = run_adb(["shell", "su", "-c", "id"], serial=serial)
        if "uid=0" in (result.stdout or ""):
            return ["su", "-c"]
    except (subprocess.SubprocessError, OSError):
        pass

    # Emulator / userdebug: restart adbd as root and run directly
    try:
        run_adb(["root"], serial=serial, timeout=20)
        time.sleep(1.0)
        run_adb(["wait-for-device"], serial=serial, timeout=20)
        result = run_adb(["shell", "id"], serial=serial)
        if "uid=0" in (result.stdout or ""):
            return []
    except (subprocess.SubprocessError, OSError):
        pass

    return None


def _start_command(serial: str, prefix: list[str]) -> list[str]:
    launch = f"nohup {_REMOTE_PATH} >/dev/null 2>&1 &"
    shell_args = prefix + [launch] if prefix else [launch]
    return ["shell", *shell_args]


class DeployWorker(QThread):
    progress = pyqtSignal(str, str)
    finished_ok = pyqtSignal(str)
    failed = pyqtSignal(str)

    def __init__(self, serial: str, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._serial = serial

    def run(self) -> None:
        serial = self._serial
        try:
            # Already running? Treat as success.
            existing = _server_pid(serial)
            if existing:
                self.progress.emit(
                    f"frida-server already running (PID {existing}).", "success"
                )
                self.finished_ok.emit(existing)
                return

            self.progress.emit("Detecting device architecture…", "info")
            arch = detect_arch(serial)
            self.progress.emit(
                f"Device ABI '{arch.abi}' → frida-server arch '{arch.frida_arch}'.",
                "info",
            )

            binary = resolve_frida_server(arch.frida_arch)
            self.progress.emit(f"Pushing frida-server to {_REMOTE_PATH}…", "info")
            push = run_adb(
                ["push", binary, _REMOTE_PATH], serial=serial, timeout=_PUSH_TIMEOUT
            )
            if push.returncode != 0:
                self.failed.emit(push.stderr.strip() or "adb push failed.")
                return

            run_adb(["shell", "chmod", "755", _REMOTE_PATH], serial=serial)

            self.progress.emit("Acquiring root and starting frida-server…", "info")
            prefix = _root_prefix(serial)
            if prefix is None:
                self.failed.emit(
                    "Could not gain root on the device. frida-server needs a rooted "
                    "device or an emulator."
                )
                return

            # Launch detached; this returns right away.
            try:
                run_adb(_start_command(serial, prefix), serial=serial, timeout=10)
            except subprocess.TimeoutExpired:
                pass

            for _ in range(_VERIFY_ATTEMPTS):
                pid = _server_pid(serial)
                if pid:
                    self.progress.emit(f"frida-server is running (PID {pid}).", "success")
                    self.finished_ok.emit(pid)
                    return
                time.sleep(_VERIFY_DELAY)

            self.failed.emit(
                "frida-server was pushed but did not start. Check device root status "
                "and SELinux policy."
            )
        except FileNotFoundError as exc:
            self.failed.emit(str(exc))
        except RuntimeError as exc:
            self.failed.emit(str(exc))
        except (subprocess.SubprocessError, OSError) as exc:
            self.failed.emit(f"Deployment error: {exc}")


class ServerDeployer(QObject):
    log = pyqtSignal(str, str)
    deployed = pyqtSignal(str)
    error = pyqtSignal(str)
    busy_changed = pyqtSignal(bool)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._worker: DeployWorker | None = None

    @property
    def is_busy(self) -> bool:
        return self._worker is not None and self._worker.isRunning()

    def deploy(self, serial: str) -> None:
        if self.is_busy:
            return
        self.busy_changed.emit(True)
        self.log.emit(f"Deploying frida-server to {serial}…", "info")
        worker = DeployWorker(serial)
        worker.progress.connect(self.log)
        worker.finished_ok.connect(self._on_ok)
        worker.failed.connect(self._on_failed)
        worker.finished.connect(self._clear_worker)
        self._worker = worker
        worker.start()

    def check_running(self, serial: str) -> bool:
        return _server_pid(serial) is not None

    def stop(self, serial: str) -> None:
        self.log.emit("Stopping frida-server…", "info")
        prefix = _root_prefix(serial) or []
        kill = (prefix + ["pkill -f frida-server"]) if prefix else ["pkill -f frida-server"]
        try:
            run_adb(["shell", *kill], serial=serial)
            self.log.emit("frida-server stopped.", "info")
        except (subprocess.SubprocessError, OSError) as exc:
            self.error.emit(f"Failed to stop frida-server: {exc}")

    def _on_ok(self, pid: str) -> None:
        self.deployed.emit(pid)

    def _on_failed(self, message: str) -> None:
        self.error.emit(message)
        self.log.emit(message, "error")

    def _clear_worker(self) -> None:
        self._worker = None
        self.busy_changed.emit(False)
