@echo off
REM Build EZ Text Compare on Windows. Double-click or run from a terminal.
REM First run creates a clean virtual environment in .venv so builds are repeatable.
setlocal
cd /d "%~dp0"

where py >nul 2>nul
if errorlevel 1 (
  echo Python launcher "py" not found. Install Python 3.12 64-bit from python.org first.
  pause
  exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
  echo Creating virtual environment...
  py -3.12 -m venv .venv 2>nul || py -3 -m venv .venv || goto :fail
)

".venv\Scripts\python.exe" -m pip install --upgrade pip >nul
".venv\Scripts\python.exe" -m pip install -r requirements.txt -r requirements-dev.txt || goto :fail
".venv\Scripts\python.exe" build.py %* || goto :fail

echo.
echo Build finished. See the dist folder.
pause
exit /b 0

:fail
echo.
echo Build failed. Scroll up for the error.
pause
exit /b 1
