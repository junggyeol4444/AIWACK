# AIWACK Stage54 부분 개발 — 로컬 조사 자료 중복·버전 차이 후보 점검

## 기준 및 보존

- 사용한 최신 누적본: `AIWACK_Stage54_Offline_Preflight_Export_Recheck_Continuation_Source.zip` (기존 529개 파일). 이전 `AIWACK_Stage54_Offline_Evidence_Continuation_Source.zip`보다 최신 버전.
- 개발 시작 전에 ZIP 안의 `docs/original_project_spec.txt`, `docs/requirements_traceability.md`, `docs/roadmap_100.csv`, `docs/roadmap_100.md`, `docs/progress.json`을 실제 열어 확인. 별도 독립 원본 기획안 첨부 텍스트는 로컬 파일에서 확인되지 않아 ZIP에 포함된 원본을 기준으로 함.
- 원본 요구사항의 실제 인터넷 조사·자동 자료 수집 기능은 **완료되지 않음**. GitHub, 웹사이트, 외부 서버, 클라우드 AI API를 호출하지 않음.
- 기존 529개 파일 전부 유지: 523개 원본 바이트 일치, 6개 수정(README, `desktop/app.py`, `desktop/storage.py`, `docs/progress.json`, `docs/roadmap_100.md`, `scripts/verify_offline_runtime.py`). `docs/original_project_spec.txt`, `docs/requirements_traceability.md`, `docs/roadmap_100.csv`, 기존 `dev_company.sqlite3`는 바이트 단위 보존. 자세한 비교: `source_preservation.txt`.

## 실제 구현

- 신규 `desktop/research_source_overlap.py`: 저장된 최신 자료 최대 2,000개를 **SQLite 조회만으로** 분석. 보관 자료 포함 여부 선택, 전체 그룹 수 및 상위 25개(관리자 API에서는 최대 50개) 표시, 스캔/표시 상한 초과 시 경고.
- 세 가지 로컬 조사 단서: **(1)** 본문 SHA-256이 같고 주장 URL이 다른 자료, **(2)** 주장 URL이 같고 본문 SHA-256이 다른 자료, **(3)** 등록 당시 원본 파일 바이트 SHA-256이 같고 주장 URL이 다른 자료. 동일 자료가 (1)과 (3)에 함께 잡힐 수 있으므로 그룹 수를 독립 자료 수로 해석하면 안 됨.
- 그룹별 건수, 서로 다른 URL/본문 해시 개수, 최대 5개 자료 ID, 최대 3개 URL 예시. 본문/원본 파일은 다시 열지 않으며 저장된 해시와 URL 문자열만 비교. URL 해석, DNS 조회, 웹 접속, 외부 호출, SQLite 쓰기 없음.
- 관리자 권한 확인 후 `desktop/storage.py`의 읽기 전용 API와 Tkinter `자료 중복·버전 차이 점검` 버튼을 연결. 기존 조사·내보내기·수동 검토 기능 및 SQLite 스키마/데이터 변경 없음.
- **동일 해시는 독립 출처·웹 출처 진위·본문 사실성·현재 파일 바이트 보존을 증명하지 않음.** 과거 자료가 2,000개 범위 밖에 있으면 분석에서 제외됨.

## 검증 기록

- 신규 `tests/test_offline_research_source_overlap.py`: **20개 통과**. 빈 DB, 두 종류 본문 겹침, 동일 파일 바이트, 수동 입력 제외, 보관 범위, 상한, ID/URL 미리보기 제한, 옵션 오류, 관리자 인증, 재로그인, 네트워크 소켓 차단, SQLite 읽기 전용 확인.
- 전체 수집 **1,034개**. 중복 없는 **5개 분할 그룹**에서 모두 통과: `research_pytest.log` **349개**, `group_1_pytest.log` **117개**, `group_2_pytest.log` **186개**, `group_3_pytest.log` **193개**, `group_4_pytest.log` **189개**. 파일 목록은 `group_*_files.txt`. 신규 20개는 연구 그룹 349개에 포함되어 중복 계산하지 않음.
- **단일 전체 pytest 실행은 완료되지 않음**: `full_pytest.log`의 약 20% 시점에서 도구 시간 제한으로 중단. 따라서 단일 전체 실행 성공이라고 보고하지 않음.
- Python 소켓/DNS 함수 차단 환경에서 오프라인 self-test 및 Linux Xvfb Tkinter **총 38개 서로 다른 명령 통과**. 일괄 `scripts.verify_offline_runtime` 실행은 **17개 명령 통과 후 실행 제한으로 중단** (`offline_runtime.log`), 나머지 21개는 동일한 Python 소켓 차단 정책을 적용하여 8+7+6개로 나눠 독립 실행 (`offline_remaining_*.log`). 전체 일괄 실행 완료라고 주장하지 않음.
- 신규 실제 Tkinter 버튼 조작 및 로그아웃/재로그인 복원은 `scripts/stage54_source_overlap_gui_smoke.py`에서 확인. Python `compileall` 통과. ZIP 무결성 및 SHA-256은 최종 패키징 결과 참조.

## 진행률과 한계

- 로드맵 **53/100단계 완료 = 53%**, **54단계 인터넷 조사 및 자료 수집 진행 중**. 55단계 미착수.
- 실질 제품 완성도 **약 20~25%**, 주관적 추정이며 통합된 자율 회사 운영·실제 수익·모델 능력에 대한 검증 수치가 아님.
- Windows 10/11 실기기, Windows EXE 빌드, 실제 GGUF 모델 추론, 장시간 자율 운영, OS 방화벽 수준의 네트워크 차단, 실제 인터넷 조사/자동 수집은 검증 또는 구현하지 않음. 기존 병렬 작업의 간헐적인 1.5초 타임아웃 원인도 해결한 것은 아님.
