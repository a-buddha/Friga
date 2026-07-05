""" One-click APK patching for the non-rooted (frida-gadget) path.
Decompiles the APK with apktool, drops the matching libfrida-gadget.so (plus a
config so the app resumes on its own instead of hanging), injects a
System.loadLibrary into the entry-point class, rebuilds, signs with a debug key,
and installs. Every step streams to the console; it all runs on a worker thread """

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

from PyQt6.QtCore import QObject, QThread, pyqtSignal

from .adb_manager import run_adb
from .resources import (
    APP_ROOT,
    frida_arch_for_abi,
    is_windows,
    resolve_apksigner_jar,
    resolve_apktool_jar,
    resolve_gadget,
    resolve_java,
    resolve_keytool,
)

_CREATE_NO_WINDOW = 0x08000000 if is_windows() else 0
_ANDROID_NS = "{http://schemas.android.com/apk/res/android}"
_STEP_TIMEOUT = 300

# Gadget config: listen but resume on load, so the app runs normally and can be
# attached to at any time (no bootstrap script needed).
_GADGET_CONFIG = {
    "interaction": {
        "type": "listen",
        "address": "127.0.0.1",
        "port": 27042,
        "on_load": "resume",
    }
}

_KEYSTORE = APP_ROOT / "keystore" / "debug.keystore"
_OUTPUT_DIR = APP_ROOT / "output"


def _run(cmd: list[str], timeout: int = _STEP_TIMEOUT) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=timeout,
        creationflags=_CREATE_NO_WINDOW,
    )


def _apk_abis(apk: Path) -> set[str]:
    abis: set[str] = set()
    with zipfile.ZipFile(apk) as z:
        for name in z.namelist():
            if name.startswith("lib/") and name.count("/") >= 2:
                abis.add(name.split("/")[1])
    return abis


def _device_abis(serial: str) -> list[str]:
    result = run_adb(["shell", "getprop", "ro.product.cpu.abilist"], serial=serial)
    abis = [a.strip() for a in (result.stdout or "").split(",") if a.strip()]
    if abis:
        return abis
    single = run_adb(["shell", "getprop", "ro.product.cpu.abi"], serial=serial)
    return [single.stdout.strip()] if single.stdout.strip() else []


def _choose_abi(apk: Path, serial: str) -> str:
    device_abis = _device_abis(serial)
    apk_abis = _apk_abis(apk)
    if apk_abis:
        for abi in device_abis:
            if abi in apk_abis:
                return abi
        return sorted(apk_abis)[0]
    return device_abis[0] if device_abis else "arm64-v8a"


def _manifest_targets(manifest: Path) -> tuple[str, str | None, str | None]:
    """Return (package, application class, launcher activity) from the manifest."""
    root = ET.parse(manifest).getroot()
    package = root.get("package") or ""
    app = root.find("application")
    app_name = app.get(f"{_ANDROID_NS}name") if app is not None else None
    launcher = None
    if app is not None:
        for act in list(app.findall("activity")) + list(app.findall("activity-alias")):
            for intent in act.findall("intent-filter"):
                actions = {a.get(f"{_ANDROID_NS}name") for a in intent.findall("action")}
                cats = {c.get(f"{_ANDROID_NS}name") for c in intent.findall("category")}
                if "android.intent.action.MAIN" in actions and \
                        "android.intent.category.LAUNCHER" in cats:
                    launcher = act.get(f"{_ANDROID_NS}targetActivity") or \
                        act.get(f"{_ANDROID_NS}name")
                    break
            if launcher:
                break
    return package, app_name, launcher


def _fqcn(name: str, package: str) -> str:
    if name.startswith("."):
        return package + name
    if "." not in name:
        return f"{package}.{name}"
    return name


def _find_smali(decompiled: Path, fqcn: str) -> Path | None:
    rel = fqcn.replace(".", "/") + ".smali"
    for smali_dir in sorted(decompiled.glob("smali*")):
        candidate = smali_dir / rel
        if candidate.is_file():
            return candidate
    return None


_LOAD_LINES = [
    '    const-string v0, "frida-gadget"',
    "    invoke-static {v0}, Ljava/lang/System;->loadLibrary(Ljava/lang/String;)V",
]


