# AIWACK 54단계 부분 개발: 저장 URL 경고 전체 JSON 내보내기 및 재검사

## 기준 자료와 범위

- 기준 누적 ZIP: `AIWACK_Stage54_Offline_URL_Preflight_Continuation_Source.zip` (이 대화에서 확인한 최신 510개 파일). 초기 지정된 Evidence ZIP보다 최신본을 사용함.
- 개발 전에 ZIP 안의 `docs/original_project_spec.txt`(원본 기획안 제6장·14장 포함), `docs/requirements_traceability.md`, `docs/roadmap_100.csv`, `docs/roadmap_100.md`, `docs/progress.json`을 실제 열어 확인함. 독립된 원본 첨부 텍스트는 로컬 파일로 접근 불가해 ZIP 내 원본 사용.
- 원본 요구사항을 수정하지 않고, 기존 1~53단계 구현을 반복하지 않음. 54단계 인터넷 조사·자동 자료 수집은 **미완료**. 금지된 GitHub/외부 서버/API에 접속하지 않음.

## 실제 구현

1. `desktop/research_preflight_exports.py` 추가: 관리자 선택 경로에 저장 HTML 링크의 **경고 URL 전체**(최신 2,000개 링크 샘플·수동 검토 필터/보관 옵션 반영)를 JSON으로 내보냄. 기존 40개 GUI 표시 제한을 적용하지 않음. 한 SQLite 읽기 스냅샷을 사용하고 원본 수동 메모는 내보내지 않음.
2. 보고서 항목(경고 URL·경고 코드·로컬 후보 상태), 경고 유형별 개수, 샘플 상한/필터/범위를 포함. 결정적 UTF-8 JSON, SHA-256 **자체 체크섬**, 파일 최대 12MB, 관리자 명시적 절대 로컬 경로, 기존 파일 덮어쓰기 방지. 체크섬은 전자서명이 아님.
3. 로컬 JSON 재검사: 원본 JSON 구조/체크섬/경고 분류 규칙 검증 후 저장 당시 필터·범위로 현재 SQLite와 비교. 추가/누락/동일 URL 상태 변화 및 메타데이터 차이, 종류별 최대 20개 URL 미리보기. 네트워크/DNS/웹 접속·DB 쓰기 없음. 체크섬 통과는 출처 진위 인증이 아님.
4. `desktop/storage.py` 관리자 전용 API 2개 및 `desktop/app.py` Tkinter `URL 경고 JSON 저장`/`URL 경고 JSON 재검사` 버튼 추가. 기존 SQLite 테이블/자료·기존 내보내기 형식 변경 없음.
5. `tests/test_offline_research_preflight_exports.py` 21개 테스트와 `scripts/stage54_preflight_export_gui_smoke.py` 추가. `scripts/verify_offline_runtime.py`에 GUI 검사 등록.

## 이번 실행의 검증 (정확한 범위)

- 신규 테스트 파일 **21개 통과** (`new_pytest.log` / 초기 구현 테스트 2개 실패는 링크 수집기가 `.localhost` URL을 등록하지 않는 기존 정책을 확인해 테스트 URL을 `.local`로 수정 후 21개 통과). 기존 소스 동작은 변경하지 않음.
- 관련 4개 테스트 파일 **93개 통과** (`related_pytest.log`).
- `tests/test_offline_research*.py` 연구 영역 **329개 통과** (`research_pytest.log`). 위 21개·93개는 329개에 포함되므로 중복 합산하지 않음.
- Linux Xvfb에서 신규 Tkinter 실제 버튼 조작·파일 생성·재검사·추가 URL 차이·재로그인 확인. Python 소켓/DNS 함수 차단 환경에서 신규 및 기존 3개 GUI와 데스크톱 self-test 등 **선택한 5개 명령 통과** (`offline_selected.log`). OS 방화벽 수준 차단은 아님.
- Python `compileall` 검사 통과 (`compileall.log`).
- **전체 pytest 단일 실행은 제한 시간으로 중단**: 진행률 약 21%에서 도구 실행 시간 초과, 최종 전체 통과/실패를 판정할 수 없음 (`full_pytest.log`).
- **전체 `scripts.verify_offline_runtime` 일괄 실행도 제한 시간으로 중단**, 최종 통과를 주장하지 않음 (`offline_runtime.log`는 출력 버퍼 때문에 비어 있음). 대신 위 선택한 5개 명령을 독립적으로 검사함.
- 원본 기획안·요구사항 추적표·CSV 로드맵·기존 `dev_company.sqlite3`는 SHA-256 일치. 기존 510개 엔트리 전부 포함. 원본/수정 파일 비교는 `source_preservation.txt` 참조.

## 남은 한계

- 저장 URL 경고는 **문자열 기반 수동 검토 단서**로, DNS, 리다이렉트, 서버 IP, 출처 신뢰성, 실제 웹 콘텐츠를 검사하지 않음. 경고가 없어도 URL이 안전하다는 뜻이 아님. JSON에는 URL 자체가 들어갈 수 있으므로 사용자 선택 저장 경로의 기밀성은 별도 고려 필요.
- Windows 10/11 실기기·Windows EXE 빌드·실제 GGUF 모델 추론·장시간 자율 운영·실제 웹 자동 수집/결제 등 미검증. 이전 간헐적 병렬 작업 1.5초 타임아웃 원인 미해결.
- 로드맵 완료 **53/100 = 53%**, 현재 **54단계 진행 중**, 실질 제품 완성도 **약 20~25%**(기능 목표 대비 주관적 추정, 검증된 실물 사업 성과 아님).
