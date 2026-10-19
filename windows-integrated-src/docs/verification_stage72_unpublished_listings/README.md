# Stage72 상품 등록 및 가격 관리 — 오프라인 부분 구현

**원본 72단계, BLOCKED. 다음 73단계 '주문 접수 및 상태 관리'. 완전 완료 개수는 기존 54/100 유지.**

## 구현 범위

- `desktop/offline_listing_prices.py`: Stage71 `REVIEWED_DISCONNECTED` + 미래 `listing_draft_future` 계획 권한을 갖춘 계약과 동일 Stage68 시제품에서 유래한 Stage67 상품 ID를 대조하여 로컬 미게시 상품·가격 초안을 생성. Stage70/69/68/67/71 감사와 원본 파일 검사를 기존 API를 통해 재사용.
- 통화는 KRW/USD/EUR/JPY로 제한. 모든 가격은 관리자 **미검증 정수 최소 화폐단위**(KRW/JPY 원·엔, USD/EUR 센트)이며 환율/세금/할인 계산·실제 판매 가격이 아니다. 로컬 상품명/설명/가격 가정 메모만 기록; 비밀키·URL·이메일 입력 패턴은 보조 차단(완전한 비밀정보 탐지 보장 아님).
- 초안 생성·가격/문구 수정·관리자 자체 검토·폐기 및 버전별 SQLite 추가 전용 감사 SHA-256 해시 체인. 동일 채널/상품의 미폐기 초안 중복 차단, 원본 상품/계약 변경 stale 검사. 검토도 `REVIEWED_UNPUBLISHED`로 **미게시** 유지; 폐기는 종료 상태. 외부 상품 등록·게시·동기화·주문·결제 경로 없음.
- `desktop/storage.py` 관리자 권한·SQLite 즉시 트랜잭션, `desktop/app.py` 관리자 전용 Tkinter 화면, `scripts/stage72_listing_prices_gui_smoke.py` 실제 Xvfb GUI 검사, `scripts/verify_offline_runtime.py` 오프라인 검증 항목 추가. 기존 데이터 삭제·스키마 파괴 없음.
- SQLite 해시 체인은 무결성 검사이며 DB 관리자 공격을 방어하는 전자서명·OS 격리가 아니다. 관리자 자기보고는 실제 출시/가격 승인이나 시장 검증이 아니다.

## 검증·한계

실제 로그는 `logs/`와 ZIP 외부 검증 TXT에 있다. 선택 회귀만 수행한 경우 전체 프로젝트 회귀 통과로 보고하지 않는다. Windows 실기기/EXE, 실제 GGUF, 실제 외부 채널, 실거래·장시간 운영 미검증. Stage63 병렬 subprocess 시간 임계 실패 이력 미해결. 상세 사용자 수행 항목은 `USER_ACTIONS_PENDING.md`.

## 이번 실행의 실제 검사 결과

- Stage72 신규 pytest **39 passed** (`logs/stage72_only.txt`); Stage72+구조 **44 passed** (`logs/stage72_structure_final.txt`).
- 서로 다른 테스트 파일의 선택 회귀: Stage55~60 **125 passed**, Stage61~65 **129 passed**, Stage66~68 **87 passed**, Stage69~72+구조 **187 passed**. 합계 **528 passed, 0 failed** (`logs/regression55_60.txt`, `regression61_65.txt`, `regression66_68.txt`, `regression69_72.txt`). 최초 Stage66~72 통합 실행은 시간 제한으로 중단되었고 해당 미완료 로그(`regression66_72.txt`)를 보존; 이후 두 그룹으로 분할해 선택 범위 통과 확인.
- Linux Xvfb Stage72 실제 GUI 스모크 통과 (`logs/gui72.txt`). 소켓/DNS 차단 self-test 1 + Stage66~72 GUI 7 = **8개 명령 통과** (`logs/offline_*.txt`). 전체 77개 명령은 미실행.
- 단일 전체 프로젝트 pytest 미실행. Stage63 병렬 subprocess 시간 임계 실패 이력은 미해결/이번 범위 미재검증.
- ZIP 압축 해제본 Stage72+구조 pytest/GUI는 별도 최종 로그 참조. Windows 실기기/EXE, GGUF, 외부 판매 서비스·실거래·장시간 운영 미검증.
