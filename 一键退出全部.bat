@echo off
setlocal
pushd "%~dp0"
"%~dp0venv\Scripts\python.exe" -m pet.quit_all
set "result=%errorlevel%"
popd
if not "%result%"=="0" pause
endlocal & exit /b %result%
