# AIWACK 54단계 부분 구현 — 로컬 HTML 출처 자기 표기 사전 검토

## 기준 및 완료 상태

- 기준 누적 ZIP: `AIWACK_Stage54_Offline_Bundle_HTML_Link_Preview_Continuation_Source.zip` (663개 파일).
- 실제 확인: `docs/original_project_spec.txt`, `docs/requirements_traceability.md`, `docs/roadmap_100.csv`, `docs/roadmap_100.md`, `docs/progress.json`.
- 원본 54단계 완료 조건: **인터넷 조사 및 자료 수집**. 외부 접속 금지 때문에 미완료. 기존 **1~53 완료, 54 진행 중** 유지. 별도 독립 원본 기획안 텍스트는 현재 실행에서 접근하지 못했으므로 ZIP 내부 원본을 사용함.

## 이번 코드 변경

- `desktop/research_captures.py`: 비활성 HTML의 `<link rel="canonical">` 및 `<meta property="og:url">`에서 자체 표기 출처를 추출. 사용자가 주장한 출처 URL과 문자열 비교해 `match`, `mismatch`, `invalid` 분류. HTML당 최대 8개, UI 예시 최대 4개. 외부 `<base>` 무시, 비웹 스킴 경고, 숨긴 script/style/template 내용에서 추출하지 않음.
- `desktop/app.py`: 자료 묶음의 사전 승인 전 HTML 자체 표기 상태 표시와 불일치/형식 오류 건수 경고. 승인 취소 시 데이터 기록하지 않음. 명시적 승인으로만 기존 SQLite 등록. 기존 승인 토큰은 HTML 파일 SHA-256에 결속돼 변경 시 재검토 요구.
- `tests/test_offline_research_bundle_source_hints.py`: 11개 신규 테스트(일치·불일치·형식 오류·상한·권한·DB 불변·승인 변경·네트워크 차단 등).
- `scripts/stage54_source_hints_gui_smoke.py`: Linux Xvfb 실제 GUI 로그인, 경고 표시, 취소, 승인 등록 확인.
- 기존 Windows 오프라인 Tkinter·로컬 SQLite 구조 변경 없음. 네트워크, DNS, GitHub, 클라우드 AI 미사용.

## 검증 기록

- 관련 테스트: `related_pytest.log` — 36개 통과, 실패 0.
- GUI: `gui_smoke.log` — Linux Xvfb 실제 Tkinter 버튼 조작 통과. 코드에서 소켓·DNS 호출을 금지한 상태로 검사함.
- 전체 `pytest` 단일 실행: `full_pytest_incomplete.log` — 약 18% 진행 후 실행 환경 제한으로 중단, 전체 단일 실행 **미완료** (통과로 표기하지 않음).
- 전체 테스트 수집: 1,180개. `group_01.log`~`group_08.log`, `split_results.json`에 표시된 서로 겹치지 않는 8개 파일 묶음의 pytest 총 **1,180개 통과 / 0 실패**.
- 원본 보존: `source_preservation.json` — 기존 파일 663개 모두 보존. 657개 바이트 일치, 기존 코드·문서 6개 수정. 원본 기획안, 요구사항 추적표, 로드맵 CSV 및 기존 SQLite DB SHA-256 불변.
- `offline_runtime.log`: Python 소켓·DNS 함수 차단 환경에서 데스크톱 자체 실행 및 Tkinter GUI 포함 **47개 명령 통과**. 이는 OS 전체 네트워크 차단을 의미하지 않음.
- `reextract_related_pytest.log`: 전체 소스 ZIP 예비본을 독립 폴더에 압축 해제한 뒤 관련 테스트 **36개 통과**. `reextract_gui.log`: 동일 압축 해제본에서 실제 Tkinter GUI 통과.

## 해석 제한

HTML 메타데이터는 원본 출처를 인증하는 신뢰할 수 있는 근거가 아니다. `match`는 URL의 문자열 일치만 뜻하며 웹사이트 접근 가능성·보안·독립성·진실성을 의미하지 않는다. Python 소켓 호출 차단은 운영체제 방화벽이나 임의의 외부 프로세스를 통한 전송 차단을 보장하지 않는다. Windows 실기기, Windows EXE, 실제 GGUF 추론, 장시간 무인 운영 및 실시간 인터넷 자동 조사·수집은 검증하지 않았다. 실질 제품 완성도 **약 20~25%**는 주관적인 추정이며 로드맵 완료율 **53%**와 별개다.
