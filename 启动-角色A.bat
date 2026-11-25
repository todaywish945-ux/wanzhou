@echo off
cd /d %~dp0
start "" "%~dp0venv\Scripts\pythonw.exe" -m pet --slot 1 --instance A --character A
