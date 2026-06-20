""" Locating the external tools the app shells out to
For now that's just ADB. The scan will look for a bundled copy under ``bundled/`` 
because the app is meant to be shipped self contained in the future, and then fall back to whatever's on PATH in
the environment variables, useful while developing """

from __future__ import annotations

import platform
import shutil
from pathlib import Path

APP_ROOT = Path(__file__).resolve().parent.parent
BUNDLED_DIR = APP_ROOT / "bundled"

def is_windows() -> bool:
    return platform.system() == "Windows"

def _platform_dir() -> str:
    return "win" if is_windows() else "linux"

def _exe(name: str) -> str:
    return f"{name}.exe" if is_windows() else name

def resolve_tool(tool: str, exe_name: str) -> str:
    bundled = BUNDLED_DIR / tool / _platform_dir() / _exe(exe_name)
    if bundled.is_file():
        return str(bundled)

    on_path = shutil.which(exe_name)
    if on_path:
        return on_path

    raise FileNotFoundError(
        f"Couldn't find '{exe_name}'. Looked for a bundled copy at "
        f"'{bundled}' and on the system PATH."
    )

def resolve_adb() -> str:
    return resolve_tool("adb", "adb")

_ABI_TO_FRIDA_ARCH = {
    "arm64-v8a": "arm64",
    "armeabi-v7a": "arm",
    "armeabi": "arm",
    "x86_64": "x86_64",
    "x86": "x86",
}

FRIDA_ARCHES = ("arm", "arm64", "x86", "x86_64")

def frida_arch_for_abi(abi: str) -> str | None:
    return _ABI_TO_FRIDA_ARCH.get(abi.strip())

def resolve_frida_server(arch: str) -> str:
    if arch not in FRIDA_ARCHES:
        raise ValueError(f"Unknown frida-server arch: {arch!r}")
    binary = BUNDLED_DIR / "frida-server" / arch / "frida-server"
    if not binary.is_file():
        raise FileNotFoundError(
            f"No bundled frida-server for '{arch}'. Expected it at '{binary}'."
        )
    return str(binary)