def _inject_loadlibrary(smali: Path) -> None:
    lines = smali.read_text(encoding="utf-8").splitlines()

    # Existing static constructor -> prepend our two instructions.
    for i, line in enumerate(lines):
        if line.strip().startswith(".method") and "constructor <clinit>()V" in line:
            j = i + 1
            while j < len(lines) and not (
                lines[j].strip().startswith(".locals")
                or lines[j].strip().startswith(".registers")
            ):
                j += 1
            if j < len(lines):
                parts = lines[j].split()
                count = int(parts[1]) if len(parts) > 1 else 0
                if count < 1:
                    lines[j] = f"    {parts[0]} 1"
                lines[j + 1:j + 1] = _LOAD_LINES
                smali.write_text("\n".join(lines) + "\n", encoding="utf-8")
                return
            break

    # No static constructor -> add one before the first method (or at the end).
    new_clinit = [
        ".method static constructor <clinit>()V",
        "    .locals 1",
        *_LOAD_LINES,
        "    return-void",
        ".end method",
        "",
    ]
    idx = next((k for k, l in enumerate(lines) if l.strip().startswith(".method ")), None)
    if idx is None:
        lines += [""] + new_clinit
    else:
        lines[idx:idx] = new_clinit
    smali.write_text("\n".join(lines) + "\n", encoding="utf-8")


