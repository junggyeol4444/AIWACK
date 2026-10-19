# 26단계 검증 — 선행·후속 업무 의존성 관리 (PC 로컬 전용)

## 구현 범위

- `company_task_dependencies(task_id, prerequisite_id)`로 후속 업무가 완료를 기다리는 선행 업무를 연결. 기존 25단계 테이블/행은 비파괴적으로 유지.
- 등록·해제 이력을 `company_task_dependency_events`에 기록. 동일 연결 중복 저장은 변경 없음; 해제해도 과거 기록 유지.
- 자기 참조 및 직접·간접 순환 참조를 재귀 CTE로 거부. 등록과 상태 변경의 검사·저장을 `BEGIN IMMEDIATE` SQLite 트랜잭션으로 직렬화.
- 선행 업무가 모두 `done`이 아니면 후속 업무의 `in_progress`/`done` 전환 거부. 진행·완료된 후속 업무가 있으면 선행 업무 `done → todo` 재개 거부.
- 후속 업무에 연결된 선행 업무의 삭제 차단. 후속 업무 삭제 시 해당 연결 및 이력 정리. 감사 기록 실패 시 전체 작업 롤백.
- 관리자의 수동 관리 기능이며 AI 모델·외부 서버·GitHub 실행 없음.
- Tkinter `업무 의존성` 탭에 후속/선행 업무 선택, 연결/해제 버튼, 준비 상태·미완료 ID·변경 이력 표시.

## 재현 명령

```bash
python -m pytest -q
python -m pytest -q tests/test_task_dependencies.py tests/test_tasks.py tests/test_task_priorities.py tests/test_task_routing.py
python -m desktop.entry --self-test
xvfb-run -a python -m scripts.desktop_gui_smoke
python -m scripts.verify_offline_runtime
python scripts/next_step.py
```

## 검증 결과 (2026-10-12, Linux 테스트 환경)

- 전체 pytest: **282 passed in 44.89s** (원본 개발 폴더, 상세 실행 로그로 확인).
- 새 의존성 테스트 9개 포함. 의존성·업무·우선순위·배정 회귀: **65 passed**.
- EXE 진입점 `--self-test`: 성공(실제 EXE 빌드가 아니라 Python 실행).
- Xvfb 네이티브 Tk 버튼 조작, DB 재실행 및 의존성 차단·해제: **PASS**.
- Python 소켓 차단 환경의 진입점 자체 검사 및 Tk GUI: **PASS**.
- `next_step.py`: `Completed: 26/100`, `Next: 27/100`.
- ZIP 압축 해제본 전체 pytest: **282 passed in 44.14s**.
- ZIP 압축 해제본 Python 소켓 차단 자체 검사 및 Xvfb Tk GUI: **PASS**.

## 한계

- 사용자 Windows 10/11에서의 실제 EXE 빌드·실행과 GGUF 실제 추론은 미검증.
- 소켓 차단은 Python 수준 회귀 검사이며 OS 전체 네트워크 격리를 증명하지 않음.
- 의존성은 수동 업무 상태 변경을 검증할 뿐 자동 작업 실행/자동 스케줄러는 제공하지 않음.
- 로드맵 진행률 26%와 실질 제품 완성도 약 8% 추정은 별개이며, 후자는 정량 측정 결과가 아님.
