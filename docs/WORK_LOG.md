# 개발 작업 기록 / 계속하기 체크포인트

프로젝트: AI Autonomous Company  
기준 문서: `docs/original_project_spec.txt`  
이번 작업 환경: ChatGPT 파일 생성 환경 (사용자의 개인 PC 아님)

## 완료 및 검증한 단계

- [x] 001. 원본 기획서의 기능·완료 조건 정리 → `docs/requirements_traceability.md`; T01~T20 추적 항목 정리.
- [x] 002. 전체 시스템 구성과 개발 순서 확정 → `docs/architecture_v0.md`, `docs/roadmap_100.md`.
- [x] 003. 프로젝트 폴더 구조 생성 → 원문 9.5절 기준 디렉터리.
- [x] 004. 개발 환경 및 설정 파일 구성 → `pyproject.toml`, `.env.example`, `backend/core/config.py`.
- [x] 005. Python 중앙 서버 기본 구현 → `backend/main.py`, GET /.
- [x] 006. 서버 실행 및 상태 확인 기능 → GET /health, GET /api/v1/health, 테스트.

## 다음 단계

- [ ] 007. 데이터베이스 연결 및 초기화. 첫 연결과 초기화 이후에 정상·오류 동작 검증.
- [ ] 008. 데이터베이스 변경 이력 관리.

## 현재 사용자 승인이 필요한 항목

사용자 PC에 필요한 프로그램·설치·비용·계정은 사용자가 PC를 켜고 요청할 때 한 번에 안내한다. 이 환경에서 PC 설치는 수행하지 않는다.

## 실행 제약

매시간 예약은 개인 PC의 켜짐/꺼짐을 확인하지 못한다. 사용자 PC에 접근하거나 자동 설치하지 않는다. 예약별 작업 환경이 다를 수 있으므로 `docs/WORK_LOG.md`와 결과 ZIP 같은 체크포인트를 보존하고, 접근 가능한 코드가 확인된 경우에만 이어 개발한다. 접근 불가한 코드를 구현했다고 주장하지 않는다.

## 테스트 기록

- `python -m pytest -q`: **9 passed**.
- 독립 프로세스 `uvicorn backend.main:app` 실행 후, `GET /api/v1/health`가 HTTP 200 및 `status=ok`를 반환하는 것을 확인.
- 사용자의 실제 PC 또는 외부 서버에서 검증한 결과는 아님.


## GitHub 통합 이후 — 2026-10-12: 8단계 구현 및 로컬 실구동 검사

- Alembic migration `0001_initial`: 최초 로컬 DB 생성, `alembic_version` 관리, 이전 7단계 DB의 데이터 보존 도입.
- `scripts/launch_local.py`, `start_windows.bat`, `start_mac_linux.sh`: 사용자 로컬 실행기.
- `/diagnostics` 화면과 DB 영구 저장을 확인하는 실제 HTTP 진단.
- `scripts/real_smoke_test.py`: Uvicorn 서버 프로세스 두 번 기동, API/HTML, 데이터 저장·재시작·재조회 검증.
- **코드/구조 pytest 17개 통과** (로컬) 및 **실제 HTTP/DB 재시작 스모크 테스트 통과**.
- 회사의 AI 에이전트 및 자율 수익 기능은 아직 미구현.
- 이후 개발: 9단계 회사 소유자 및 기본 권한 기능.

- Chromium 실제 브라우저 클릭 검증은 샌드박스 관리자 네트워크 정책(127.0.0.1 차단)으로 실행 불가. 브라우저 구문 검사 통과. 사용자 PC 실사 확인 요청.


## 데스크톱 프로그램 전환 (100단계 진행 수는 유지)

- 사용자 요청에 따라 Windows EXE가 주요 배포 형태이며 웹 UI는 배포판에서 사용하지 않음.
- `desktop/entry.py`, `desktop/app.py`, `desktop/storage.py`로 Tkinter 데스크톱 창, 로컬 SQLite, 데이터 재실행 후 보존 기능 구현.
- `scripts/desktop_gui_smoke.py`에서 실제 네이티브 창의 버튼을 호출하고 다시 열어 데이터 유지 검증.
- GitHub Actions `windows-exe.yml`로 Windows 빌드와 실행파일 자체 저장 검사 및 다운로드 가능한 Artifact 준비.
- 전체 AI 회사의 자율 동작은 미구현; 관리자 화면 로드맵의 완성으로 간주하지 않음. 진행률 8/100 유지.

## 2026-10-12 9단계 — 소유자 계정·기본 권한

- 새 owner_accounts SQLite 테이블과 PBKDF2-SHA256 salted password hash(310,000 반복). 비밀번호 원문·API 키 저장하지 않음.
- 첫 실행 계정 생성, 최초 관리자 단일 등록, 로그인, 로그아웃, 세션별 로컬 메모 접근 권한 검사, 5회 실패 시 60초 차단.
- 기존 EXE 메모 데이터는 보존; 디스크 파일 자체 암호화/비밀번호 복구는 미지원(별도 보안 고도화 단계 필요).
- 실제 GUI 시작/계정 생성/로그인 실패/정상 로그인/저장/종료/재실행을 scripts/desktop_gui_smoke.py로 점검.
- Windows PyInstaller EXE 빌드/실행은 GitHub Actions 성공 여부 별도 확인 후 보고.

다음 단계: 10단계 관리자 화면 기본 틀.
