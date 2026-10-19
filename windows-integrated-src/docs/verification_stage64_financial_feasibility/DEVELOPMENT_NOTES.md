# 64단계 구현·검증 기록

- 기준: `AIWACK_Stage63_Offline_Market_Evidence_Continuation_Source.zip` 1,366개 파일. 원본 기획안/요구사항 추적표/`dev_company.sqlite3` 바이트 불변.
- 원본 요구사항 §4.1 비용·수익 불확실성 평가를 부분 구현. 원본 §4.6 실제 매출·정산·손익 요구사항을 가정 산술로 대체하지 않음.
- 신규 `desktop/financial_feasibility.py` 및 `tests/test_stage64_financial_feasibility.py`, `scripts/stage64_financial_feasibility_gui_smoke.py`.
- SQLite 가정 평가/감사 이력 테이블은 기존 테이블을 변경하지 않고 `CREATE TABLE IF NOT EXISTS`로 추가. 원본 데이터를 삭제/재생성하지 않음.
- 저장 실패 시 단일 트랜잭션 롤백. 입력/결과/감사 SHA-256 무결성 검사. UPDATE/DELETE 차단 트리거는 보조적 방어이며 강한 변조 방지 보장 아님.
- 비용/매출 모두 관리자 미검증 가정. 실제 거래/매출/정산/이익·고객 수요/가격·세금/현금흐름은 확인되지 않음.
- **단일 전체 pytest 시도는 시간 제한으로 중단**. 중단 전 약 13% 진행, 전체 회귀 통과라고 보고하지 않음. 이전 63단계의 병렬 실행 시간 임계 테스트 실패 이력도 유지.
- 55~64단계와 프로젝트 구조 관련 11개 테스트 파일 **237개 통과**, 64단계 신규 테스트 **37개 통과**. 별도 신규+61~64단계+구조 **112개 통과**.
- 전체 오프라인 69개 명령 실행 시도는 시간 제한으로 중단, 처음 14개 통과까지만 확인. 별도 마지막 4개(61~64단계 GUI)는 소켓/DNS 차단 조건에서 통과. **69개 전부 통과로 보고하지 않음.**
- Stage64 Tkinter 실제 GUI smoke는 Linux Xvfb에서 관리자 인증·취소·저장·결과·로그아웃 차단 통과. Windows 실기기/EXE 미검증.
- 기존 부분 구현 보류(54,56~63)는 재개발하지 않음. Stage64 BLOCKED 후 65단계로 전진.
