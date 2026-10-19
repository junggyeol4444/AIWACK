# 29단계 검증 기록 — 독립 업무 병렬 실행

기반: `AIWACK_Stage28_Local_Offline_Source.zip` 압축 해제, `docs/progress.json`에서 `next_step=29` 확인. 신규 코드: `desktop/storage.py`, `desktop/app.py`, `tests/test_task_parallel.py`, `scripts/stage29_gui_smoke.py`.

| 검증 | 명령 | 결과 |
|---|---|---|
| 자동 테스트 첫 묶음 | `python -m pytest -q tests/test_admin_sections.py tests/test_api.py tests/test_chief_chat.py tests/test_chief_company_status.py tests/test_company.py tests/test_database.py tests/test_departments.py tests/test_designations.py` | 77 통과 |
| 자동 테스트 두 번째 묶음 | `python -m pytest -q tests/test_desktop.py tests/test_employee_access.py tests/test_employee_management.py tests/test_employee_models.py tests/test_employee_schema.py tests/test_hierarchy.py tests/test_local_models.py tests/test_project_structure.py` | 117 통과 |
| 자동 테스트 세 번째 묶음 | `python -m pytest -q tests/test_task_artifacts.py tests/test_task_dependencies.py tests/test_task_execution.py tests/test_task_parallel.py tests/test_task_priorities.py tests/test_task_routing.py tests/test_tasks.py tests/test_work_plans.py` | 119 통과 |
| 전체 단일 실행 | `python -m pytest -q` | **313 통과, 39.56초** (최종 재실행). 초기 시도에서는 실행 환경 지연으로 중단됐으며 최종 단일 전체 결과는 통과 |
| Stage29 신규 테스트 | `python -m pytest -q tests/test_task_parallel.py` | 9 통과: 2개 예약·3번째 거부, 직원 중복 차단, 선행 관계, 병렬 취소 격리, SQLite 동시 예약, 기존 인덱스 마이그레이션, 모델 보호, 로그인·복구, 실제 로컬 CLI 2개 겹침 |
| 기존 실제 GUI | `xvfb-run -a python -m scripts.desktop_gui_smoke` | 통과: 기존 28단계 결과물 검수까지 유지 |
| 신규 실제 GUI | `xvfb-run -a python -m scripts.stage29_gui_smoke` | 통과: Tk에서 서로 다른 업무 2개 클릭, 실제 CLI 2개 동시 실행, 응답 분리, 수동 결과물 저장, 선택 업무 취소 버튼, 재로그인 보존 |
| EXE용 자체 검사 | `python -m desktop.entry --self-test` | 통과 (Windows EXE 빌드는 아님) |
| 네트워크 소켓 차단 검사 | `python -m scripts.verify_offline_runtime` | 통과: 자체 검사·기존 GUI·신규 병렬 GUI (Python 소켓 차단) |
| 단계 일관성 | `python scripts/next_step.py` | 29 완료 / 30 다음 |
| ZIP 압축 해제본 회귀 검사 | 새 디렉터리에 압축 해제 후 동일한 3개 pytest 묶음 | **77 + 117 + 119 = 313 통과** |
| ZIP 압축 해제본 오프라인 GUI | 압축 해제본에서 `python -m scripts.verify_offline_runtime` | 통과: 자체 검사, 기존 Tk GUI, Stage29 병렬 Tk GUI |
| Windows EXE 실기기, 실제 GGUF 모델 추론 | 미실시 | 미검증 |

**한계:** 사용자 선택 외부 로컬 실행파일의 OS 네트워크 사용은 격리되지 않습니다. GUI 임시 출력은 프로세스 종료 시 소멸하며 명시적으로 저장한 본문만 암호화되지 않은 로컬 SQLite에 남습니다. 모델 RAM/GPU 메모리 부족이나 드라이버별 병렬 추론 안정성은 검증되지 않았습니다. 원본 기획서의 다중 AI 장시간 부하·자율 운영 통합 테스트는 아직 미검증입니다. 작업은 관리자 확인 없이 시작하지 않습니다.
