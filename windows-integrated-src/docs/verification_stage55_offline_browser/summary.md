# AIWACK 공식 55단계 검증 — 허용된 브라우저 작업 실행

개발 기준: `AIWACK_Stage54_Offline_Strict_JSON_Keys_Continuation_Source.zip` (1056개 누적 파일).
원문 `docs/original_project_spec.txt`, `docs/requirements_traceability.md`, `docs/roadmap_100.csv`, `docs/roadmap_100.md`, `docs/progress.json` 실제 확인.

## 중요한 단계 전환

- **54단계** '인터넷 조사 및 자료 수집'은 외부 접속 금지로 **BLOCKED / 미완료**. 임의로 완료하지 않음.
- **55단계** '허용된 브라우저 작업 실행'은 정책상 허용되는 범위인 **관리자 수동 선택 로컬 HTML의 헤드리스 Chromium 읽기·문자열 검색 작업**을 실제 구현. 허용된 로컬 브라우저 작업 범위에서 DONE.
- 다음 개발 단계는 **56단계** 'AI 코드 작성·수정 기능'. 원래 단계명과 순서는 보존.
- 완료 수 54/100 = 1~53 + 55. 54단계 미완료를 숨기지 않으며 비연속 완료를 `scripts/next_step.py`와 `tests/test_project_structure.py`가 검증.

## 실제 변경 내용

- `desktop/offline_browser.py`: 로컬 정규 HTML 파일 1MiB 이하 읽기, symlink/UNC 경로 거부, 원본 HTML에서 scripts/styles/iframe 등을 제외해 평문 추출. 브라우저엔 HTML 이스케이프한 평문만 전달. Chromium/Chrome/Edge를 설치되어 있을 때만 Playwright로 호출, JS 비활성, 컨텍스트 offline, 서비스 워커 차단 및 모든 네트워크 요청 거부, 브라우저에서 렌더링한 텍스트·검색 횟수 반환.
- `desktop/app.py`: 로그인한 관리자가 직접 파일을 선택·버튼을 눌러 실행하는 Tkinter 탭 추가. 로그아웃 후 실행 거부. 외부 서버에 접속하거나 파일을 다운로드하지 않음.
- `tests/test_stage55_offline_browser.py`, `scripts/stage55_offline_browser_gui_smoke.py`: 파일 경로·크기·심볼릭 링크·검색어·HTML 스크립트 제외·실제 Chromium·로그아웃 접근 제한 테스트.
- `docs/progress.json`, CSV/MD 로드맵, `scripts/next_step.py`, 진행률 표시, 단계 검증 테스트: **보류 단계와 완료 단계를 별도로 추적**.

## 실제 검증

- `PYTHONPATH=. python -m pytest -q tests/test_stage55_offline_browser.py tests/test_project_structure.py tests/test_tool_registry.py tests/test_tool_approvals.py tests/test_managed_documents.py` → **83 passed**, `pytest_targeted.log`.
- `PYTHONPATH=. python -m pytest -q tests/test_task_parallel.py tests/test_local_models.py tests/test_offline_research.py tests/test_offline_research_imports.py` → **64 passed**, `pytest_regression.log`.
- `xvfb-run -a python -m scripts.stage55_offline_browser_gui_smoke` → 실제 Tkinter 로그인·로컬 Chromium 검색·로그아웃 거부 **통과**.
- `python -m desktop.entry --self-test` → **통과** (기존 로컬 SQLite 기반 데스크톱 자체 검사).
- `python scripts/next_step.py` → `Completed: 54/100; Blocked: [54]`, `Next: 56/100`.
- 전체 단일 pytest는 약 **15%**에서 도구 시간 제한으로 중단. **전체 통과 주장 불가.** 분할 회귀는 처음 두 그룹(10개 파일씩) **93 + 143 통과**, 이후 실행 제한으로 중단. 다른 그룹은 검증 완료로 계산하지 않음.
- 전체 오프라인 실행 점검 `python -m scripts.verify_offline_runtime` 또한 시간 제한으로 중단. 완료 주장 불가.

## 보안·한계

- Chromium은 현재 개발 환경(`/usr/bin/chromium`)에서 실제 실행했지만 Windows 10/11 실기기에서 테스트하지 않음. Windows에서 브라우저와 Playwright가 사전 설치되지 않았다면 기능은 **명시적으로 실패**. 앱이 자동 설치하지 않음.
- 차단은 Playwright 컨텍스트·요청 라우팅 수준. 브라우저 바이너리의 OS 차원 백그라운드 통신까지 차단하는 **방화벽/커널 격리가 아님**. 신뢰 가능한 로컬 브라우저가 필요.
- 원본 HTML/JavaScript/CSS/iframe/링크는 실행되지 않으며 사용자가 입력한 URL을 접속하지 않음. 실제 원격 브라우저 자동화·폼 제출·다운로드·인터넷 조사 기능은 지원하지 않음.
- 브라우저 작업은 **사용자가 직접 버튼을 눌러 실행**. AI가 자동으로 브라우저를 제어하는 자율 시스템으로 과장하지 않음.
- 원본 기획안 및 요구사항 문서와 기존 `dev_company.sqlite3` 파일 내용은 바이트 단위로 보존됨. `docs/progress.json` 및 CSV/MD 로드맵의 **진행 상태 메타데이터만 갱신**.
- Windows EXE 빌드·GGUF 모델 추론·장시간 자율 운영·원격 기능은 미검증.
