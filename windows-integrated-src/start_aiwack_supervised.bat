@echo off
setlocal
cd /d "%~dp0"
REM Explicit user opt-in; no Windows autostart or external service.
if not exist "dist\AIWACK.exe" (
  echo Missing AIWACK.exe. Build it locally first.
  pause
  exit /b 1
)
if not exist "dist\AIWACKSupervisor.exe" (
  echo Missing AIWACKSupervisor.exe. Build it locally first.
  pause
  exit /b 1
)
"dist\AIWACKSupervisor.exe" "dist\AIWACK.exe"
set "RESULT=%errorlevel%"
echo Supervisor exit code: %RESULT%
pause
exit /b %RESULT%
