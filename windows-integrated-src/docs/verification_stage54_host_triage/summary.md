# AIWACK 54단계 부분 개발: 오프라인 링크 호스트별 조사 현황

## 개발 기준 및 원본 보존

- **기준 ZIP:** `AIWACK_Stage54_Offline_Followup_Recheck_Continuation_Source.zip` (이 대화에서 접근 가능한 가장 최신 누적본, 기존 파일 470개). 사용자가 문장에 지정한 `AIWACK_Stage54_Offline_Evidence_Continuation_Source.zip`보다 뒤의 누적본을 우선했습니다.
- 개발 전에 ZIP 내부 `docs/original_project_spec.txt`, `docs/requirements_traceability.md`, `docs/roadmap_100.csv`, `docs/roadmap_100.md`, `docs/progress.json`을 직접 열어 요구사항과 54단계 완료 조건을 확인했습니다. **별도의 원본 기획안 첨부 텍스트 파일은 이 실행의 로컬 파일 목록에서 확인되지 않아 ZIP 내 보존 원본을 기준으로 했습니다.**
- 원본 기획안의 실제 인터넷 조사·자료 수집은 여전히 미완료. 완료 단계 **1~53/100**, 진행 중 **54**, 55단계는 시작하지 않았습니다.
- 기존 470개 엔트리는 **464개 바이트 동일, 6개 수정, 누락 0개**. 특히 원본 기획안, 요구사항 추적표, CSV 로드맵, 기존 `dev_company.sqlite3`는 **SHA-256 기준 동일** (`source_preservation.txt`). 사용자 PC와 외부 서비스에 접속하지 않았습니다.

## 실제 구현

1. `desktop/research_followup_domains.py` 신규. 기존 `build_full_queue_report()`의 일관된 SQLite 읽기 스냅샷을 재사용하여 **최신 최대 2,000개 HTML 링크**의 저장된 URL 문자열을 호스트별로 묶습니다. DNS, HTTP, 브라우저, 외부 API는 사용하지 않습니다.
2. 호스트별 URL 개수, 참조 자료 수 합계, `unregistered`/`archived_only`/`multiple_active`/`one_active` 개수, 수동 `deferred`/비보류 건수, URL 예시 최대 3개를 집계합니다. 로컬 미등록·보관본만 있는 URL이 많은 호스트를 우선 정렬합니다. **같은 호스트라는 사실은 사이트 소유·진위 검증이 아닙니다.**
3. `all`/`pending`/`deferred` 필터와 보관 자료 포함 조건을 기존 조사 목록과 동일하게 적용합니다. 화면에는 호스트 25개, API에는 최대 50개를 표시하며 전체 호스트·URL 수와 스캔 상한 초과 여부는 별도로 명시합니다.
4. `desktop/storage.py`에 관리자 권한을 먼저 확인하는 읽기 전용 조회 API 추가. `desktop/app.py` Tkinter 조사 화면에 **호스트별 조사 현황** 버튼 및 상세 결과 출력 추가.
5. 기존 후속 조사 목록의 상태 문구를 `실제 인터넷 접속 없음`으로 명확하게 바꿔 이전 GUI 스모크 검사에서 기대하던 문구와 일치시켰습니다. DB·기존 자료 변경 없음.
6. `tests/test_offline_research_followup_domains.py` 신규 (23개), `scripts/stage54_followup_domains_gui_smoke.py` 신규. 오프라인 일괄 검사에 신규 GUI 검사를 등록했습니다.

## 실제 검증 결과

- **pytest: 65개 서로 다른 테스트 파일을 8개 중복 없는 그룹으로 실행, 총 955개 통과 / 최종 그룹 실패 0개.** 각 그룹 파일 목록 및 로그(`group_1..8_*`) 보존. 그룹별 통과 수: **112, 106, 128, 96, 128, 135, 122, 128**.
- 신규 테스트 단독 재실행: **23개 통과** (`new_tests.log`). 신규·기존 관련 3개 테스트 파일 재실행: **50개 통과** (`related_retest.log`). 이들은 955개에 추가로 합산하지 않았습니다.
- **오프라인 실행 전체 검사: 35개 명령 통과** (`offline_runtime_full.log`). `sitecustomize.py`로 Python 소켓 연결·송신·DNS 조회 함수를 차단한 프로세스에서 자체 검사와 Linux Xvfb Tkinter GUI 검사를 수행했습니다. 이는 **OS 방화벽 수준의 네트워크 차단을 의미하지 않습니다**.
- 신규 GUI 검사에서 실제 Tkinter 버튼 조작, 관리자 로그아웃/재로그인, 수동 보류 필터 반영, 소켓 차단 조건을 확인했습니다. 기존 후속 조사 GUI도 수정 후 통과 (`offline_selected_retest.log`).
- `python -m compileall -q desktop scripts tests` 통과 (`compileall.log`). 원본 470개 파일 중 누락 0개, 원본 SQLite/기획안 SHA-256 동일, ZIP 자체 무결성은 별도 패키징 검사에 기록.

## 실패·제한 및 해석

- 최초 신규 테스트에서 **대소문자가 다른 URL 문자열 두 개를 동일 URL로 계산한 테스트 기대값 오류 1개**가 발생했습니다. URL 문자열은 별개이나 호스트 그룹은 동일한 것이 정상이라 기대값을 바로잡고 신규 23개 및 955개 전체 분할 회귀 검사를 통과했습니다.
- 최초 기존 `stage54_followups_gui_smoke.py` 실행은 기존 GUI 피드백 문구가 스모크 검사 기대 문구와 달라 실패했습니다. 실제 인터넷 접속이 없다는 뜻을 명시하도록 피드백을 수정했고, 이후 해당 검사와 35개 일괄 오프라인 검사 모두 통과했습니다. 초기 실패 기록은 `offline_selected.log`에 남겼습니다.
- **단일 명령으로 모든 pytest 테스트를 실행한 결과는 이번에 검증하지 않았습니다.** 분할 실행의 955개 통과와 단일 실행 통과는 구분해야 합니다. 과거 병렬 subprocess 실행 시간 1.5초 초과의 간헐적 실패 원인은 아직 확정·해결되지 않았으며, 이번 분할 테스트 통과가 원인 해결을 증명하지 않습니다.
- **Windows 10/11 실기기, Windows EXE 빌드, 실제 GGUF 모델 추론, 실시간 웹 조사·자동 자료 수집, 원격 출처 진위 확인은 미검증/미구현**입니다. 외부 서버, GitHub, 클라우드 AI API, 유료 서비스, 사용자 PC 설정 변경 없음.
- **100단계 로드맵 완료율: 53/100 = 53%. 실질 제품 완성도: 약 20~25%(주관적 추정, 객관적 검증 아님).** 54단계 완료 조건인 실제 인터넷 조사 및 자료 수집은 외부 접속 금지 때문에 충족하지 못했으므로 54단계는 계속 진행 중입니다.
