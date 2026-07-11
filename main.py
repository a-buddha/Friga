
from __future__ import annotations

import sys

from PyQt6.QtWidgets import QApplication

from ui.fonts import register_bundled_fonts
from ui.main_window import MainWindow
from ui.theme import DARK_QSS


def _run_selftest(app: QApplication) -> int:
    # --selftest: build the window and check every bundled tool resolves, so we can
    # confirm a PyInstaller build actually shipped bundled/ + assets/. prints and exits.
    from PyQt6.QtCore import QTimer

    from core import resources

    window = MainWindow()
    window.show()

    probes = [
        ("adb", resources.resolve_adb),
        ("apktool.jar", resources.resolve_apktool_jar),
        ("apksigner.jar", resources.resolve_apksigner_jar),
        ("java (bundled JRE)", resources.resolve_java),
        ("frida-server x86_64", lambda: resources.resolve_frida_server("x86_64")),
        ("gadget arm64", lambda: resources.resolve_gadget("arm64")),
    ]
    ok = True
    for name, resolve in probes:
        try:
            print(f"  OK   {name} -> {resolve()}")
        except Exception as exc:
            ok = False
            print(f"  FAIL {name}: {exc}")
    print(f"  java-bridge: {'present' if resources.read_java_bridge() else 'MISSING'}")
    print("SELFTEST_OK" if ok else "SELFTEST_FAIL")

    QTimer.singleShot(200, app.quit)
    app.exec()
    return 0 if ok else 1


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("Friga")
    app.setOrganizationName("APU-FYP")  # gives QSettings a stable spot to persist the layout
    app.setStyleSheet(DARK_QSS)
    register_bundled_fonts()

    if "--selftest" in sys.argv:
        return _run_selftest(app)

    window = MainWindow()
    window.show()

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
