# Stage71 외부 판매 채널 연결 구조 — 오프라인 부분 구현

**원본 71단계, BLOCKED. 다음 개발 72단계 '상품 등록 및 가격 관리'. 완전 완료 단계는 기존 54/100 유지.**

## 실제 구현

- `desktop/sales_channel_contracts.py`: Stage70 운영 계획이 관리자 자기보고 검토되었고 원본이 변경되지 않은 경우에만 **비활성 판매 채널 연결 계획**을 생성. Stage69 출시 보류 시제품/Stage68 파일 무결성/Stage67 카탈로그/Stage70 감사 이력 검증을 재사용한다. Stage70의 새 검토·폐기, 상품 원본 변경/철회, 출시 보류 재검토 시 연결 계획을 stale로 표시하고 신규 자체 검토 차단.
- 채널 종류 4종, 미래 대상 지역 3종, 미래 연결 방식 2종, 계획된 권한 범위 4종 중 1~4개, 로컬 별칭·매핑·규정 계획 텍스트만 기록. **URL, 계정 ID, 이메일, 인증 비밀키, 토큰, 실제 외부 서비스 API 호출은 제공하지 않음.** 단순 문자열 차단은 모든 민감정보를 완벽히 판별하지 못하므로 비밀정보를 입력하지 말 것.
- 관리자 준비 체크리스트 5항목의 `unverified`, `needs_work`, `owner_reports_prepared` 상태만 수동 기록. `owner_reports_prepared`는 외부 판매 채널의 실제 사용 승인/연결 확인이 아니다.
- 상태는 `DRAFT_DISCONNECTED`, `REVIEWED_DISCONNECTED`, `RETIRED_DISCONNECTED`만 가능. `connected`, `listing_created`, `orders_received`, `payments_received`, `credentials_stored`는 항상 거짓. 연결/상품 등록/판매/금전 거래 기능 없음.
- `desktop/storage.py` owner 권한 검사·SQLite 트랜잭션, `desktop/app.py` Tkinter 관리자 화면, `scripts/stage71_sales_channel_gui_smoke.py` 실제 GUI 스모크 검사. SQLite 감사 행 UPDATE/DELETE 차단 트리거, revision·SHA-256 해시 체인/계획 스냅샷 무결성 검사. SQLite 해시는 OS/DB 관리자 공격에 대한 암호학적 서명·격리 수단이 아님.
- 원본 기획안/로드맵 1~70단계 기존 소스/설정/사용자 데이터/SQLite 파일 보존. 외부 네트워크·GitHub·클라우드 AI·계정 연동·설치·결제 미사용.

## 한계 및 검증

실제 검사 결과는 `logs/`와 ZIP 밖의 별도 검증 TXT를 참조. 단일 전체 pytest 또는 전체 오프라인 검사를 실행하지 않은 경우 전체 통과를 주장하지 않는다. 기존 Stage63 병렬 subprocess 시간 임계 실패는 해결되지 않았다. Windows 실기기/EXE·실제 GGUF·실제 판매 채널·장시간 자율 운영 미검증. 사용자 수행 목록은 `USER_ACTIONS_PENDING.md`.

## 이번 실행의 실제 검사 결과

- Stage71 신규 pytest **62 passed** (`logs/stage71_only.txt`); Stage71+구조 **67 passed** (`logs/new_tests.txt`).
- Stage55~60 선택 회귀 **125 passed**, Stage61~65 **129 passed**, Stage66~71+구조 **235 passed**. 세 그룹은 서로 다른 테스트 파일로 **선택 회귀 총 489 passed, 0 failed** (`logs/regression*.txt`). Stage66~71 그룹은 도구 실행 결과 표시가 시간 제한으로 끊겼으나 프로세스가 정상 종료했고 로그 끝에 235 passed가 기록되었다.
- Linux Xvfb Stage71 Tkinter GUI 통과 (`logs/gui71.txt`). 소켓·DNS 차단 self-test 1개 + Stage66~71 GUI 6개 = **7개 명령 통과** (`logs/offline_*.txt`). 전체 76개 오프라인 명령은 미실행.
- 단일 전체 프로젝트 pytest 미실행. Stage63 병렬 subprocess 실행 시간 임계 테스트 실패 이력은 미해결/이번 범위 미재검증.
- 최종 ZIP 압축 해제본의 신규+구조 pytest/GUI 검사는 별도 로그 참조. Windows 실기기·EXE, 실제 GGUF·외부 판매 서비스·장시간 자율 운영 미검증.
