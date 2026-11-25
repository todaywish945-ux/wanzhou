@echo off
setlocal
pushd "%~dp0"
start "" "%~dp0venv\Scripts\pythonw.exe" -m pet --slot 1 --instance A --character A
start "" "%~dp0venv\Scripts\pythonw.exe" -m pet --slot 2 --instance B --character B
start "" "%~dp0venv\Scripts\pythonw.exe" -m pet --slot 3 --instance C --character C
popd
endlocal
