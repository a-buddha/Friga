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

## What works so far
This started as a device discovery and a console; since then I've been building it out so now it includes frida-server deployment, process attach and spawn, a script editor, and one-click APK patching. More refinement and testing still to come this semester

## To Run
Needs Python 3.10 and ADB on PATH environment variables.

```bash
python -m venv .venv
source .venv/bin/activate   # For Windows: .venv\Scripts\activate
pip install -r requirements.txt
python main.py
```

## Layout
core/   logic for device detection and logging\
ui/     the PyQt6 panels and the main window\
main.py entry point

