@echo off
setlocal
cd /d "%~dp0"
where py >nul 2>&1
if %errorlevel%==0 (set "PY=py -3") else (set "PY=python")
%PY% --version >nul 2>&1
if errorlevel 1 (
  echo Python was not found. For normal use, download AIWACK.exe from GitHub Actions. It needs no Python install.
  pause
  exit /b 1
)
%PY% -m desktop.entry
if errorlevel 1 (
  echo Failed to start the native desktop program.
  pause
  exit /b 1
)
