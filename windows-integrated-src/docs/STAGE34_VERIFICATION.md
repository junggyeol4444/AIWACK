# 34단계 검증 기록 — 실행 가능성 및 우선순위 분석

## 기준 및 구현 범위

- 원본: 실제 `AIWACK_Stage33_Local_Offline_Source.zip`을 로컬에서 압축 해제. `docs/progress.json`의 완료 `1..33`, `next_step=34`, 로드맵 34 `TODO`를 확인한 후 구현.
- 신규 `desktop/task_feasibility.py`: 사용자 입력·AI 출력 텍스트를 명령으로 취급하지 않는 규칙 기반 평가. 차단 업무의 기존 우선순위, 준비 계획 단계 수, 활성 목표의 계획 부재만 사용.
- 분석 상태: `needs_unblocking`(차단 해결), `needs_assignment`(배정 검토), `needs_breakdown`(세부 분할 검토), `needs_plan`(계획 수립). **어떤 상태도 AI 실행 가능/실행 성공을 보장하지 않음**.
- 추천 우선순위/점수는 내부 검토 순서용 휴리스틱. 0~100 점수는 성공 확률이 아님. 기존 업무 우선순위/실행 상태를 변경하지 않음.
- SQLite `company_task_assessments`를 `CREATE TABLE IF NOT EXISTS`로 추가. `BEGIN IMMEDIATE` 안에서 스냅샷 기록, 내용/출처 상태 변경 시에만 이력 추가, 오래된 제안 `stale` 처리. 이전 DB/업무/계획/승인/AI 모델 정보 보존.
- 기존 Tk `자동 업무 제안` 탭에 추천 우선순위·준비 상태·점수·근거·재분석 버튼 추가. 관리자 승인 없이 실제 업무 생성/실행 없음. 점수와 추천은 대기 제안에만 현재 정보로 표시.

## 검증 결과

| 검사 | 결과 |
|---|---|
| 신규 SQLite/규칙/보안 테스트 | `python -m pytest -q tests/test_task_feasibility.py` → **14개 통과** |
| 기존+신규 회귀 테스트 1 | `python -m pytest -q tests/test_admin_sections.py tests/test_api.py tests/test_autonomous_task_proposals.py tests/test_chief_chat.py tests/test_chief_company_status.py tests/test_chief_task_handoff.py tests/test_company.py tests/test_company_detection.py tests/test_company_health_monitor.py tests/test_database.py` → **85개 통과** |
| 기존+신규 회귀 테스트 2 | `python -m pytest -q tests/test_departments.py tests/test_designations.py tests/test_desktop.py tests/test_employee_access.py tests/test_employee_management.py tests/test_employee_models.py tests/test_employee_schema.py tests/test_hierarchy.py tests/test_local_models.py tests/test_project_structure.py` → **151개 통과** |
| 기존+신규 회귀 테스트 3 | `python -m pytest -q tests/test_task_artifacts.py tests/test_task_dependencies.py tests/test_task_execution.py tests/test_task_feasibility.py tests/test_task_parallel.py tests/test_task_priorities.py tests/test_task_routing.py tests/test_tasks.py tests/test_work_plans.py` → **133개 통과** |
| 전체 합계 | **369개 통과 (85+151+133)**. 단일 전체 실행은 시간 제한으로 미완료. |
| 실제 Tkinter GUI | `xvfb-run -a python -m scripts.stage34_gui_smoke` → **통과**. 점수순 정렬, 근거 조회, 관리자 승인 거절, 로그아웃, 재시작, 데이터 유지. |
| Python 네트워크 소켓 차단 검사 | `python -m scripts.verify_offline_runtime` → **통과**. 자체 검사와 기존 및 34단계 Tk GUI 검사. |
| 실제 33단계 데이터 마이그레이션 | 33단계 원본 ZIP의 `desktop.storage`로 SQLite 생성(관리자/목표/차단 업무/우선순위/제안 2건), 34단계 소스로 재개방 후 원본 유지, 평가 2건 생성, `PRAGMA foreign_key_check` 빈 결과 → **통과**. |
| 단계 정합성 | `python scripts/next_step.py` → **34/100 완료, 다음 35단계**. |
| Windows EXE 실기기 | **미실시/미검증**. Linux의 Xvfb GUI 검사는 Windows 호환성 검증이 아님. |
| 실제 GGUF 모델 추론·외부 업무 자동 실행 | **미실시/미검증**. 규칙 분석은 실제 AI 추론이 아님. |

## 한계 및 데이터 경계

- 실행 준비 상태는 업무 생성 *제안*의 **정적 사전 검토**다. 모델 성능·실제 실행 자원·사업성·의존성 전체·예산·성공 확률을 평가하지 않는다. 추천 우선순위를 실제 업무에 자동 적용하지 않는다.
- 분석은 관리자 로그인 상태에서 제안 스캔 시 최대 100개 및 별도 재분석 시 최대 200개씩 처리한다. 제안이 매우 많으면 모든 항목의 최신 평가를 보장하지 않는다.
- 로그인한 Tk 창이 열린 동안만 5분 주기 검사. 앱 종료 후 백그라운드 분석 없음.
- 사용자 SQLite 본문은 암호화되지 않는다. Python 소켓 차단은 로컬 모델 실행파일의 OS 수준 네트워크 격리가 아니다.
- GitHub·외부 서버·클라우드 AI API·자동 결제/거래 사용 없음. 사용자 DB, 비밀번호, 모델 파일 및 테스트 캐시를 누적 ZIP에 포함하지 않는다.
- 로드맵 **34/100 (34%)**, 실질 제품 완성도 **약 11~12% (비공식 주관적 추정)**는 서로 다른 지표이다. 다음 35단계는 복합 업무의 세부 계획 생성.

## 최종 ZIP 압축 해제본 재검증

`AIWACK_Stage34_Local_Offline_Source.zip`을 별도 폴더에 실제 압축 해제하여 `python scripts/next_step.py`가 **34 완료/35 다음**을 출력함을 확인했다. 압축 해제본에서 자동 테스트를 **85+151+133=369개 전부 통과(3묶음)**, `python -m scripts.verify_offline_runtime`을 **통과**했다. 오프라인 검사는 자체 검사와 Stage29~Stage34를 포함한 실제 Tk GUI 스모크를 모두 실행했다. 소스 ZIP은 **143개 파일**이며 사용자 SQLite DB·모델 파일·테스트 캐시는 제외했다. 마지막 문서 보완은 프로그램 코드/테스트 결과에 영향을 주지 않는다.