class PatchWorker(QThread):
    progress = pyqtSignal(int, int, str)  # step, total, label
    log = pyqtSignal(str, str)
    finished_ok = pyqtSignal(str)         # installed package name
    failed = pyqtSignal(str)

    _TOTAL = 7

    def __init__(self, apk: str, serial: str, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._apk = Path(apk)
        self._serial = serial

    def run(self) -> None:
        work = Path(tempfile.mkdtemp(prefix="friga-patch-"))
        try:
            self._patch(work)
        except FileNotFoundError as exc:
            self.failed.emit(str(exc))
        except subprocess.TimeoutExpired:
            self.failed.emit("A patching step timed out.")
        except Exception as exc:  # surface anything else rather than crashing
            self.failed.emit(f"Patching error: {type(exc).__name__}: {exc}")
        finally:
            shutil.rmtree(work, ignore_errors=True)

    def _step(self, n: int, label: str) -> None:
        self.progress.emit(n, self._TOTAL, label)
        self.log.emit(f"[{n}/{self._TOTAL}] {label}", "info")

    def _patch(self, work: Path) -> None:
        if not self._apk.is_file():
            self.failed.emit(f"APK not found: {self._apk}")
            return

        java = resolve_java()
        apktool = resolve_apktool_jar()

        # 1) arch
        self._step(1, "Detecting target architecture…")
        abi = _choose_abi(self._apk, self._serial)
        arch = frida_arch_for_abi(abi)
        if arch is None:
            self.failed.emit(f"Unsupported ABI '{abi}' — no matching frida-gadget.")
            return
        self.log.emit(f"Using ABI '{abi}' → gadget arch '{arch}'.", "info")

        # 2) decompile
        self._step(2, "Decompiling APK (apktool)…")
        decompiled = work / "decompiled"
        r = _run([java, "-jar", apktool, "d", "-f", "-o", str(decompiled), str(self._apk)])
        if r.returncode != 0:
            self.failed.emit(r.stderr.strip() or "apktool decode failed.")
            return

        # 3) gadget + config
        self._step(3, "Injecting frida-gadget library…")
        lib_dir = decompiled / "lib" / abi
        lib_dir.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(resolve_gadget(arch), lib_dir / "libfrida-gadget.so")
        (lib_dir / "libfrida-gadget.config.so").write_text(
            json.dumps(_GADGET_CONFIG), encoding="utf-8"
        )

        # 4) smali loadLibrary
        self._step(4, "Patching entry-point smali…")
        package, app_name, launcher = _manifest_targets(decompiled / "AndroidManifest.xml")
        target = None
        for candidate in (app_name, launcher):
            if candidate:
                target = _find_smali(decompiled, _fqcn(candidate, package))
                if target:
                    break
        if target is None:
            self.failed.emit("Could not locate the app's entry-point smali to patch.")
            return
        _inject_loadlibrary(target)
        self.log.emit(f"Injected loadLibrary into {target.name}.", "info")

        # 5) rebuild
        self._step(5, "Rebuilding APK (apktool)…")
        unsigned = work / "patched-unsigned.apk"
        r = _run([java, "-jar", apktool, "b", "-f", "-o", str(unsigned), str(decompiled)])
        if r.returncode != 0 or not unsigned.is_file():
            self.failed.emit(r.stderr.strip() or "apktool build failed.")
            return

        # 6) sign
        self._step(6, "Signing patched APK…")
        _OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        signed = _OUTPUT_DIR / f"{self._apk.stem}-frida.apk"
        self._ensure_keystore()
        r = _run([
            java, "-jar", resolve_apksigner_jar(), "sign",
            "--ks", str(_KEYSTORE),
            "--ks-pass", "pass:android",
            "--key-pass", "pass:android",
            "--ks-key-alias", "androiddebugkey",
            "--out", str(signed), str(unsigned),
        ])
        if r.returncode != 0 or not signed.is_file():
            self.failed.emit(r.stderr.strip() or "apksigner failed.")
            return

        # 7) install
        self._step(7, "Installing on device…")
        if not self._install(signed, package):
            return

        self.log.emit(f"Patched APK saved to {signed}", "success")
        self.finished_ok.emit(package or self._apk.stem)

    def _ensure_keystore(self) -> None:
        if _KEYSTORE.is_file():
            return
        _KEYSTORE.parent.mkdir(parents=True, exist_ok=True)
        self.log.emit("Generating debug keystore…", "info")
        r = _run([
            resolve_keytool(), "-genkeypair", "-v",
            "-keystore", str(_KEYSTORE),
            "-storepass", "android", "-keypass", "android",
            "-alias", "androiddebugkey",
            "-keyalg", "RSA", "-keysize", "2048", "-validity", "10000",
            "-dname", "CN=Android Debug,O=Android,C=US",
        ])
        if r.returncode != 0:
            raise RuntimeError(r.stderr.strip() or "keytool failed to create a keystore.")

    def _install(self, apk: Path, package: str) -> bool:
        r = run_adb(["install", "-r", str(apk)], serial=self._serial, timeout=_STEP_TIMEOUT)
        out = (r.stdout or "") + (r.stderr or "")
        if r.returncode == 0 and "Success" in out:
            return True
        # A re-signed app clashes with an existing install — remove and retry.
        if package and ("INSTALL_FAILED_UPDATE_INCOMPATIBLE" in out or "signatures do not match" in out):
            self.log.emit("Existing install has a different signature — reinstalling…", "warning")
            run_adb(["uninstall", package], serial=self._serial, timeout=60)
            r = run_adb(["install", str(apk)], serial=self._serial, timeout=_STEP_TIMEOUT)
            if r.returncode == 0 and "Success" in ((r.stdout or "") + (r.stderr or "")):
                return True
        self.failed.emit(out.strip() or "adb install failed.")
        return False


class Patcher(QObject):
    log = pyqtSignal(str, str)
    error = pyqtSignal(str)
    finished = pyqtSignal(str)            # installed package
    busy_changed = pyqtSignal(bool)
    progress = pyqtSignal(int, int, str)  # step, total, label

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._worker: PatchWorker | None = None

    @property
    def is_busy(self) -> bool:
        return self._worker is not None and self._worker.isRunning()

    def patch(self, apk: str, serial: str) -> None:
        if self.is_busy:
            return
        self.busy_changed.emit(True)
        self.log.emit(f"Patching {Path(apk).name}…", "info")
        worker = PatchWorker(apk, serial)
        worker.progress.connect(self.progress)
        worker.log.connect(self.log)
        worker.finished_ok.connect(self._on_ok)
        worker.failed.connect(self._on_failed)
        worker.finished.connect(self._clear_worker)
        self._worker = worker
        worker.start()

    def _on_ok(self, package: str) -> None:
        self.log.emit(f"Done. Installed '{package}' — launch it and attach with Frida.", "success")
        self.finished.emit(package)

    def _on_failed(self, message: str) -> None:
        self.error.emit(message)
        self.log.emit(message, "error")

    def _clear_worker(self) -> None:
        self._worker = None
        self.busy_changed.emit(False)
