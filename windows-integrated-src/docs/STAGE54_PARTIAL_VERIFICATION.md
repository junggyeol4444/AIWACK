# AIWACK Stage54 — 인터넷 조사 및 자료 수집 (오프라인 부분 구현, **미완료**)

## 원본 및 범위

- 기반 ZIP: `AIWACK_Stage53_Local_Offline_Source.zip` (기존 53단계까지 완료)
- `docs/progress.json`: 완료 단계 1~53, `next_step: 54` 확인. 기능을 중복 개발하지 않음.
- 외부 서버 접속·검색·GitHub·클라우드 API **일절 사용하지 않음**. 원본 54단계의 자동 인터넷 검색/페이지 수집 목표는 아직 미구현 상태이며, **54단계를 DONE으로 표시하지 않음**.
- 로컬 오프라인 자료 수집 기능만 구현: 사용자가 확보한 텍스트/HTML 사본을 수동 등록·검색·보관.

## 실제 구현

- `desktop/research_captures.py`: SQLite 전용 불변 기록(보관 상태 제외), source URL metadata, SHA-256, raw text/HTML 사본 추출, 크기·입력 검사, 검색, 중복 차단. URL은 저장만 하며 접속하지 않음. 출처 검증 상태는 `unverified` 고정.
- `desktop/storage.py`: 관리자 권한 확인을 포함한 API + 기존 DB 초기화 시 CREATE TABLE IF NOT EXISTS 추가. 기존 데이터는 건드리지 않음.
- `desktop/app.py`: Tkinter `오프라인 조사 자료 수집` 탭에서 관리자만 수동 등록·검색·상세 조회·보관.
- `tests/test_offline_research.py`: 24개 단위·통합·거부·보안·중복·재시작 테스트.
- `scripts/stage54_offline_gui_smoke.py`: 실제 Tkinter 버튼·로그인·로그아웃·SQLite 복구 검증. Python socket 연결 차단.
- `scripts/verify_offline_runtime.py`: 신규 Tkinter 검사 등록.

## 검증 결과

- `python -m pytest -q tests/test_offline_research.py` → **24 passed**.
- 전체 pytest 단일 실행: **시간 제한으로 중단**되어 단일 실행 통과라고 주장하지 않음.
- 테스트 파일 전체 49개를 순서에 따라 **중복·누락 없는 4개 묶음**으로 실행:
  - 1~16: `169 passed`
  - 17~24: `134 passed`
  - 25~32: `196 passed`
  - 33~49: `210 passed`
  - **합계 709개 전부 통과(분할 실행)**. 해당 로그의 결과는 `docs/STAGE54_TEST_RESULTS.txt`에 별도 기록.
- `python -m compileall -q desktop tests/test_offline_research.py scripts/stage54_offline_gui_smoke.py` → 통과.
- Linux Xvfb 실제 GUI: `scripts.stage53_offline_gui_smoke`, `scripts.stage54_offline_gui_smoke`, `scripts.desktop_gui_smoke` → 각 통과.
- `python -m desktop.entry --self-test` → 0 종료; `python scripts/next_step.py` → **53 완료, 다음 54**.
- 전체 `python -m scripts.verify_offline_runtime`: 실행이 시간 제한으로 중단되었으며 **전체 묶음 통과로 주장하지 않음**.
- Windows 10/11 실기기 / PyInstaller EXE / 실제 GGUF / 실시간 웹 수집 / 서버 API 호출: **미검증 또는 미구현**.

## 제한 사항

- 사용자가 URL과 웹 콘텐츠를 임의로 붙여 넣으므로 **사실 확인, 시점 증명, 출처 신뢰성 보장 불가**. URL은 접속하지 않는다.
- HTML을 브라우저 실행하지 않고 HTMLParser로 텍스트만 추출; 원문 HTML을 보존하는 웹 아카이브는 아니다.
- 앱 로그인은 SQLite 파일 자체의 암호화나 운영체제 ACL을 대체하지 못한다.
- 자율적인 실제 인터넷 조사·자동 크롤링은 단계 완료 기준에서 제외할 수 없으므로 **로드맵 53/100 완료, 54 진행 중**, 실질 제품 완성도 약 20~25%(주관적 추정)로 유지.
