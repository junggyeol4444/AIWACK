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
REM Keep the same native company imports as the Windows 2022/2025 Actions EXE builder.
REM The release must contain the company office, operations, and local model GUI.
%PY% -m PyInstaller --noconfirm --clean --onefile --windowed --name AIWACK --paths . --hidden-import desktop.company_operations --hidden-import desktop.company_office_gui --hidden-import desktop.company_model_connect_ui --hidden-import desktop.company_campaign --hidden-import desktop.company_deliverables --hidden-import desktop.company_backup --hidden-import desktop.company_handoffs --hidden-import desktop.company_autopilot --hidden-import desktop.company_continuity --hidden-import desktop.company_staff_metrics --hidden-import desktop.company_department_collaboration --hidden-import desktop.company_department_progress --hidden-import desktop.company_chief_review_leases --hidden-import desktop.company_collaboration_coverage --hidden-import desktop.company_approved_tool_execution --hidden-import desktop.company_native_diagnostics --hidden-import desktop.company_meeting_ai --hidden-import desktop.company_campaign_resume_gate --hidden-import desktop.company_campaign_plan_provenance --hidden-import desktop.company_campaign_owner_dossier --hidden-import desktop.company_campaign_chain_integrity --hidden-import desktop.company_owner_operational_summary --hidden-import desktop.company_wide_campaign --hidden-import desktop.company_failure_followups --hidden-import desktop.company_payment_reconciliation --hidden-import desktop.company_business_ideas_model --hidden-import desktop.company_business_idea_pipeline --hidden-import desktop.company_business_idea_delivery --hidden-import desktop.company_staff_reallocation --add-data "docs/roadmap_100.csv;docs" desktop/entry.py
if errorlevel 1 ( echo Build failed. & pause & exit /b 1 )
REM A Windows GUI-subsystem EXE may return before it exits in plain cmd.
REM Start-Process -Wait checks the REAL EXE exit code (no internet needed).
powershell -NoProfile -Command "$p = Start-Process -FilePath (Resolve-Path '.\dist\AIWACK.exe') -ArgumentList '--self-test' -PassThru -Wait; exit $p.ExitCode"
if errorlevel 1 ( echo EXE data self-test failed. & pause & exit /b 1 )
echo Build complete: dist\AIWACK.exe
pause
