# AIWACK 54단계 — 오프라인 근거 JSON 차이 후보 분석 (후속 개발)

## 원본 요구사항과 작업 범위

- 실제 확인한 누적 원본: `AIWACK_Stage54_Offline_Evidence_Recheck_Continuation_Source.zip` (332개 파일).
- 확인 문서: `docs/original_project_spec.txt` (시장조사·정보 출처·제6장 웹 도구·단계별 완료 조건), `docs/requirements_traceability.md` (R06/T06), `docs/roadmap_100.csv`, `docs/roadmap_100.md`, `docs/progress.json`.
- 로드맵: **1~53단계 완료, 54단계 진행 중, 55단계 미진입**. 인터넷 조사·실제 자동 웹 수집은 구현하거나 검증하지 않음.

## 구현 사항

1. `desktop/research_verification.py`: 사용자가 명시적으로 선택한 로컬 JSON의 자체 체크섬 검사 후, 현재 SQLite의 활성 자료/보관 포함 보고서와 비교. 정확히 일치하지 않으면 두 후보 중 유사한 로컬 보고서와 비교해 **현재 DB에만 있는 자료 ID, 내보낸 JSON에만 있는 자료 ID, 동일 ID이지만 값이 다른 자료, 일치 항목 수**를 최대 20개 범위에서 표시. 범위 선택은 후보이며 내보내기 당시 범위나 불일치 원인을 증명하지 않음. 중복/잘못된 자료 ID 거부.
2. 기존 `lstat` 후 `open` 간 파일 교체 위험을 줄이기 위해 절대 경로·UNC 경로·Windows 네트워크 드라이브 제한, POSIX `O_NOFOLLOW`, 열린 파일 `fstat` 정규 파일/장치·inode 검사, 읽기 전후 크기·mtime 검사 및 재 `lstat` 검사. 기존 1MB 제한 유지. **Windows에서는 POSIX `O_NOFOLLOW`에 상응하는 완전한 경쟁 조건 방어를 주장하지 않음**. 부모 디렉터리 링크, 모든 마운트/공유 방식까지 차단했다고 주장하지 않음.
3. `desktop/app.py`: 기존 `근거 JSON 재검사` 버튼의 상세창에 관찰된 차이 ID를 표시하고, 원인 진단·웹 출처 진위 확인이 아님을 명시. 데이터베이스 쓰기 없음.
4. `tests/test_offline_research_drift.py`: 새 단위·보안·오프라인 테스트 12개. `scripts/stage54_drift_gui_smoke.py`: 실제 Tkinter 버튼으로 차이 ID 표시·재로그인·Python 소켓 차단 검사. `scripts/verify_offline_runtime.py`에 새 GUI 스모크 등록.

## 검증 결과 (2026-10-13)

- 전체 테스트 파일 **58개**, 중복 없는 7개 묶음 실행: **830 passed** (93 + 165 + 200 + 156 + 87 + 123 + 6). `docs/verification_stage54_drift/group_1.log`~`group_7_models.log` 참고. 단일 전체 pytest 실행 통과를 주장하지 않음.
- 신규 테스트 파일: **12 passed**. 관련 기존 검사 `test_offline_research_verification.py` **11 passed**.
- Linux Xvfb 실제 Tkinter 신규 GUI 검사: **PASS**, 기존 재검사 GUI 스모크: **PASS**.
- Python socket 연결 차단 `sitecustomize.py` 적용 후 데스크톱 self-test 및 기존/신규 54단계 GUI 스모크 **8개 명령 PASS** (`offline_subset.log`). OS 수준 네트워크 차단이나 모든 실행 경로의 오프라인 동작 증명이 아님.
- Python `compileall` 통과. 원본 누적 ZIP의 332개 파일이 모두 새 ZIP에 존재하는지 및 원본 기획안·기존 SQLite 파일의 바이트 일치 여부를 최종 ZIP 검사에서 확인.
- Windows 10/11 실기기, 실제 GGUF 추론, 인터넷 검색/원격 자료 수집, 전체 오프라인 실행 일괄 검사 **미검증**.

## 진위와 무결성의 경계

- JSON SHA-256은 **서명/작성자 인증이 아님**. 공격자가 JSON과 체크섬을 함께 변경할 수 있음.
- DB 비교는 **현재 로컬 기록 간 차이 후보**이며 실제 웹 출처의 존재·정확성·진위 또는 변경의 원인을 확정하지 않음.
- 원본 54단계는 **미완료**. 완료 53/100 (53%), 실질 제품 완성도 약 20~25% (주관적 추정).
