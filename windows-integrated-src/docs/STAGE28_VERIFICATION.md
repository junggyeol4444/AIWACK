# 28단계 검증 기록 — 업무 결과물 저장 및 검수

기반: `AIWACK_Stage27_Local_Offline_Source.zip`; `docs/progress.json`의 `next_step=28` 확인.

| 항목 | 실행 | 결과 |
|---|---|---|
| 기존 기능 + 신규 자동 테스트 (첫 묶음) | `python -m pytest -q tests/test_admin_sections.py tests/test_api.py tests/test_chief_chat.py tests/test_chief_company_status.py tests/test_company.py tests/test_database.py tests/test_departments.py tests/test_designations.py` | 77 통과 |
| 두 번째 묶음 | `python -m pytest -q tests/test_desktop.py tests/test_employee_access.py tests/test_employee_management.py tests/test_employee_models.py tests/test_employee_schema.py tests/test_hierarchy.py tests/test_local_models.py tests/test_project_structure.py` | 117 통과 |
| 세 번째 묶음 | `python -m pytest -q tests/test_task_artifacts.py tests/test_task_dependencies.py tests/test_task_execution.py tests/test_task_priorities.py tests/test_task_routing.py tests/test_tasks.py tests/test_work_plans.py` | 110 통과 |
| 단일 전체 자동 테스트 | `python -m pytest -q` | 120초 제한으로 두 차례 중단. 전체 단일 통과 주장하지 않음 |
| 실제 Tk 데스크톱 조작 | `xvfb-run -a python -m scripts.desktop_gui_smoke` | 통과: 로그인, 실제 실행, 명시적 결과 저장, 검수, 재열기 |
| EXE용 자체 검사 | `python -m desktop.entry --self-test` | 통과 |
| 네트워크 차단 상태 검사 | `python -m scripts.verify_offline_runtime` | 통과: 자체 검사와 실제 Tk GUI |
| 단계 순서 검사 | `python scripts/next_step.py` | 28 완료 / 29 다음 |
| Windows EXE 실기기 및 GGUF 모델 | 미실시 | 미검증 |

보안·한계: 저장된 결과물 본문은 로컬 SQLite에 **암호화되지 않은 평문**으로 남음. GUI 저장은 명시적 관리자 승인만 허용함. 검수 결과가 업무 상태를 변경하거나 모델을 재호출하지 않음. 파이썬 소켓 차단은 임의 외부 실행파일의 OS 네트워크까지 차단한다는 보장은 아님. 관리자 DB 파일 직접 변조에 대한 불변성 보장은 제공하지 않음.
