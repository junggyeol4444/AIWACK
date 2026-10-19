@echo off
setlocal
cd /d "%~dp0"
where py >nul 2>&1
if %errorlevel%==0 (set "PY=py -3") else (set "PY=python")
%PY% --version >nul 2>&1
if errorlevel 1 (
  echo Python 3.11 or later is required to run source files. No GitHub connection is used.
  pause
  exit /b 1
)
%PY% -m desktop.entry
if errorlevel 1 (
  echo Failed to start the native desktop program.
  pause
  exit /b 1
)
