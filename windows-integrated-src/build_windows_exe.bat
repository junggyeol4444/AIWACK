@echo off
setlocal
cd /d "%~dp0"
where py >nul 2>&1
if %errorlevel%==0 (set "PY=py -3") else (set "PY=python")
%PY% --version >nul 2>&1
if errorlevel 1 (
  echo Windows Python 3.11+ is required to build an EXE locally.
  pause
  exit /b 1
)
REM Do not silently download/install dependencies or connect to GitHub.
%PY% -m PyInstaller --version >nul 2>&1
if errorlevel 1 (
  echo PyInstaller is not installed locally. No network request was made.
  echo To build offline, install PyInstaller on this PC in advance,
  echo or install a downloaded wheel from local storage yourself.
  echo The finished AIWACK.exe runs without Python, PyInstaller or GitHub.
  pause
  exit /b 1
)
%PY% -m PyInstaller --noconfirm --clean --onefile --windowed --name AIWACK --paths . --add-data "docs/roadmap_100.csv;docs" desktop/entry.py
if errorlevel 1 ( echo Build failed. & pause & exit /b 1 )
REM A Windows GUI-subsystem EXE may return before it exits in plain cmd.
REM Start-Process -Wait checks the REAL EXE exit code (no internet needed).
powershell -NoProfile -Command "$p = Start-Process -FilePath (Resolve-Path '.\dist\AIWACK.exe') -ArgumentList '--self-test' -PassThru -Wait; exit $p.ExitCode"
if errorlevel 1 ( echo EXE data self-test failed. & pause & exit /b 1 )
echo Build complete: dist\AIWACK.exe
pause
