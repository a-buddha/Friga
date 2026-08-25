""" Talking to frida.
Uses the frida-python API directly (not the CLI) to see the device, list its
processes and attach to or spawn an app. The blocking calls run on worker threads
and frida's own callbacks come back to the UI thread over signals.

Spawn is early instrumentation done the way `frida -f` does it: spawn the process
(created suspended), attach, load the script, and resume — all back-to-back on one
worker thread. The suspend window is milliseconds, so hooks (anti-root, SSL
unpinning) are in place before the app's first line runs, and Android's activity
watchdog never gets a chance to kill a process that's sitting frozen. Holding a
spawn suspended while waiting for a human to press Run does NOT work — Android
terminates the app after a few seconds — so the script must be prepared first.
"""

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


def _assemble(source: str, inject_java: bool) -> tuple[str, int]:
    """Return (final source, line offset) after optionally prepending the bridge."""
    if not inject_java:
        return source, 0
    bridge = read_java_bridge()
    if bridge is None:
        return source, 0
    # The bridge is prepended, pushing the user's lines down; the offset lets a
    # frida error line map back onto what the user actually wrote.
    return f"{bridge}\n{source}", bridge.count("\n") + 1


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
    """Attach to an already-running process."""

    attached = pyqtSignal(object, int, str)
    failed = pyqtSignal(str)

    def __init__(self, serial: str, pid: int, display_name: str,
                 parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._serial = serial
        self._pid = pid
        self._display_name = display_name

    def run(self) -> None:
        try:
            device = _get_device(self._serial)
            session = device.attach(self._pid)
            self.attached.emit(session, self._pid, self._display_name)
        except Exception as exc:
            self.failed.emit(_friendly_error(exc))


class SpawnRunWorker(QThread):
    """Spawn an app and (optionally) inject a script before it runs.

    spawn -> attach -> load script -> resume, all here on the worker thread so the
    suspended window is tiny and the app is never left frozen long enough for
    Android to kill it.
    """

    ready = pyqtSignal(object, int, str, object)  # session, pid, name, script|None
    failed = pyqtSignal(str)

    def __init__(self, serial: str, identifier: str, final_source: str,
                 on_message, on_log, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._serial = serial
        self._identifier = identifier
        self._source = final_source
        self._on_message = on_message
        self._on_log = on_log

    def run(self) -> None:
        try:
            device = _get_device(self._serial)
            pid = device.spawn([self._identifier])
            session = device.attach(pid)
            script = None
            if self._source.strip():
                script = session.create_script(self._source)
                script.on("message", self._on_message)
                script.set_log_handler(self._on_log)
                script.load()          # hooks installed while still suspended
            device.resume(pid)         # now the app actually runs
            self.ready.emit(session, pid, self._identifier, script)
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
    # A runtime error from the script: (line, column, message, line_offset). The
    # line/column are in the *assembled* source frida ran; line_offset is how many
    # lines we prepended (the Java bridge), so the UI can map it back onto what the
    # user actually typed. The editor gutter listens for this.
    script_error = pyqtSignal(int, int, str, int)
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
        self._spawn_worker: SpawnRunWorker | None = None
        self._script_worker: ScriptRunWorker | None = None
        # Lines prepended to the last-run script (the Java bridge), so a frida error
        # line can be mapped back onto the user's own source.
        self._line_offset = 0
        # Clearing the session runs on the UI thread via this self-connection.
        self.session_stopped.connect(self._clear_session)

    @property
    def session_info(self) -> SessionInfo | None:
        return self._info

    @property
    def has_session(self) -> bool:
        return self._session is not None

    @property
    def has_script(self) -> bool:
        return self._script is not None

    @property
    def busy(self) -> bool:
        return any(
            w is not None and w.isRunning()
            for w in (self._attach_worker, self._spawn_worker)
        )

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
        if self.busy:
            return
        if self.has_session:
            self.detach()
        self.busy_changed.emit(True)
        self.log.emit(f"Attaching to {name}…", "info")
        worker = AttachWorker(serial, pid, name)
        worker.attached.connect(lambda s, p, n: self._on_attached(s, p, n, serial))
        worker.failed.connect(self._on_attach_failed)
        worker.finished.connect(self._clear_attach_worker)
        self._attach_worker = worker
        worker.start()

    def spawn_and_run(
        self, serial: str, identifier: str, source: str = "", inject_java: bool = True
    ) -> None:
        """Spawn an app and inject the given script before it runs.

        With a non-empty source this is true early instrumentation. With an empty
        source it just launches the app under Frida and resumes it.
        """
        if self.busy:
            return
        if self.has_session:
            self.detach()
        # Only build a script when the editor actually has one — otherwise the
        # bridge prepend alone would make an "empty" spawn load a bridge-only script.
        if source.strip():
            final_source, self._line_offset = _assemble(source, inject_java)
            if inject_java and read_java_bridge() is None:
                self.log.emit(
                    "Java bridge bundle missing — 'Java' will be undefined in the script.",
                    "warning",
                )
        else:
            final_source, self._line_offset = "", 0
        self.busy_changed.emit(True)
        if final_source.strip():
            self.log.emit(f"Spawning {identifier} with startup instrumentation…", "info")
        else:
            self.log.emit(f"Spawning {identifier}…", "info")
        worker = SpawnRunWorker(
            serial, identifier, final_source,
            self._on_script_message, self._on_script_log,
        )
        worker.ready.connect(lambda s, p, n, sc: self._on_spawned(s, p, n, sc, serial))
        worker.failed.connect(self._on_attach_failed)
        worker.finished.connect(self._clear_spawn_worker)
        self._spawn_worker = worker
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

        final_source, self._line_offset = _assemble(source, inject_java)
        if inject_java and read_java_bridge() is None:
            self.log.emit(
                "Java bridge bundle missing — 'Java' will be undefined in the script.",
                "warning",
            )

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

    def _on_spawned(
        self, session: frida.core.Session, pid: int, name: str, script: object, serial: str
    ) -> None:
        self._session = session
        self._info = SessionInfo(pid=pid, name=name, serial=serial)
        session.on("detached", self._on_detached)
        self.session_started.emit(self._info)
        if script is not None:
            self._script = script
            self.script_state_changed.emit(True)
            self.log.emit(
                f"Spawned {name} (PID {pid}) — script injected before startup, resumed.",
                "success",
            )
        else:
            self.log.emit(f"Spawned {name} (PID {pid}) and resumed.", "success")

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
            # frida gives the fault location as lineNumber/columnNumber (camelCase);
            # forward it so the editor can put a squiggle on the offending line.
            line = message.get("lineNumber")
            if line is not None:
                try:
                    self.script_error.emit(
                        int(line),
                        int(message.get("columnNumber") or 1),
                        str(message.get("description") or detail),
                        self._line_offset,
                    )
                except (TypeError, ValueError):
                    pass

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

    def _clear_spawn_worker(self) -> None:
        self._spawn_worker = None
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
