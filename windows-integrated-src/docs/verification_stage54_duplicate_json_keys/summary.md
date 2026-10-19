# Stage54 — 오프라인 조사 JSON 중복 키 거부 (부분 개발)

## 변경 범위
- 개발 기준: `AIWACK_Stage54_Offline_Windows_Bundle_Names_Continuation_Source.zip` (1,011개 파일).
- 사전 확인: `docs/original_project_spec.txt`, `docs/requirements_traceability.md`, `docs/roadmap_100.csv`, `docs/roadmap_100.md`, `docs/progress.json`.
- `desktop/research_captures.py`: 직접 입력 자료 묶음 JSON의 중첩 객체까지 중복 키 금지. 이미 존재하는 파일 내용, 로컬 등록 기록, URL 출처는 건드리지 않음.
- `desktop/research_bundle_manifest.py`: 동일한 엄격 JSON 처리로 로컬 지문 기록 재검사 시 중복 키 차단.
- 기존 v1 JSON 형식·Tkinter 화면·SQLite 구조, 관리자 승인 정책 유지. 자동 수집·네트워크 통신 없음.
- 새 테스트: `tests/test_offline_research_duplicate_json_keys.py` (중복된 루트/항목 키, 정상 호환성, 소켓 차단).
- 실제 Tkinter GUI 검사: `scripts/stage54_duplicate_json_keys_gui_smoke.py` (승인 창 표시 전 거부, 정상 기록, 조작 기록 거부, SQLite 불변).

## 주의 및 완료 조건
- JSON 중복 키의 의미가 모호하므로 마지막 값을 임의 채택하지 않고 거부합니다. 기본 JSON 파서와 동작이 다릅니다.
- 기존 올바른 JSON을 수정하지 않으며 자기 체크섬 SHA-256만으로 작성자·웹 출처를 인증하지 못합니다.
- 원본 100단계 로드맵 완료: **53/100 (53%)**, **54단계 진행 중**. 실질 제품 완성도 **약 20~25%, 주관적 추정**.
- 실제 인터넷 조사·자료 자동 수집, Windows 10/11 실기기, Windows EXE, 실제 GGUF 추론, 장시간 자율 운영 **미검증/미구현**.
- Python 네트워크 차단 검사는 OS 전역의 통신 차단 증명이 아닙니다.

## 실행 로그
- `targeted_pytest.log`, `full_pytest.log`, `gui_smoke.log`, `offline_runtime.log`, `compileall.log`, `reextract_checks.log`, `preservation.json`.
- 각 로그의 실제 종료 코드와 결과를 기준으로 해석하며, 종료되지 않은 실행은 완료로 기록하지 않습니다.

## 이번 실행에서 실제 확인된 결과
- 신규·기존 관련 pytest 3개 파일: **56개 통과, 실패 0개** (`targeted_pytest.log`). 신규 테스트 파일은 10개 매개변수 사례.
- 전체 회귀: 테스트 **89개 파일**, 파일이 중복되지 않는 **13개 그룹**, **총 1,342개 통과**, 실패 0개. 개별 `group_XX.log`, `test_groups_summary.json` 기록.
- 전체 pytest 단일 실행은 **약 16%에서 시간 제한으로 중단**; 단일 실행 성공으로 보고하지 않음 (`full_pytest.log`, `full_pytest.status.txt`).
- 네트워크 소켓·DNS 호출을 Python 수준에서 차단한 데스크톱·GUI 오프라인 실행: **59개 명령 모두 통과** (`offline_runtime.log`), 종료 코드 0.
- 실제 Tkinter GUI: Linux Xvfb에서 중복 키 자료 목록 거부(승인 창 미표시), 정상 지문 저장·재검사, 중복 키 지문 거부, SQLite 바이트 불변 확인 (`gui_smoke.log`).
- Python compileall 검사: 종료 코드 0 (`compileall.exit`).
- 기존 ZIP 1,011개 경로 모두 보존, 1,006개 바이트 동일, 기존 코드/문서 5개 수정. 원본 기획안, 요구사항 추적표, CSV·Markdown 로드맵 및 기존 SQLite 해시 동일 (`preservation.json`).
- 예비 ZIP을 별도 폴더에 압축 해제 후 관련 pytest **56개 통과**, Linux Xvfb Tkinter GUI 재검사 통과 (`reextract_checks.log`).
