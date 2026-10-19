# AIWACK 43단계 — 프로젝트별 협업 대화방 검증

## 개발 기준

- 입력: `AIWACK_Stage42_Local_Offline_Source.zip` 및 그 내부 `docs/progress.json` (`completed_steps`: 1–42, `next_step`: 43).
- 원본 기획안의 3.3 프로젝트별 대화방·AI 간 협업, 9장 운영 시스템, 관리자 통제 원칙과 100단계 로드맵 43번을 기준으로 구현.
- 기존 소스의 `docs/original_project_spec.txt`, `dev_company.sqlite3`의 SHA-256/바이트가 원본 Stage42 ZIP과 일치함을 확인. 기존 테이블/데이터 초기화 없음.

## 구현

1. `desktop/project_chat.py`: `local_project_rooms`(로컬 대화방), `local_project_participants`(다부서 참여자), `local_project_messages`(개별 대화방의 독립 메시지)를 SQLite 비파괴 테이블로 추가.
2. 활성 직원만 프로젝트에 참여 가능. 현재 활성 참여자만 새 메시지 작성 가능. SQL INSERT 트리거에서도 검증. 참여자 ID UPDATE 차단 및 메시지 UPDATE/DELETE 차단. 참여자를 제외해도 과거 기록 보존.
3. 프로젝트·직원 유효성, 정수 ID, 메시지 1~4000자, 프로젝트 제목 1~120자, 조회 1~500건 제한. 로그아웃 시 owner `agents:manage` 권한을 검사하여 읽기/쓰기 차단.
4. `desktop/storage.py`: 기존 단일 사용자 LocalStore에 권한 확인 전용 로컬 API 추가. SQLite 영구 저장/재시작 복원.
5. `desktop/app.py`: `프로젝트 협업 대화` 네이티브 탭 및 대화방 생성, 직원 참여/제외, 조회/발신 버튼. 대화방 ID가 잘못되거나 바뀌면 이전 대화 내용을 즉시 지움.
6. `tests/test_project_chat.py`, `scripts/stage43_gui_smoke.py` 추가. 네트워크 차단 오프라인 스모크에도 43단계 GUI 검사 추가.
7. 기존 부서별 대화 및 개인 메시지 기능, 기존 소스 구조와 함께 유지.

## 검증 수행

- 신규/인접 회귀: `python -m pytest -q tests/test_project_chat.py tests/test_department_chat.py tests/test_direct_messages.py` → **36 passed**.
- 추가 변경 후 신규/진행 기록/인접 회귀: `python -m pytest -q tests/test_project_chat.py tests/test_project_structure.py tests/test_department_chat.py tests/test_direct_messages.py` → **41 passed**.
- Tkinter 실제 GUI 버튼 검사: `PYTHONPATH=. xvfb-run -a python -m scripts.stage43_gui_smoke` → **PASS** (Linux Xvfb: 대화방·참여·메시지·격리·로그아웃 확인).
- 소켓 연결 차단 오프라인 실행: `python -m scripts.verify_offline_runtime` → **12개 PASS** (`docs/STAGE43_OFFLINE_RUNTIME.log` 참조). 소켓 차단은 Python 검증 프로세스에 한하며 운영체제 방화벽 검증은 아님.
- Python 컴파일: `python -m compileall -q desktop scripts tests` → **PASS**.
- 전체 pytest: `docs/STAGE43_FULL_PYTEST.log` 참고.

## 한계

- 현재 프로젝트는 **협업 기록용 로컬 대화방**. 사업 프로젝트의 실제 작업·예산·기획·수익과 연동하지 않음.
- 메시지는 사용자가 직원 ID로 기록하는 것이며 **AI 직원의 자율 소통 및 자동 회의**는 미구현.
- Windows 10/11 실기기·설치 EXE·실제 GGUF 추론·장시간 무인 실행은 미검증.
- GitHub·외부 서버·클라우드 AI API 호출 없음.

## 진행 상태

- 100단계 로드맵: **43/100 = 43%** (문서 단계이며 실제 완성도 지표 아님).
- 실질 제품 완성도: **약 15~17%** (제품의 전체 목표 대비 주관적 범위 추정; 자동 사업 운영·실제 판매·자율 AI 협업 미완성).
- 다음: **44단계 — AI 회의 안건 및 참석자 관리**.
