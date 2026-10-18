@echo off
cd /d "%~dp0"
py -3.12 app.py --open
if errorlevel 1 pause
