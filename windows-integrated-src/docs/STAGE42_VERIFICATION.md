# AIWACK 42단계 — 부서별 협업 대화 (Stage 42)

## 근거 및 변경 범위

- 기반 자료: `AIWACK_Stage41_Local_Offline_Source.zip` 안의 `docs/progress.json` (`completed_steps`: 1–41, `next_step`: 42).
- 원본 기획안 제3장 3.3의 부서별 대화, 제9장 SQLite 기반 데이터 보존, 관리자 통제 원칙과 100단계 로드맵 42번을 기준으로 작업했다.
- 원래 소스의 `docs/original_project_spec.txt` 및 `dev_company.sqlite3`는 수정하지 않았다. 기존 저장소를 삭제하거나 초기화하지 않는다.
- 신설: `desktop/department_chat.py`, `tests/test_department_chat.py`, `scripts/stage42_gui_smoke.py`.
- 수정: `desktop/storage.py` (초기화 + 권한 확인 서비스 API), `desktop/app.py` (부서 대화 탭과 UI 처리, 기존 `run()` 아래 잘못 중첩된 Stage38/41 메서드 위치 복구), `scripts/verify_offline_runtime.py` (새 GUI 검사 포함), `docs/progress.json`, `docs/roadmap_100.csv`, `README.md`.

## 구현 및 제약

1. 부서당 독립된 대화 기록. SQLite에서 `department_id`를 기준으로 최근 1~500건 조회(기본 200건). 표시 순서는 오래된 것부터.
2. 발신 직원이 현재 그 부서에 소속되고 `draft` 상태여야 쓰기 가능. 다르면 거부.
3. 입력값 검증(정수 ID, 공백 제외 1~4000자 본문) 및 부서·직원 참조 제한(FK RESTRICT), DB INSERT 트리거를 통한 회원성 확인, 메시지 본문 및 귀속 정보의 불변성.
4. 관리자 `agents:manage` 권한 검사. 로그인 전/로그아웃 후 열람/작성 차단.
5. 해당 직원이 다른 부서로 이동하거나 비활성화되어도 과거 메시지의 소속 및 본문은 변경되지 않음.
6. Tkinter `부서별 협업 대화` 탭에서 부서 ID, 발신 직원 ID, 메시지 입력 및 부서별 기록 조회. 조회 대상이 유효하지 않으면 이전 목록을 제거함.
7. 실제 AI 추론/자율 메시지/네트워크 통신/부서별 다중 사용자 권한 계정은 **미구현**. 관리자에 의한 **기록 대행**만 구현한 초기 단계.

## 검증

- `python -m pytest -q tests/test_department_chat.py tests/test_direct_messages.py tests/test_departments.py`: **30 passed** (해당 기능 및 인접 회귀 검사).
- `PYTHONPATH=. xvfb-run -a python scripts/stage42_gui_smoke.py`: **PASS**. 실제 Tk 버튼을 통한 기록, SQLite 조회, 서로 다른 부서 격리, 권한 차단 및 로그아웃 확인.
- `PYTHONPATH=. python -m pytest -q`: **421 passed in 53.02s**, 전체 pytest 통과.
- `PYTHONPATH=. python scripts/verify_offline_runtime.py`: **10개 통과**. 검사 프로세스의 소켓 연결을 차단한 채 로컬 엔트리·기존 Tkinter GUI·신규 GUI를 실제 실행했다. 이는 실제 OS 방화벽 차단 검사가 아니다.
- `python -m compileall -q desktop scripts tests`: **PASS**.
- 원문 기획서와 누적 ZIP에 포함된 `dev_company.sqlite3`의 원본 바이트 보존 확인.
- 실행 로그: `docs/STAGE42_FULL_PYTEST.log`, `docs/STAGE42_OFFLINE_RUNTIME.log`.
- Windows 10/11 실기기에서 직접 실행하지 않았음. 실제 GGUF 추론 및 장기 무인 작동은 미검증.

## 진행률

- 로드맵 42 / 100 (42%). 이전 단계 기록과 관계없이 제품 완성률과 같지 않음.
- 실질적인 자율형 AI 회사 제품 완성도 **약 14~16% (주관적인 기능 범위 추정치, 계측 지표 아님)**.
- 다음 로드맵 단계 43: 프로젝트별 협업 대화방.
