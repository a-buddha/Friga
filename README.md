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

Device discovery and the output console is the first sprint of this application development; pushing frida-server to a device, attaching to a process, and a script editor will all be built gradually throughout the course of my semester

## What works so far
~ Detects USB-connected Android devices over ADB (serial, model, Android version,
 connection status), running on a background thread so that the UI never freezes\
~ An output console that keeps the full log for the session\
~ Dark theme

## To Run
Needs Python 3.10 and ADB on PATH environment variables.\

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

