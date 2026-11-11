@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo [TuneBridge] Creating virtual environment...
    py -3 -m venv .venv 2>nul || python -m venv .venv
    if not exist ".venv\Scripts\python.exe" goto :fail
    ".venv\Scripts\python.exe" -m pip install --upgrade pip
)
".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -q -r requirements.txt
if errorlevel 1 goto :fail

".venv\Scripts\python.exe" run.py
pause
goto :eof

:fail
echo.
echo [TuneBridge] Setup failed. Install Python 3.11+ and run start.bat again.
pause
