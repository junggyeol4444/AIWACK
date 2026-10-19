# Stage73 주문 접수 및 상태 관리 — 오프라인 부분 구현 (BLOCKED)

**원본 73단계; 실제 주문이 아닌 비실거래 상태 시뮬레이션. 다음 순번 74단계 '결제 서비스와 거래 검증 연동'. 완전 완료 단계 54/100 유지.**

## 구현한 로컬 범위

- `desktop/offline_order_simulations.py`: Stage72 `REVIEWED_UNPUBLISHED` 미게시 초안과 원본 계보 감사 검증 후 **실거래 없는** 모의 주문 수량 1~1000, 고정 가정 단가/총액/통화 스냅샷 생성. 실제 고객 데이터 없음. 사용자가 입력한 로컬 중복 방지 토큰(영문·숫자·`_`·`-`, 8~48자) 전역 UNIQUE. 동일 토큰+초안+수량 재요청은 기존 모의 기록 반환; 불일치 요청 거부. 토큰은 결제·고객·외부 주문 ID가 아님.
- 상태 `RECEIVED_SIMULATED` → `REVIEWED_SIMULATED` → `CLOSED_SIMULATED` 또는 생성·검토 단계에서 `CANCELLED_SIMULATED`; 종료/취소 후 변경 불가. `closed`는 **상품 전달·결제·배송 완료를 의미하지 않음**. 원본 초안 폐기/변경 시 상태 전환 보류.
- `desktop/storage.py` 관리자 권한과 SQLite 즉시 트랜잭션, `desktop/app.py` 관리자 전용 Tkinter 화면, `scripts/stage73_simulated_orders_gui_smoke.py` 소켓·DNS 차단 실제 Linux Xvfb GUI 스모크, `scripts/verify_offline_runtime.py` 선택 실행 항목 추가.
- SQLite 두 신규 테이블은 추가 전용 트리거, 상태 전환 이력의 SHA-256 체인/스냅샷 검증. 기존 테이블/데이터 삭제·변경 없음. 해시 체인은 DB 관리자 공격에 대한 전자서명/OS 격리가 아님.
- 외부 채널 접속, 주문 API, 결제, 고객 이름·이메일·주소, 재고, 배송, 세금/정산, 매출 기록을 **실행/생성하지 않음**. 총액은 사용자 미검증 가격 가정 × 모의 수량이며 실측 매출이 아님.

## 검증 한계

검증 로그는 `logs/` 및 ZIP 외부 검증 TXT 참조. 단일 전체 pytest 및 전체 오프라인 검사 미실행이면 전체 회귀 통과로 표시하지 않습니다. 이전 Stage63 병렬 subprocess 시간 임계 실패 이력은 별도 미해결. Windows 실기기/EXE, GGUF, 실제 외부 채널/결제, 장시간 자율 운영 미검증.

## 이번 실행의 실제 검사 결과

- Stage73 신규 pytest **48 passed** (`logs/stage73_only.txt`); Stage73+구조 **53 passed** (`logs/stage73_structure.txt`).
- 비중복 선택 회귀: Stage55~60 **125 passed**, Stage61~65 **129 passed**, Stage66~68 **87 passed**, Stage69~70 **81 passed**, Stage71~72 **101 passed**, Stage73+구조 **53 passed** = **576 passed, 0 failed**. Stage69~73 통합 실행은 약 30% 이후 시간 제한 중단(`logs/regression69_73.txt`), 이후 Stage69~70/71~72/73+구조 분할 통과.
- Linux Xvfb Stage73 GUI **통과** (`logs/gui73.txt`). 소켓/DNS 차단 오프라인 self-test 1 + Stage66~73 GUI 8 = **9개 명령 통과** (`logs/offline_selftest.txt`, `logs/offline_gui70_77.txt`). 전체 78개 명령 미실행.
- 단일 전체 프로젝트 pytest **미실행**. Stage63 병렬 subprocess 시간 임계 실패 이력은 해결/재검증하지 않음.
- 최종 ZIP 추출본 Stage73+구조 및 GUI 결과는 `logs/final_zip_extracted_*.txt` 참고.
