# AIWACK 61단계 — 범용 사업 유형 관리 시스템 (부분 구현)

기준 ZIP: `AIWACK_Stage60_Tool_Use_Audit_Continuation_Source.zip` (기존 파일 1,246개).
원본 기획안 §4.2의 사업 유형 14종은 **예시**이며 유형 등록을 제한하는 목록이 아닙니다. 관리자는 임의 신규 유형을 추가할 수 있습니다.

## 실제 구현

- `desktop/business_portfolio.py`: 범용 유형 14종 예시 초기 등록, 사용자 정의 유형 키/설명 등록, 유형 비활성(기존 사업 유지).
- 한 유형에 여러 사업 등록: 고유 ID·사업명·목표·계획 예산(원, 실제 지출 아님)·기존 직원 ID 책임자·참여 직원 목록·상태 `draft/active/paused/closed`.
- 사업 상태 전환 규칙 및 종료 사업의 재활성화 차단, 다중 사업에 같은 직원 참여 가능, 직원/사업/유형 ID의 실제 로컬 SQLite 참조 검사.
- 사업 변경 기록 추가 전용 테이블 및 SHA-256 값 검사. DB 자체는 암호화/외부 변조 방지 저장소가 아님.
- `desktop/storage.py`: 관리자 인증/권한 검사를 거치는 로컬 CRUD 래퍼. `desktop/app.py`: 관리자 전용 Tkinter 사업 관리 화면, 목록·상태·참여·감사 이력 조회.
- `tests/test_stage61_business_portfolio.py`, `scripts/stage61_business_portfolio_gui_smoke.py`: 유효성·상태·직원 참조·다중 사업·로그아웃·영속성·오프라인 GUI 검사.

## 미구현·보류 (완료로 계산하지 않음)

- 실제 사업 발굴/평가/선택 및 AI 직원의 자율 업무 실행, 판매·배포·외부 서비스 계정·고객·매출/지출/순이익·사업 평가 기록의 통합.
- 이 단계의 `active`는 **로컬 계획 상태**일 뿐 실제 사업을 시작하지 않음. 예산은 금전 이체/결제와 무관한 입력값.
- Windows 10/11 실기기, Windows EXE, 실제 GGUF 추론, 외부 API 및 장시간 자율 운영 검증 없음.
- 단계 상태 `PARTIAL_BLOCKED`, 원본 로드맵 **다음 개발 62단계 '신규 수익 사업 후보 자동 발굴'**. 완료 개수 54/100은 변하지 않음.

검증: `logs/`, `verification.json`, `USER_ACTIONS_PENDING.md`. 원본 기획안/추적표/기존 DB 및 사용자 자료 보존 검사 결과는 최종 보고서 참고.
