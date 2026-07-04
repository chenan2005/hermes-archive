@echo off
REM sing-box-ctrl wrapper for Windows
REM Place the parent directory in PATH to use "sing-box-ctrl <subcommand>" from anywhere
cd /d "%~dp0"
python "%~dp0sing-box-ctrl.py" %*
