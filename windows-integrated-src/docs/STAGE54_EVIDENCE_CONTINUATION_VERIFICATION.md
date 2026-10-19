# Stage54 후속 개발: 로컬 본문 근거 발췌 (완료로 처리하지 않음)

## 근거 및 변경 범위

- 입력 소스: `AIWACK_Stage54_Offline_Reference_Trace_Continuation_Source.zip`.
- `docs/progress.json`: 1~53 완료, 54 진행 중. 다음 단계는 54로 유지.
- `desktop/research_captures.py`: 로컬 사본 본문을 읽어 검색어가 일치하는 행을 최대 두 개씩 발췌. URL 진위를 판단하거나 외부 접속하지 않음.
- `desktop/storage.py`: 로그인 소유자 권한 검사 후 읽기 전용 함수 제공.
- `desktop/app.py`: 기존 Tkinter 자료 수집 화면에 `검색어 근거 발췌 보고서` 버튼 제공.
- `scripts/stage54_evidence_gui_smoke.py`, `tests/test_offline_research_evidence.py`: 11개 신규 단위/통합 테스트 및 실제 GUI 검사.
- `scripts/verify_offline_runtime.py`에 신규 GUI 검사를 등록했지만 일괄 실행은 시간 제한으로 최종 요약을 얻지 못함.

## 데이터 및 안전 경계

- 기존 SQLite 스키마와 기존 데이터 수정 없음. 조회는 읽기 전용.
- 소유자(`company:manage`) 로그인 필수.
- 단일 행 검색어 1~80자, 최대 500개 SQLite 문서 조사, 최대 20개 자료에 대해 최대 2개 일치 행 발췌.
- 등록 URL은 검증되지 않은 메타데이터. 본문 해시 일치 여부는 *SQLite 기록 자체*의 무결성 확인이며 웹 출처 인증이 아님.
- 보고서는 원문 검색어와 일치한 자료의 발췌일 뿐 AI 추론, 자동 요약, 인터넷 검색 결과, 출처 신뢰성 판단이 아님.
- Python 소켓을 차단한 테스트에서 기능 동작. OS 전체 네트워크 차단, Windows 경로 및 실제 GGUF 추론은 검증하지 않음.

## 검증 결과

- 신규 및 관련 테스트: `python -m pytest -q tests/test_offline_research_evidence.py tests/test_offline_research_trace.py tests/test_offline_research.py` → **47 passed**.
- 전체 기존+신규 테스트 파일 55개, 중복 없는 파일 묶음 6개: **151 + 167 + 136 + 157 + 157 + 28 = 796 passed**.
- 기존 묶음 1~5는 `docs/verification_stage54_trace/group_{1..5}.txt`에 기록된 파일 목록을 사용했고, 마지막 묶음은 `tests/test_local_models.py`와 `tests/test_offline_research_evidence.py`로 구성함. 묶음 5의 **157 passed**는 이번 실행의 터미널 출력에서 확인함. 나머지 5개의 실행 로그는 `docs/verification_stage54_evidence/` 참조.
- 전체 `python -m pytest -q` 단일 실행은 약 27%에서 실행 제한 시간으로 종료됐으며 통과로 간주하지 않음.
- 진행 기록 갱신 후 `tests/test_offline_research_evidence.py tests/test_project_structure.py` → **16 passed**.
- `xvfb-run -a python scripts/stage54_evidence_gui_smoke.py` → GUI 검색 버튼, 재로그인 복원, Python outbound 소켓 연결 차단 검사 **PASS**.
- `python scripts/verify_offline_runtime.py` 전체 일괄 실행은 시간 제한으로 중단되었으며 **전 항목 통과를 주장하지 않음**.
- Python 컴파일 검사와 최종 ZIP 무결성 및 기존 소스 파일 보존 여부를 별도 확인함.

## 남은 작업

원본 54단계의 실시간 인터넷 검색, 웹페이지 직접 수집, 온라인 출처 진위 확인 및 AI의 자율 조사 기능은 **미구현**. 사용자가 금지한 외부 서버 접속을 수행하지 않았으므로 **54단계 전체 미완료**, 로드맵 **53/100** 유지. 실질 제품 완성도는 기존과 비슷한 **약 20~25% (주관적 추정)**.
