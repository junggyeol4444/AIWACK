# Desktop software verification record

This is not a website. It is a standalone Tkinter GUI with local SQLite storage.

Checks required before reporting runnable build:

1. Linux/Xvfb actual window is created, clicked and closed. UI is re-created and note persists: `xvfb-run -a python scripts/desktop_gui_smoke.py`.
2. `python -m desktop.entry --self-test` actual file write/re-open passes.
3. Windows GitHub Actions packages PyInstaller `dist/AIWACK.exe`, invokes `dist/AIWACK.exe --self-test` on a Windows runner, uploads artifact.
4. End user must still test opening the Windows app, clicking and restarting on their own computer. CI runner's non-interactive desktop cannot confirm real-world rendering, display drivers, antivirus warnings or usability.

No one should mark the overall AI autonomous company as functional based on this test.
