""" Session log storage
Everything that shows up in the output console goes through here first. The
manager keeps every entry for the lifetime of the session and gives a signal
whenever a new one arrives. The console panel just listens and renders. Logs are all kept
in one place so it is easier for troubleshooting or testing for later features """

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum

from PyQt6.QtCore import QObject, pyqtSignal


class LogLevel(str, Enum):
    SUCCESS = "success"
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


@dataclass
class LogEntry:
    text: str
    level: LogLevel = LogLevel.INFO
    timestamp: float = field(default_factory=time.time)

    @property
    def time_str(self) -> str:
        return time.strftime("%H:%M:%S", time.localtime(self.timestamp))


class LogManager(QObject):
    entry_added = pyqtSignal(object)
    cleared = pyqtSignal()

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._entries: list[LogEntry] = []

    @property
    def entries(self) -> list[LogEntry]:
        return list(self._entries)

    def log(self, text: str, level: LogLevel = LogLevel.INFO) -> None:
        entry = LogEntry(text=text, level=level)
        self._entries.append(entry)
        self.entry_added.emit(entry)

    def info(self, text: str) -> None:
        self.log(text, LogLevel.INFO)

    def success(self, text: str) -> None:
        self.log(text, LogLevel.SUCCESS)

    def warning(self, text: str) -> None:
        self.log(text, LogLevel.WARNING)

    def error(self, text: str) -> None:
        self.log(text, LogLevel.ERROR)

    def clear(self) -> None:
        self._entries.clear()
        self.cleared.emit()
