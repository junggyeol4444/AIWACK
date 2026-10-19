# AIWACK 54단계 오프라인 후속 개발: HTML 링크 목록

## 기준 및 진행 상태

- 입력 누적 소스: `AIWACK_Stage54_Offline_Audit_Continuation_Source.zip` (원래 파일 268개).
- 입력 `docs/progress.json`: 1~53단계 완료, 54단계 진행 중.
- **54단계는 아직 완료하지 않음.** 외부 서버에 접속하지 않으므로 원격 인터넷 검색·수집·출처 진위 검증을 구현하거나 실행하지 않음.
- Windows 오프라인 Tkinter와 로컬 SQLite 기존 구조를 보존함.

## 실제 코드 변경 내용

1. `desktop/research_captures.py`: 신규 HTML 자료 등록 시 `<a href>`의 안전한 HTTP(S) URL 문자열을 추출. 상대 링크는 관리자가 기재한 출처 URL을 기준으로 조합하며 `<base>`는 무시. javascript/data/file/mailto 및 비표준 포트 등의 주소는 무시. 중복 제거, 최대 100개로 제한.
2. `offline_research_html_links` SQLite 테이블 추가 (순서·출처 자료 ID·URL·미검증 상태), 외래키와 변경·삭제 차단 트리거. **이전 기록은 원시 HTML이 보존되지 않았으므로 링크를 소급 생성하지 않음.**
3. 조회 시 링크 URL 문자열과 같은 `source_url`로 이미 등록된 로컬 자료가 있는지를 표시하며, 이것은 **인터넷 출처의 진실성 검증이 아님.** 감사 기능에서 링크 참조 및 순서 무결성을 추가 검사.
4. `desktop/storage.py`: 관리자 권한 검사 후 링크 조회 API 추가.
5. `desktop/app.py`: 기존 `오프라인 조사 자료 수집` 탭의 `선택 HTML 링크 목록` 버튼과 검증 경고 표시.
6. 신규 테스트 `tests/test_offline_research_links.py` 16개, 실제 Tkinter GUI 검증 `scripts/stage54_links_gui_smoke.py` 및 `scripts/verify_offline_runtime.py`에 스모크 명령 추가.

## 실제 검증 결과

- 신규 테스트: **16개 통과**.
- 관련 조사 자료·신규 테스트 합계: **88개 통과**.
- 전체 `python -m pytest -q` **단일 실행**: 시간 제한으로 중단됐으므로 완료로 보고하지 않음. 로그 `docs/STAGE54_LINKS_PYTEST_FULL.log`.
- 전체 53개 테스트 파일을 중복 없이 네 묶음으로 실행: **129 + 217 + 227 + 200 = 773개 통과**. 각 실행의 결과는 `docs/STAGE54_LINKS_PYTEST_PART1.log`~`PART4.log`에 보존됨.
- 실제 Tkinter GUI 버튼 동작: **통과** (Linux Xvfb). `선택 HTML 링크 목록` → 미검증 URL 노출 → 로그인 재시작 후 복원. 실행 중 Python 소켓 연결 차단.
- 오프라인 런타임 검사: **26개 명령 통과**, `docs/STAGE54_LINKS_OFFLINE_RUNTIME.log`. Python socket 통신 제한이지 OS 전체 네트워크 방화벽 테스트는 아님.
- Python 컴파일 검사 통과, 누적 ZIP 무결성 검사 실시.
- 기존 ZIP **268개 파일 모두 보존**, 수정하지 않은 기존 파일은 바이트 동일. 원본 기획서와 기존 SQLite 파일 바이트 동일.

## 검증하지 못한 점과 범위 제한

- **실제 인터넷 자동 검색·웹페이지 다운로드·원격 출처 진위 확인 미구현.** URL 목록은 조사 후보일 뿐 실제 방문 기록이 아님.
- HTML 링크 추출은 URL 문자열만 저장하고 해당 링크의 내용을 가져오거나 실행하지 않음.
- HTML 악성 내용과 출처 정보는 검증되지 않은 외부 자료로 간주해야 함. 기존 텍스트 추출기에서 원격 사이트가 제공한 실제 원본이 맞는지는 알 수 없음.
- Windows 10/11 실제 기기, Windows 실행 파일 빌드, 실제 로컬 GGUF 추론은 검증하지 않음.
- 완료 로드맵 **53/100 = 53%**. 54단계는 진행 중. 실질 제품 완성도 **약 20~25%**, 주관적 추정.
