# AIWACK 54단계 후속 작업 — 로컬 파일 증거 가져오기 (진행 중)

## 기준 및 작업 범위

- 기반: `AIWACK_Stage54_Local_Offline_Source.zip`, 239개 파일.
- `docs/progress.json`: 완료 1~53, 다음 54. 단계 번호 중복 또는 건너뛰기 없음.
- 원본 54단계의 **인터넷 조사 및 자료 수집** 중 로컬에서 수행 가능한 부분을 개선.
- 외부 서버/GitHub/클라우드 AI API/브라우저 자동접속: 실행 및 통합하지 않음.

## 실제 구현

- `desktop/research_captures.py`: 사용자 지정 로컬 `.txt/.md/.html/.htm` 읽기,
  UTF-8 검증, 최대 256,000바이트 검사, 심볼릭 링크·UNC·매핑된 Windows 네트워크
  드라이브 거부 시도, 원본 바이트 SHA-256와 추출 본문 해시 분리 저장.
  저장되는 것은 텍스트와 메타데이터이며 원본 파일 바이트나 외부 URL의 내용은
  **검증하거나 보존하지 않음**. 파일명만 기록하여 절대 경로 노출 축소.
- 로컬 파일 출처 메타데이터용 SQLite 테이블
  `offline_research_local_imports` 신규 추가. `CREATE TABLE IF NOT EXISTS`로
  마이그레이션하며 기존 조사 자료/SQLite 데이터는 삭제하지 않음.
- 저장 트랜잭션 내 새 자료와 가져오기 메타데이터를 함께 기록. 변경·삭제 금지
  트리거 및 기존 URL + 본문 중복 차단 유지.
- `desktop/storage.py`: 관리자 로그인/권한 검사 포함 `import_offline_research_file`.
- `desktop/app.py`: Tkinter `로컬 파일 가져오기` 및 원본 해시 표시.
- `tests/test_offline_research_imports.py`: 14개 신규 테스트.
- `scripts/stage54_local_import_gui_smoke.py`: 실제 Tkinter 버튼 조작 및 재로그인,
  Python 네트워크 소켓 호출 차단 검사.
- `scripts/verify_offline_runtime.py`: 신규 GUI 스모크 검사 등록.

## 검증 결과 (실제로 완료한 실행만 기재)

- pytest 파일 전체 50개, **723개 통과(5개 실행으로 분할)**:
  - `pytest_group_1.log`: 129 passed
  - `pytest_group_2_without_local_models.log`: 200 passed
  - `pytest_local_models.log`: 17 passed
  - `pytest_group_3.log`: 210 passed
  - `pytest_group_4.log`: 167 passed
- 신규 파일 가져오기 테스트: **14 passed** (최종 수정 뒤 재실행).
- 기존 조사 자료 테스트: **24 passed**.
- Linux Xvfb GUI: `scripts.stage53_offline_gui_smoke`,
  `scripts.stage54_offline_gui_smoke`, `scripts.stage54_local_import_gui_smoke` 통과.
- `python -m desktop.entry --self-test`: 0 종료.
- `python -m scripts.verify_offline_runtime` 전체 일괄 실행은 시간 제한으로
  끝나지 않았으므로 **일괄 통과로 주장하지 않음**.
- Windows 10/11 실기기, Windows 네트워크 드라이브 안전성, GGUF 추론: **미검증**.

## 완료되지 않은 54단계 원래 목표

원본 기획은 실제 인터넷 조사·웹페이지 자동 수집을 요구한다. 현 개발 환경에서는
**외부 서버 접속 금지**가 우선 적용되므로 실제 웹 수집·진위 검증·자동
시장조사를 구현/시험하지 못했다. URL은 단지 관리자가 입력한 미검증
참조 문자열이다. 원본의 54단계를 **DONE으로 표시하지 않는다**.

## 한계와 보안 주의

- SHA-256은 가져온 로컬 파일의 동일성 비교용일 뿐 출처의 신뢰성/정확성 증명이 아니다.
- 파일을 읽는 동안 바뀌지 않았는지 검사하지만, Windows에서 최종 경로 링크
  경쟁 조건과 네트워크 드라이브를 실기기로 검증하지 않았다.
- 파일 가져오기 기능은 크기·형식 제한을 두는 것일 뿐 악성 내용의 사실성 판단
  및 프롬프트 인젝션 방어를 보장하지 않는다. HTML/파일 내용은 실행하지 않는다.
- SQLite 데이터베이스 암호화 미제공. 실제 인터넷 자동 검색·실행 미제공.
