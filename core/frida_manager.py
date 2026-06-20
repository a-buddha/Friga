""" Talking to frida.
Uses the frida-python API directly (not the CLI) to see the device, list its
processes and attach to or spawn an app. The blocking calls run on worker threads
and frida's own callbacks come back to the UI thread over signals """

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

import frida
from PyQt6.QtCore import QObject, QThread, pyqtSignal


class AttachMode(str, Enum):
    ATTACH = "attach"  # hook a process that's already running
    SPAWN = "spawn"    # launch the app under instrumentation from the start


@dataclass
class ProcessInfo:
    pid: int
    name: str


@dataclass
class SessionInfo:
    pid: int
    name: str
    serial: str


def _friendly_error(exc: Exception) -> str:
    if isinstance(exc, frida.ServerNotRunningError):
        return (
            "frida-server is not running on the device. Deploy it from the "
            "frida-server panel first."
        )
    if isinstance(exc, frida.ProcessNotFoundError):
        return "Target process not found — it may have exited."
    if isinstance(exc, frida.PermissionDeniedError):
        return "Permission denied by frida-server (is it running as root?)."
    if isinstance(exc, frida.InvalidArgumentError):
        return f"Invalid target: {exc}"
    return f"{type(exc).__name__}: {exc}"


def _get_device(serial: str) -> frida.core.Device:
    return frida.get_device_manager().get_device(serial)


class ProcessListWorker(QThread):
    listed = pyqtSignal(list)
    failed = pyqtSignal(str)

    def __init__(self, serial: str, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._serial = serial

    def run(self) -> None:
        try:
            device = _get_device(self._serial)
            procs = device.enumerate_processes()
            self.listed.emit([ProcessInfo(p.pid, p.name) for p in procs])
        except Exception as exc:
            self.failed.emit(_friendly_error(exc))


class AttachWorker(QThread):
    attached = pyqtSignal(object, int, str)
    failed = pyqtSignal(str)

    def __init__(
        self,
        serial: str,
        mode: AttachMode,
        target: str,
        display_name: str,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._serial = serial
        self._mode = mode
        self._target = target
        self._display_name = display_name

    def run(self) -> None:
        try:
            device = _get_device(self._serial)
            if self._mode is AttachMode.SPAWN:
                pid = device.spawn([self._target])
                session = device.attach(pid)
                device.resume(pid)  # let the app actually run
                name = self._target
            else:
                pid = int(self._target)
                session = device.attach(pid)
                name = self._display_name
            self.attached.emit(session, pid, name)
        except Exception as exc:
            self.failed.emit(_friendly_error(exc))


class FridaManager(QObject):
    processes_listed = pyqtSignal(list)
    session_started = pyqtSignal(object)
    session_stopped = pyqtSignal(str)
    log = pyqtSignal(str, str)
    error = pyqtSignal(str)
    busy_changed = pyqtSignal(bool)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._session: frida.core.Session | None = None
        self._info: SessionInfo | None = None
        self._list_worker: ProcessListWorker | None = None
        self._attach_worker: AttachWorker | None = None
        # Clearing the session runs on the UI thread via this self-connection.
        self.session_stopped.connect(self._clear_session)

    @property
    def session_info(self) -> SessionInfo | None:
        return self._info

    @property
    def has_session(self) -> bool:
        return self._session is not None

    @property
    def busy(self) -> bool:
        return self._attach_worker is not None and self._attach_worker.isRunning()

    def list_processes(self, serial: str) -> None:
        if self._list_worker is not None and self._list_worker.isRunning():
            return
        self.log.emit("Listing processes on device…", "info")
        worker = ProcessListWorker(serial)
        worker.listed.connect(self._on_listed)
        worker.failed.connect(self._on_error)
        worker.finished.connect(lambda: setattr(self, "_list_worker", None))
        self._list_worker = worker
        worker.start()

    def attach(self, serial: str, pid: int, name: str) -> None:
        self._start_attach(serial, AttachMode.ATTACH, str(pid), name)

    def spawn(self, serial: str, identifier: str) -> None:
        self._start_attach(serial, AttachMode.SPAWN, identifier, identifier)

    def _start_attach(
        self, serial: str, mode: AttachMode, target: str, display_name: str
    ) -> None:
        if self._attach_worker is not None and self._attach_worker.isRunning():
            return
        if self.has_session:
            self.detach()
        self.busy_changed.emit(True)
        verb = "Spawning" if mode is AttachMode.SPAWN else "Attaching to"
        self.log.emit(f"{verb} {display_name}…", "info")
        worker = AttachWorker(serial, mode, target, display_name)
        worker.attached.connect(lambda s, p, n: self._on_attached(s, p, n, serial))
        worker.failed.connect(self._on_attach_failed)
        worker.finished.connect(self._clear_attach_worker)
        self._attach_worker = worker
        worker.start()

    def detach(self) -> None:
        if self._session is None:
            return
        try:
            self._session.detach()
        except Exception:
            pass
        # _on_detached fires and emits session_stopped.

    def _on_attached(
        self, session: frida.core.Session, pid: int, name: str, serial: str
    ) -> None:
        self._session = session
        self._info = SessionInfo(pid=pid, name=name, serial=serial)
        session.on("detached", self._on_detached)
        self.log.emit(f"Session established: {name} (PID {pid}).", "success")
        self.session_started.emit(self._info)

    def _on_detached(self, reason: str, *args: object) -> None:
        # Runs on a frida thread; the queued signal hops to the UI thread.
        self.session_stopped.emit(str(reason))

    def _on_listed(self, processes: list[ProcessInfo]) -> None:
        self.log.emit(f"Found {len(processes)} process(es).", "info")
        self.processes_listed.emit(processes)

    def _on_error(self, message: str) -> None:
        self.error.emit(message)
        self.log.emit(message, "error")

    def _on_attach_failed(self, message: str) -> None:
        self._on_error(message)

    def _clear_attach_worker(self) -> None:
        self._attach_worker = None
        self.busy_changed.emit(False)

    def _clear_session(self, reason: str) -> None:
        if self._info is not None:
            self.log.emit(f"Session detached ({reason}): {self._info.name}.", "warning")
        self._session = None
        self._info = None
