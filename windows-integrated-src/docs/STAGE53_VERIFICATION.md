# AIWACK 53단계 — 문서·파일 생성·수정 기능

## 요구사항과 실제 구현

- 입력: 최신 `AIWACK_Stage52_Local_Offline_Source.zip`; 원본 `docs/progress.json`은 1~52단계 완료, 다음 53단계.
- 구현: `desktop/managed_documents.py`, `desktop/storage.py`의 관리자 인증 연계, `desktop/app.py`의 `로컬 문서·파일 작업` 탭.
- 실제 결과물: SQLite 데이터 경로 옆 **`managed_documents/`** 전용 폴더의 UTF-8 `.txt/.md/.csv/.json` 파일. 임의 절대 경로·상대 경로·외부 서비스에 쓸 수 없다. 문서당 최대 128KiB.
- 저장/수정 시 버전 및 SHA-256 검사; 문서 원문과 이전 버전 내용은 SQLite `managed_document_revisions`에 보존. SQLite 트리거로 이력 UPDATE/DELETE 차단.
- 기존 무관한 파일 덮어쓰기, 탐색 경로(`../` 등), 작업 공간 심볼릭 링크, 파일 심볼릭/하드 링크, 기존 기록과 다른 내용, 오래된 버전의 수정은 모두 거부.
- **직접 관리자 조작만 지원**. 직원 AI 실행기, 52단계 도구 사용 승인 원장과의 자동 연결, 작업 자동 생성, 외부 문서 편집은 구현하지 않는다.

## 안전성 및 현재 한계

- 파일 교체는 동일 폴더에 임시 파일 생성 후 `os.replace()`로 원자적 파일 내용 교체. SQLite와 파일 시스템을 포괄하는 단일 원자적 트랜잭션은 불가능하며 **파일 교체 후 DB 커밋 전 예기치 않은 프로세스 종료 시 불일치**가 발생할 수 있다. 불일치를 감지해 자동 덮어쓰지 않고 관리자 확인을 요구한다.
- 파일 소유자가 악의적으로 작업 공간을 동시 변경하는 경우의 TOCTOU 경합까지 OS 수준으로 완전히 막지는 못한다. SQLite/파일 보호는 로컬 프로세스 관리 기능이지 디스크 암호화·OS 권한 분리 또는 악성 사용자 차단이 아니다.
- `.json` 확장자라고 해서 JSON 문법을 검증하지 않는다. `.csv`도 행 구조 유효성 검사가 아니라 일반 UTF-8 텍스트 파일이다.
- 최초 앱 실행 시 기록된 기존 데이터/기획서는 수정하지 않으며 기존 데이터베이스는 자동 초기화하지 않는다.
- Linux Xvfb GUI 통과, Windows 10/11 실기기·PyInstaller 설치판·실제 로컬 GGUF 추론 미검증.

## 검사 로그

- `tests/test_managed_documents.py`: **26 passed** (생성·수정·이력·재시작·동시 변경·충돌·미관리 파일·링크·크기·인증·SQLite 이력·소켓/프로세스 차단).
- **전체 pytest: 685 passed in 84.01s** (`docs/STAGE53_FULL_PYTEST.log`). 첫 -q 실행은 종료되지 않았으나 상세 -vv 재실행 결과 확인.
- `scripts/stage53_offline_gui_smoke.py`: 실제 Tkinter 관리자 버튼 클릭, 생성·중복 차단·업데이트·충돌 거부·재로그인·실제 파일 확인 (`docs/STAGE53_OFFLINE_SMOKE.log`). Python 소켓 호출 차단.
- `scripts/verify_offline_runtime.py`: 이전 단계의 기존 검사 유지하고 Stage53 검사 추가. **21개 명령 모두 통과** (소켓 연결을 차단한 Python 프로세스, 실제 OS 전체 방화벽은 아님).
- 진행 기록 갱신 후 관련 pytest 재검사: **47 passed** (`docs/STAGE53_RECHECK_PYTEST.log`).
- 52단계 ZIP의 **227개 파일 전부 보존**; 기존 `dev_company.sqlite3`와 `docs/original_project_spec.txt`는 바이트 단위 동일.
- Windows 실기기 및 실제 GGUF 추론은 미검증.

## 완료 보고 (조건부)

- 100단계 로드맵: **53/100 (53%)**, 이번 단계의 *관리자 수동 파일 작성 및 수정* 범위 검증.
- 실질 제품 완성도: **약 20~25%** (주관적 추정; 자율 사업 운영·외부 결제·24시간 운용은 대부분 미구현).
- 다음 54단계: **인터넷 조사 및 자료 수집** (현재 단계에서는 외부 서버 호출 금지 원칙 준수).
