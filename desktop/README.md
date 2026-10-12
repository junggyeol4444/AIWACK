# Native Windows desktop app

Entry point: `python -m desktop.entry`. Bundled exe entry: `desktop/entry.py`.

No HTTP server is started. User data path: `%LOCALAPPDATA%/AIWACK/aiwack.sqlite3` on Windows. The executable does not modify or delete earlier `dev_company.sqlite3` development data; migration of existing development data is not implemented.

Windows artifact is produced by GitHub Actions `windows-exe.yml` with PyInstaller on a Windows runner. A Linux/Mac Python process is **not** a native Windows executable; the artifact must pass Windows build and self-test before being called verified.

Current initial functionality: 3 tabs (status/notes/100-step roadmap), SQLite persistence, restart test. All AI-company business behavior remains future work.
