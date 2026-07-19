""" Talking to frida.
Uses the frida-python API directly (not the CLI) to see the device, list its
processes and attach to or spawn an app. The blocking calls run on worker threads
and frida's own callbacks come back to the UI thread over signals """

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

import frida
from PyQt6.QtCore import QObject, QThread, pyqtSignal

from .resources import read_java_bridge


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


class ScriptRunWorker(QThread):
    loaded = pyqtSignal(object)
    failed = pyqtSignal(str)

    def __init__(
        self, session, source, on_message, on_log, parent: QObject | None = None
    ) -> None:
        super().__init__(parent)
        self._session = session
        self._source = source
        self._on_message = on_message
        self._on_log = on_log

    def run(self) -> None:
        try:
            script = self._session.create_script(self._source)
            script.on("message", self._on_message)  # before load, to catch early output
            # frida-python grabs type:"log" messages itself before "message" ever sees
            # them and prints them to this process's own stdout/stderr by default — so
            # console.log/warn/error need this override or they never reach the GUI.
            script.set_log_handler(self._on_log)
            script.load()
            self.loaded.emit(script)
        except Exception as exc:
            self.failed.emit(_friendly_error(exc))


class FridaManager(QObject):
    processes_listed = pyqtSignal(list)
    session_started = pyqtSignal(object)
    session_stopped = pyqtSignal(str)
    message = pyqtSignal(str, str)           # script output -> console
    script_state_changed = pyqtSignal(bool)  # True when a script is loaded
    log = pyqtSignal(str, str)
    error = pyqtSignal(str)
    busy_changed = pyqtSignal(bool)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._session: frida.core.Session | None = None
        self._info: SessionInfo | None = None
        self._script = None
        self._list_worker: ProcessListWorker | None = None
        self._attach_worker: AttachWorker | None = None
        self._script_worker: ScriptRunWorker | None = None
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
        self._unload_script()
        try:
            self._session.detach()
        except Exception:
            pass
        # _on_detached fires and emits session_stopped.

    @property
    def has_script(self) -> bool:
        return self._script is not None

    def run_script(self, source: str, inject_java: bool = True) -> None:
        if not self.has_session:
            self._on_error("No active session — attach to or spawn a process first.")
            return
        if not source.strip():
            self.log.emit("Nothing to run: the script is empty.", "warning")
            return
        if self._script_worker is not None and self._script_worker.isRunning():
            return
        self._unload_script()

        final_source = source
        if inject_java:
            bridge = read_java_bridge()
            if bridge is None:
                self.log.emit(
                    "Java bridge bundle missing — 'Java' will be undefined in the script.",
                    "warning",
                )
            else:
                final_source = f"{bridge}\n{source}"  # one line, shifts user lines by 1

        self.busy_changed.emit(True)
        self.log.emit("Loading script into session…", "info")
        worker = ScriptRunWorker(
            self._session, final_source, self._on_script_message, self._on_script_log
        )
        worker.loaded.connect(self._on_script_loaded)
        worker.failed.connect(self._on_script_failed)
        worker.finished.connect(self._clear_script_worker)
        self._script_worker = worker
        worker.start()

    def unload_script(self) -> None:
        if self._script is not None:
            self._unload_script()
            self.log.emit("Script unloaded.", "info")

    def _unload_script(self) -> None:
        if self._script is None:
            return
        try:
            self._script.unload()
        except Exception:
            pass
        self._script = None
        self.script_state_changed.emit(False)

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

    def _on_script_message(self, message: dict, data: object) -> None:
        # Runs on a frida thread; emitting a signal hops back to the UI thread.
        # console.log/warn/error never show up here — frida intercepts type:"log"
        # messages before "message" callbacks run and hands them to the script's log
        # handler instead. See _on_script_log for that path.
        msg_type = message.get("type")
        if msg_type == "send":
            self.message.emit(str(message.get("payload", "")), "success")
        elif msg_type == "error":
            detail = message.get("description") or message.get("stack") or "Script error"
            self.message.emit(str(detail), "error")

    def _on_script_log(self, level: str, text: str) -> None:
        # Runs on a frida thread (via Script.set_log_handler, not "message" — see
        # ScriptRunWorker.run). This is what actually carries console.log/warn/error.
        mapped = {"warning": "warning", "error": "error"}.get(level, "info")
        self.message.emit(text, mapped)

    def _on_listed(self, processes: list[ProcessInfo]) -> None:
        self.log.emit(f"Found {len(processes)} process(es).", "info")
        self.processes_listed.emit(processes)

    def _on_error(self, message: str) -> None:
        self.error.emit(message)
        self.log.emit(message, "error")

    def _on_attach_failed(self, message: str) -> None:
        self._on_error(message)

    def _on_script_loaded(self, script: object) -> None:
        self._script = script
        self.log.emit("Script loaded and running.", "success")
        self.script_state_changed.emit(True)

    def _on_script_failed(self, message: str) -> None:
        self._on_error(message)

    def _clear_attach_worker(self) -> None:
        self._attach_worker = None
        self.busy_changed.emit(False)

    def _clear_script_worker(self) -> None:
        self._script_worker = None
        self.busy_changed.emit(False)

    def _clear_session(self, reason: str) -> None:
        self._unload_script()
        if self._info is not None:
            self.log.emit(f"Session detached ({reason}): {self._info.name}.", "warning")
        self._session = None
        self._info = None
