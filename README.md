```
███████╗██████╗ ██╗ ██████╗  █████╗ 
██╔════╝██╔══██╗██║██╔════╝ ██╔══██╗
█████╗  ██████╔╝██║██║  ███╗███████║
██╔══╝  ██╔══██╗██║██║   ██║██╔══██║
██║     ██║  ██║██║╚██████╔╝██║  ██║
╚═╝     ╚═╝  ╚═╝╚═╝ ╚═════╝ ╚═╝  ╚═╝                                   
```
A desktop GUI for the Frida (https://frida.re) instrumentation toolkit, aimed at
people who want to do mobile security testing without living in the CLI. Built as
my final year project

This started as just device discovery and a console; since then I've been building it out. This includes the frida-server deployment, process attach and spawn, a script editor, and one-click APK patching. Always trying to improve the application.

## What works so far
~ Detects USB-connected Android devices over ADB (serial, model, version, status), on a background thread so the UI never freezes\
~ Pushes and starts frida-server on rooted devices/emulators, auto-matching the device architecture\
~ Lists running processes and lets you attach to one, or spawn an app fresh\
~ A JavaScript editor with a script library to write and run Frida hooks, output streamed to the console\
~ One-click APK patching that injects frida-gadget, so non-rooted devices can be instrumented too (plus a design-preview IPA screen because iOS is out of scope for the FYP)\
~ Log search with one-tap filters for sensitive keywords (password, token, etc.) to go back through a session\
~ A menu bar, toolbar, and Save/Load Project so you can reopen a session where you left off\
~ Dark theme, an output console that keeps the whole session log, and it packages into a standalone build so it runs without installing Python

## To Run
Needs Python 3.10+ and ADB on PATH environment variables.

Make a virtual environment, then run it with the venv's own Python. This skips the `activate` step, which PowerShell usually blocks with its execution policy, calling the venv Python directly always works.

**Windows (PowerShell):**
```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe main.py
```

**Linux / macOS:**
```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python main.py
```

## The tools it bundles

The external tools it uses like ADB, frida-server, the frida-gadget libraries, apktool, apksigner and a small JRE, normally live under `bundled/` but aren't checked in here because they're large. The app looks in `bundled/` first and falls back to whatever's on your PATH, so device detection works with just ADB installed and you can add the rest when you want those features.

**Easiest way:** download `friga-bundled.zip` from this repo's [Releases](../../releases) page and extract it into the project root, that drops in the whole `bundled/` folder, ready to go, no manual downloads.

To set them up by hand instead (or to use a different frida version): the Frida binaries have to match the frida version in `requirements.txt` (currently 17.12.0). Check what you've got with:

```bash
frida --version
```

Then grab the matching builds for your device's architecture (one of `arm`, `arm64`, `x86`, `x86_64`) from the Frida releases https://github.com/frida/frida/releases and unpack them into place:

- `frida-server-<version>-android-<arch>.xz`  →  `bundled/frida-server/<arch>/frida-server`
- `frida-gadget-<version>-android-<arch>.so.xz`  →  `bundled/gadgets/<arch>/libfrida-gadget.so`

For APK patching you'll also want `apktool.jar` in `bundled/apktool/` and `apksigner.jar` in `bundled/apksigner/`, plus a JRE, or just have `java`, `apktool` and `apksigner` on your PATH.

## Layout
core/   the app logic including ADB, frida sessions, server deployment, APK patching, logging\
ui/     the PyQt6 panels and the main window\
main.py entry point

