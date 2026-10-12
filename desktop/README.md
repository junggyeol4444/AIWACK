# Native Windows desktop app

Entry point: `python -m desktop.entry`. Bundled exe entry: `desktop/entry.py`.

No HTTP server is started. User data path: `%LOCALAPPDATA%/AIWACK/aiwack.sqlite3` on Windows. The executable does not modify or delete earlier `dev_company.sqlite3` development data; migration of existing development data is not implemented.

Windows artifact is produced by GitHub Actions `windows-exe.yml` with PyInstaller on a Windows runner. A Linux/Mac Python process is **not** a native Windows executable; the artifact must pass Windows build and self-test before being called verified.

Current initial functionality: 3 tabs (status/notes/100-step roadmap), SQLite persistence, restart test. All AI-company business behavior remains future work.

Stage 9: single local owner login, salted PBKDF2 password hashes, 5 failed login attempts/60 sec lockout, logged-in permission guard for note read/write and owner-only role scope. First run creates owner; existing notes remain. No password reset, multiuser, full-disk encryption, or external auth.

Stage 10 adds the authenticated **관리자 센터** view. Its 7 navigation sections are scaffolding; only DB health and logged-in owner role are live, and future AI/business/finance actions are visibly marked unimplemented.

## Stage 11

Authenticated local company profile and goal CRUD is available under the fifth notebook tab, `회사·목표 관리`. No live business activity takes place.
