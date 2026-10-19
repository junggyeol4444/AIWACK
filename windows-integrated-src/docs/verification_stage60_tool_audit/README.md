# AIWACK 60단계 — 도구 사용 기록 및 실패 처리 (부분 구현)

- 원본 단계: 060. 실제 작업 도구 연결 — 도구 사용 기록 및 실패 처리.
- 기준: Stage59 누적 ZIP (1,203 파일); 기존 원본 기획안·추적표·SQLite는 변경하지 않음.
- 구현: 미디어 검사, 외부 연동 초안 저장·검토 **3개 로컬 작업 경계**에서 성공·실패를 별도 SQLite 감사 테이블에 추가 기록. 고정된 오류 분류(validation/permission/filesystem/internal)만 저장. SHA-256으로 저장된 필드 무결성 재확인, UPDATE/DELETE 트리거 거부. 관리자만 최근 이력 조회 및 실패 `acknowledged` → `resolved` 상태 기록. 실제 재시도·외부 연결·실행 없음.
- 보호: 실패 메시지/경로/본문/토큰/스택 트레이스는 감사 로그에 저장하지 않음. 원본 기존 미디어 검사/초안 기능과 데이터 보존.
- 한계: SQLite 파일을 관리자 권한으로 직접 변경하는 공격까지 막는 보안 감사 저장소는 아님. SQLite는 암호화되지 않음. **모든 도구의 사용 자동 기록·재시도·중단된 프로세스 복구·실제 외부 API/Windows 실패 처리 미구현**. 60단계는 부분 구현으로 보류하고 다음은 61단계.
- 테스트: `python -m pytest -q tests/test_stage58_media_adapters.py tests/test_stage59_offline_service_integrations.py tests/test_stage60_tool_use_audit.py`, `PYTHONPATH=. xvfb-run -a python scripts/stage60_tool_audit_gui_smoke.py`. 실제 실행 결과는 `logs/` 참조.
- 미검증: Windows 10/11 x64, Windows EXE, 실제 GGUF, 외부 서비스 계정·API, 장시간 자율 운영.

## 회귀 검사 중 발견된 문제와 재검증

- 첫 19번 그룹에서 `docs/progress.json`의 60단계 보류와 `docs/roadmap_100.csv`의 TODO 상태가 불일치해 프로젝트 구조 검사 1건 실패. CSV의 60단계 상태를 BLOCKED로 수정한 뒤 동일 4개 테스트 파일 11개 모두 통과. 원본 기획안은 변경하지 않음.
- 첫 22번 그룹의 병렬 실행 시간 검사 1건이 1.64초로 1.5초 기준을 초과했고 동일 그룹 재실행도 1.88초로 초과. 기존 코드나 시간 기준을 임의로 완화하지 않음. 나머지 43개 테스트는 분리 실행에서 통과, 병렬 시간 검사 1개는 단독 실행에서 통과. **병렬 시간 검사에는 환경 부하에 따른 변동성이 있으며 통합 실행 통과라고 주장하지 않음.**
- 단일 전체 pytest는 실행 제한으로 중단. 전체 테스트 파일을 그룹으로 분할하고 위 실패 항목을 별도 재검증한 결과만 보고.
