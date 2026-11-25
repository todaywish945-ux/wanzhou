@echo off
cd /d %~dp0
start "" "%~dp0venv\Scripts\pythonw.exe" -m pet --slot 2 --instance B --character B
