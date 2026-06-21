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
Will be updated after completion

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

