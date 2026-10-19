# Stage 45 — AI 회의 의견 수집·비교 (오프라인, 관리자 기록)

## 기준 소스

- 최신 실제 입력: `AIWACK_Stage44_Local_Offline_Source.zip` (181개 파일).
- `docs/progress.json`: 완료 1~44, 다음 45 및 기존 Tkinter/SQLite 구조 확인.
- 기획안의 제3장 AI 회의 4~5번(의견 제시, 대안 비교)에 대응하는 **초기 데이터·관리 화면 계층** 구현.

## 구현

- `desktop/meeting_opinions.py`: 로컬 SQLite `local_meeting_opinions` 신규 테이블. 스키마 초기화는 `CREATE TABLE IF NOT EXISTS`; 기존 DB 파일 삭제/변경 없음.
- 예정(`scheduled`) 상태 회의 안건에만, 해당 회의 활성 참석 직원으로만 의견 입력. 안건별 직원 1건, 찬성/보류/반대와 의견 근거·출처·대안 저장. DB UNIQUE/FK/트리거로 자격 확인과 저장 후 임의 변경·삭제 차단.
- 비교 화면: 회의별 안건 목록, 찬성·보류·반대 개수, 미제출 참석자, 서로 다른 입장의 유무, 기록된 실제 의견 표시. 미제출을 보류로 집계하지 않음.
- 관리자가 직원 명의로 입력하는 기록. AI가 스스로 의견을 만들지 않으며 최다 표를 자동 의사결정/승인/업무 생성으로 처리하지 않음.
- 취소된 회의의 의견은 열람 가능하나 새 입력 불가. 관리자 로그인 필요.

## 실행 검증 (2026-10-13)

- `python -m pytest -q`: **485 passed in 62.09s**, 0 failed (`docs/STAGE45_FULL_PYTEST.log`).
- `python -m pytest tests/test_meeting_opinions.py tests/test_meetings.py tests/test_project_chat.py tests/test_department_chat.py tests/test_direct_messages.py -q`: **82 passed**.
- `xvfb-run -a python scripts/stage45_offline_gui_smoke.py`: **PASS**. Linux/Xvfb 실제 GUI 버튼 클릭: 회의 생성/참석 확정/안건·의견 생성/서로 다른 의견 표시/중복 차단/잘못된 회의 선택 화면 초기화/로그아웃 후 재로그인 복원/취소 이후 입력 차단 (`docs/STAGE45_OFFLINE_GUI.log`). `socket.connect/connect_ex` 차단.
- `python scripts/verify_offline_runtime.py`: 기존 데스크톱 자체 검사 및 Tkinter GUI 스모크 **11개 명령 통과** (`docs/STAGE45_OFFLINE_RUNTIME.log`). 네트워크 연결 함수 패치로 외부 접속 금지.
- `python -m compileall -q desktop scripts tests`: 통과.

## 제한 및 미검증

- 검증 환경은 Linux Xvfb이며 **Windows 10/11 실기기, Windows EXE 빌드, GGUF 추론**은 미검증.
- AI의 자율적 발언, 회의 개최/의견 검증의 의미론적 정확성, 실제 회의 의사결정, 후속 업무 자동 배정은 구현하지 않음. 다음 46단계 대상.
- 이번 오프라인 검사는 Python 소켓 연결을 차단한 시험이며 PC 자체의 방화벽 검사는 아님.
- 실질 제품 완성도 약 15~18%는 주관적 추정. 로드맵 45/100 = 45%와 별개.
