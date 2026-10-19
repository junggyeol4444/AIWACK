# AIWACK Stage54 오프라인 근거 JSON 재검사 — 후속 개발

## 기획·로드맵 기준

- 실제 확인: `docs/original_project_spec.txt` 원본 제6장·제13장, `docs/requirements_traceability.md` R06/T06, `docs/roadmap_100.csv`, `docs/roadmap_100.md`, `docs/progress.json`.
- 이전 누적 입력: `AIWACK_Stage54_Offline_Evidence_Export_Continuation_Source.zip` (318개 파일).
- 1~53단계 완료 기록 보존. **54단계 인터넷 조사 및 자료 수집은 진행 중**. 55단계 미진입.

## 이번 하위 기능

- `desktop/research_verification.py`: 관리자가 직접 고른 기존 JSON 파일만 검사. `lstat`으로 심볼릭 링크·디렉터리 거부, 1MB 제한, 기존 체크섬 검증 후 현재 로그인한 로컬 SQLite DB의 동일 검색어 근거 보고서를 두 보관 범위로 다시 생성하여 전체 보고서 동등성 비교.
- `desktop/storage.py`: 관리자 `company:manage` 권한 확인 후 읽기 전용 조회 API.
- `desktop/app.py`: `근거 JSON 재검사` 버튼. 취소 시 무변경. 파일 본문을 그대로 화면에 실행·렌더링하지 않고 검사 결과만 표시.
- 불일치는 자료 추가·보관·DB 변경·다른 DB 등의 원인일 수 있으며 어떤 원인인지 단정하지 않음. 이전 체크섬이 맞아도 로컬 DB 내용이 바뀌면 불일치로 표시.
- **두 검사 모두 웹 출처 진위, 작성자 신원, 자료의 사실성, 외부 웹 원문과의 일치를 보증하지 않음.** 체크섬은 전자서명이 아님. JSON 내보내기는 암호화되지 않음.

## 한계

- 파일 선택은 명시적 사용자 행위가 필요함. 네트워크 호출, 자료 DB 쓰기, 원격 조회·수집 없음.
- 동일 검색어 보고서를 재생성하므로 새 자료 등록·보관 상태 변경 시 과거 내보내기와 불일치할 수 있음. 이는 정확한 변경 원인을 확정하는 검사가 아님.
- 파일 경로의 `lstat`과 `open` 사이 파일 교체 경쟁 조건까지 OS 수준으로 봉쇄하지는 않음.
- Windows 10/11 실기기 GUI/설치 및 실제 GGUF 모델 추론 미검증.
- 전체 원본 54단계(실제 인터넷 조사·자동 수집·온라인 출처 검증) 미완료.

## 검증 로그

검증 후 `docs/verification_stage54_recheck/`에 테스트, 실제 GUI, 오프라인 실행 결과를 보관.

## 이번 실행에서 실제 확인한 결과 (2026-10-13)

- 전체 테스트 파일 57개를 중복 없이 분할 실행: **818 passed** (128+128+6+194+109+105+148). 개별 로그는 `docs/verification_stage54_recheck/group_*.log`, 집계는 `summary.txt`. 그룹 2의 단일 묶음은 실행 시간 제한으로 완료되지 않아 `test_employee_models.py`를 따로 실행함. 모든 57개 파일은 성공한 분할 실행에 포함됨. **전체 pytest 단일 연속 실행 통과는 주장하지 않음.**
- 신규 `tests/test_offline_research_verification.py` **11 passed**, 관련 3개 테스트 파일 묶음 **33 passed**.
- `xvfb-run -a python scripts/stage54_verification_gui_smoke.py`: 실제 Tkinter 버튼, 파일 선택 취소, 로컬 DB 일치/불일치, 재로그인 후 복원, Python 소켓 연결 차단 **PASS**.
- Python outbound socket 차단 `sitecustomize.py` 하에서 데스크톱 진입 self-test + 기존 4개 Stage54 GUI + 신규 GUI = **6개 명령 PASS** (`offline_subset.log`).
- 전체 오프라인 실행 일괄 검사는 시간 제한으로 중단되어 **전체 PASS 아님**. 해당 시도 기록 `offline_full.log`.
- Python `compileall` PASS. 이전 ZIP의 318개 파일 모두 보존, 기존 변경 파일은 `desktop/app.py`, `desktop/storage.py`, `docs/progress.json`, `docs/roadmap_100.md`, `scripts/verify_offline_runtime.py` 5개. 원본 기획서 및 기존 SQLite 파일 바이트 보존.
- Windows 실기기 테스트 및 실제 GGUF 모델 추론 **미실행**. Python 소켓 차단은 OS 전체 방화벽 차단을 증명하지 않음.
- 로드맵 **53/100 완료, 54단계 진행 중**. 실질 제품 완성도 **약 20~25% (주관적 추정, 측정치 아님)**.
