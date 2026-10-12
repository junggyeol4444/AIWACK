# Native Windows desktop app

Entry point: `python -m desktop.entry`. Bundled exe entry: `desktop/entry.py`.

No HTTP server is started. User data path: `%LOCALAPPDATA%/AIWACK/aiwack.sqlite3` on Windows. The executable does not modify or delete earlier `dev_company.sqlite3` development data; migration of existing development data is not implemented.

Windows artifact is produced by GitHub Actions `windows-exe.yml` with PyInstaller on a Windows runner. A Linux/Mac Python process is **not** a native Windows executable; the artifact must pass Windows build and self-test before being called verified.

Current initial functionality: owner login, local CRUD for company profile, goals, departments and organization designations; SQLite persistence and restart test. All AI-company business behavior remains future work.

Stage 9: single local owner login, salted PBKDF2 password hashes, 5 failed login attempts/60 sec lockout, logged-in permission guard for note read/write and owner-only role scope. First run creates owner; existing notes remain. No password reset, multiuser, full-disk encryption, or external auth.

Stage 10 adds the authenticated **관리자 센터** view. Its 7 navigation sections are scaffolding; only DB health and logged-in owner role are live, and future AI/business/finance actions are visibly marked unimplemented.

## Stage 11

Authenticated local company profile and goal CRUD is available under the fifth notebook tab, `회사·목표 관리`. No live business activity takes place.

Stage 12: standalone `부서 관리` desktop tab for owner-only SQLite department CRUD. No department AI execution yet.

## 13단계 · 직급·직무·역할 카탈로그

Windows EXE의 `직급·직무·역할` 탭에서 rank(직급), job(직무), role(업무상 책임) 명칭·설명을 추가·수정·삭제할 수 있습니다. 관리자 로그인 필수, 같은 유형 내 중복 금지, 다른 유형에서 같은 이름 사용 가능, SQLite 재실행 후 보존. 이 role은 **인증 권한**이 아니며, 아직 직원 AI를 생성하거나 권한을 부여하지 않습니다.
