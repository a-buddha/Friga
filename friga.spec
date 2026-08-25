# -*- mode: python ; coding: utf-8 -*-
# PyInstaller recipe for Friga. Onedir build (dist/Friga/Friga.exe + _internal/).
# Onedir on purpose: bundled/ is ~450 MB, onefile would re-extract it every launch
# — and QtWebEngine (which hosts the Monaco editor) is not reliable under onefile
# either, since QtWebEngineProcess.exe has to sit on disk beside its resources.
# Writable data (scripts/, output/, keystore/) is made next to the .exe at runtime.
#   build:  pyinstaller friga.spec --noconfirm

block_cipher = None

from PyInstaller.utils.hooks import collect_data_files

datas = [
    ("bundled", "bundled"),
    # assets/ carries the fonts (Inter + JetBrains Mono) *and* assets/monaco
    # (~23 MB: the vendored Monaco editor + Frida .d.ts typings), served over the
    # friga:// scheme.
    ("assets", "assets"),
]
# qtawesome ships its icon fonts + charmaps as package data; without these the
# icons silently vanish in a frozen build (the app still runs, text-only).
datas += collect_data_files("qtawesome")

hiddenimports = [
    "PyQt6.Qsci",
    # QtWebEngine's own PyInstaller hooks pull in QtWebEngineProcess.exe, the ICU
    # data and the locales; these just make sure the Python modules come along.
    "PyQt6.QtWebEngineWidgets",
    "PyQt6.QtWebEngineCore",
    "PyQt6.QtWebChannel",
    "qtawesome",
    "frida",
]

a = Analysis(
    ["main.py"],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter"],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Friga",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="Friga",
)
