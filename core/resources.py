""" Locating the external tools the app shells out to
ADB, the frida-server binaries, and the APK-patching tools (apktool, apksigner, a
bundled JRE, and the frida-gadget .so files). The scan looks for a bundled copy under
``bundled/`` because the app is meant to be shipped self contained, and falls back to
whatever's on PATH, which is useful while developing """

from __future__ import annotations

import platform
import shutil
from pathlib import Path

APP_ROOT = Path(__file__).resolve().parent.parent
BUNDLED_DIR = APP_ROOT / "bundled"
SCRIPTS_DIR = APP_ROOT / "scripts"


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


# Android ABI (ro.product.cpu.abi) -> the frida-server build folder under bundled/
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


# Frida 17 dropped the global Java/ObjC bridges, so scripts using Java need it
# prepended. This is the bridge precompiled to a single IIFE that sets globalThis.Java.
def read_java_bridge() -> str | None:
    bridge = BUNDLED_DIR / "agent" / "java-bridge.js"
    if bridge.is_file():
        return bridge.read_text(encoding="utf-8")
    return None


# --- APK patching tools ---

def _resolve_jre_bin(name: str) -> str:
    exe = _exe(name)
    bundled = BUNDLED_DIR / "jre" / _platform_dir() / "bin" / exe
    if bundled.is_file():
        return str(bundled)
    on_path = shutil.which(name)
    if on_path:
        return on_path
    raise FileNotFoundError(
        f"Couldn't find '{name}'. Looked for a bundled JRE at '{bundled}' and on PATH."
    )


def resolve_java() -> str:
    return _resolve_jre_bin("java")


def resolve_keytool() -> str:
    return _resolve_jre_bin("keytool")


def _resolve_jar(tool: str) -> str:
    jar = BUNDLED_DIR / tool / f"{tool}.jar"
    if not jar.is_file():
        raise FileNotFoundError(f"Missing bundled {tool}. Expected it at '{jar}'.")
    return str(jar)


def resolve_apktool_jar() -> str:
    return _resolve_jar("apktool")


def resolve_apksigner_jar() -> str:
    return _resolve_jar("apksigner")


def resolve_gadget(arch: str) -> str:
    if arch not in FRIDA_ARCHES:
        raise ValueError(f"Unknown gadget arch: {arch!r}")
    so = BUNDLED_DIR / "gadgets" / arch / "libfrida-gadget.so"
    if not so.is_file():
        raise FileNotFoundError(f"No bundled frida-gadget for '{arch}'. Expected it at '{so}'.")
    return str(so)
