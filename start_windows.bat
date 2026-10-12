@echo off
setlocal
cd /d "%~dp0"
where py >nul 2>&1
if %errorlevel%==0 (set "PY=py -3") else (set "PY=python")
%PY% --version >nul 2>&1
if errorlevel 1 (
  echo Python 3.11 or newer is required. Ask for setup instructions.
  pause
  exit /b 1
)
if not exist .venv\Scripts\python.exe (
  %PY% -m venv .venv
  if errorlevel 1 (echo Failed to create Python environment & pause & exit /b 1)
)
.venv\Scripts\python.exe -m pip install -e ".[dev]"
if errorlevel 1 (echo Dependency installation failed & pause & exit /b 1)
echo When Uvicorn shows Running, open http://127.0.0.1:8000/diagnostics in your browser
.venv\Scripts\python.exe scripts\launch_local.py
pause
