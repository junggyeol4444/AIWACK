# Stage 44 — AI 회의 안건 및 참석자 관리 (오프라인)

## 구현

- 기존 Windows Tkinter 관리 화면에 `AI 회의 안건·참석자` 탭 추가.
- 단일 관리자 계정 권한 하에 회의 초안(제목/목적), 최대 20개 순서 지정 안건, 최대 30명 참여 직원 기록.
- `draft → scheduled → cancelled` 및 `draft → cancelled` 상태 관리. 예정 확정은 안건 1개와 활성 참석자 2명 이상 필요.
- 회의가 예정 또는 취소 상태가 되면 참석자와 안건 수정 방지. SQLite 트리거 및 외래키 제약 검증.
- 기존 데이터 삭제/초기화 없이 새 SQLite 테이블만 `CREATE TABLE IF NOT EXISTS`로 추가.
- 기존 메시지 기능 및 프로젝트 대화방과 독립된 데이터 저장.

**한계:** `scheduled`는 기록상의 예정 상태로 달력, OS 작업 스케줄러 및 자동 실행 기능과 연계되지 않습니다. 실제 AI 간 회의, AI 의견 생성 및 비교, 최종 의사결정, 후속 업무 배정은 45·46단계 이후 대상이며 미구현입니다. 로컬 UI의 접근 통제는 기존 관리자 로그인에 의존합니다.

## 검증 명령

```sh
python -m pytest -q
python -m pytest tests/test_meetings.py tests/test_project_chat.py tests/test_department_chat.py tests/test_direct_messages.py -q
python -m compileall -q desktop scripts tests
PYTHONPATH=. xvfb-run -a python scripts/stage44_offline_gui_smoke.py
```

- 최종 전체 pytest: **456개 통과, 0개 실패** (`docs/STAGE44_FULL_PYTEST.log`).
- 신규 44단계 기능 테스트: 17개 통과.
- 기존 직원 개인 메시지/부서 대화/프로젝트 대화 포함 테스트: 53개 통과.
- GUI 실제 버튼 동작 (`docs/STAGE44_OFFLINE_GUI.log`): Linux Xvfb Tkinter에서 생성/검증/확정/취소 및 SQLite 재시작 복원 통과. 소켓 연결 시도를 오류 처리한 환경에서 검사.
- Windows 10/11 실기기, GGUF 모델 추론, AI 자동 회의, 24시간 무인 운영 **미검증**.
- 이전 Stage43 ZIP 175개 파일 누락 없이 보존, `dev_company.sqlite3`와 `docs/original_project_spec.txt` 원본 바이트 일치 확인.

## 실질 완성도

100단계 로드맵 44/100(44%)는 단계 기록의 진행률일 뿐입니다. 제품 기능의 실제 완성도는 약 15~17%로 **근거가 제한된 주관적 추정**입니다. 상거래/자율 회의/실제 수익 및 Windows 실기기 검증은 미완료입니다.
