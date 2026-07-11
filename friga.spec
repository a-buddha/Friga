# -*- mode: python ; coding: utf-8 -*-
# PyInstaller recipe for Friga. Onedir build (dist/Friga/Friga.exe + _internal/).
# Onedir on purpose: bundled/ is ~450 MB, onefile would re-extract it every launch.
# Writable data (scripts/, output/, keystore/) is made next to the .exe at runtime.
#   build:  pyinstaller friga.spec --noconfirm

block_cipher = None

datas = [
    ("bundled", "bundled"),
    ("assets", "assets"),
]

hiddenimports = [
    "PyQt6.Qsci",
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
