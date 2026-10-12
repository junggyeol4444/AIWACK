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

## 14단계 · AI 직원 정보 저장 구조

`ai_employee_profiles`는 미래 AI 직원의 **실행되지 않는 초안 메타데이터**만 저장합니다. 부서·직급·직무·역할 ID를 참조하고 데이터 무결성·권한 검사를 적용합니다. 사용자용 생성/편집/비활성화 화면과 실제 AI 모델 실행은 아직 없습니다(15단계 이후).

## 15단계 — AI 직원 관리 화면

관리자 로그인 후 `AI 직원 관리` 탭에서 직원 초안 생성, 이름·설명·부서·직급·직무·역할 수정, 비활성화 및 초안 복귀가 가능합니다. 직원 식별자는 생성 후 변경할 수 없으며 SQLite에 보관됩니다. **초안/비활성화는 AI를 실행하지 않습니다.** 현재 모델·도구·총괄 AI 명령은 미구현입니다.
