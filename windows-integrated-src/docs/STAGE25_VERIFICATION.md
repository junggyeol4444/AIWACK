# 25단계 검증 — 업무 우선순위 설정 (PC 로컬 전용)

## 구현 범위

- 기존 SQLite `company_tasks` 행은 변경하지 않고 우선순위 및 감사 이벤트 전용 테이블 두 개 추가. 이전 업무는 별도 저장 없이 `normal`로 읽음.
- 관리자가 `low`/`normal`/`high`/`urgent`를 수동 지정하고 변경 이력을 로컬 SQLite에 트랜잭션으로 기록. 중복 저장은 무변경 처리.
- 목록은 미완료 업무 우선, 긴급 → 높음 → 보통 → 낮음, 동률이면 업무 ID 오름차순. 완료·취소 업무는 뒤에 업무 ID 오름차순으로 표시.
- Tk `업무 관리`에 읽기 전용 우선순위 콤보박스, 저장 버튼, 우선순위 목록 열을 추가. 업무 선택·창 재실행 후에도 설정을 읽어 표시.
- 권한 확인, 잘못된 값·업무 번호 차단, 업무 삭제 시 이력 외래키 정리, 이벤트 기록 실패 시 우선순위 변경 롤백.
- 24단계의 담당 AI 배정 기능과 독립적이며, 우선순위만으로 모델을 호출하거나 업무를 실행하지 않음.

## 재현 명령

```bash
python -m pytest -q
python -m pytest -q tests/test_task_priorities.py tests/test_tasks.py tests/test_task_routing.py
python -m desktop.entry --self-test
xvfb-run -a python -m scripts.desktop_gui_smoke
python -m scripts.verify_offline_runtime
python scripts/next_step.py
```

## 검증 결과

Linux 환경의 Xvfb 기반 Tk 검사이며 Windows EXE 실행을 의미하지 않습니다.

- 전체 pytest: **273 passed in 124.66s**
- 업무·배정·우선순위 회귀 pytest: **56 passed in 12.77s**
- 자체 검사(`--self-test`): PASS
- 실제 Tk GUI 버튼·재실행 검사: PASS
- Python 소켓 차단 자체 검사·Tk GUI 검사: **PASS**
- `next_step.py`: `Completed: 25/100`, `Next: 26/100`

## 한계

- Windows 10/11 EXE 바이너리 빌드, 실제 Windows PC 구동 및 실제 GGUF 추론은 검증하지 않았음.
- 네트워크 차단은 Python socket 경로의 회귀 검사이며 운영체제 방화벽/전체 프로세스 격리가 아님.
- 자동 우선순위 결정, 업무 실행기, 의존성 관리, 외부 거래·결제는 이 단계에서 구현하지 않음.
- 로드맵 진행률 25%와 제품 완성도 추정 약 8%는 서로 다른 지표이며, 후자는 정량적 검증 수치가 아님.
