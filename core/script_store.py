""" Saving and loading the user's Frida scripts.
Each script is just a .js file under scripts/. No Qt in here so it's easy to test
on its own """

from __future__ import annotations

import re
from pathlib import Path

from .resources import SCRIPTS_DIR

_EXT = ".js"
_SAFE_NAME = re.compile(r"^[\w .\-]+$")


class ScriptStoreError(Exception):
    pass


class ScriptStore:
    def __init__(self, directory: Path | None = None) -> None:
        self._dir = directory or SCRIPTS_DIR
        self._dir.mkdir(parents=True, exist_ok=True)

    @property
    def directory(self) -> Path:
        return self._dir

    def _path_for(self, name: str) -> Path:
        name = name.strip()
        if not name:
            raise ScriptStoreError("Script name cannot be empty.")
        if not _SAFE_NAME.match(name):
            raise ScriptStoreError(
                "Script name may only contain letters, digits, spaces, '.', '-', '_'."
            )
        return self._dir / f"{name}{_EXT}"

    def list_scripts(self) -> list[str]:
        names = [p.stem for p in self._dir.glob(f"*{_EXT}") if p.is_file()]
        return sorted(names, key=str.lower)

    def load(self, name: str) -> str:
        path = self._path_for(name)
        if not path.is_file():
            raise ScriptStoreError(f"Script '{name}' does not exist.")
        return path.read_text(encoding="utf-8")

    def save(self, name: str, content: str) -> None:
        path = self._path_for(name)
        try:
            path.write_text(content, encoding="utf-8")
        except OSError as exc:
            raise ScriptStoreError(f"Could not save '{name}': {exc}") from exc

    def delete(self, name: str) -> None:
        path = self._path_for(name)
        if not path.is_file():
            raise ScriptStoreError(f"Script '{name}' does not exist.")
        try:
            path.unlink()
        except OSError as exc:
            raise ScriptStoreError(f"Could not delete '{name}': {exc}") from exc

    def exists(self, name: str) -> bool:
        try:
            return self._path_for(name).is_file()
        except ScriptStoreError:
            return False
