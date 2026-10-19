# Stage77 — 구독·취소·환불 관리 (오프라인 부분 구현 / BLOCKED)

원본: `docs/original_project_spec.txt` / `docs/roadmap_100.csv` 단계77.

구현 범위:
- `desktop/offline_subscription_refund.py`: Stage73 모의 주문의 **가정** 통화/총액 스냅샷을 참조하는 로컬 가상 구독 계획(월간 모의 / 일회성 모의). 자동 갱신 없음.
- 모의 취소 요청 → 관리자 자체 확인, 모의 환불 **요청** → 거부 상태. 실제 완료 또는 승인 상태/호출/고객 정보 없음.
- 로컬 키 단위 중복 방지; 전역 이벤트 키 충돌 차단; 최대 가정 총액 이하의 정수 소액 단위만 허용. 변경된 Stage72 상품 원본은 LocalStore 변경 요청에서 거부.
- SQLite 두 추가 전용 테이블 + UPDATE/DELETE 금지 트리거; 감사 이벤트의 SHA-256 스냅샷·이전 해시 검증. 로컬 DB 관리자에 대한 암호학적 비부인성이나 보안 증명 아님.
- `desktop/storage.py`: 기존 단일 관리자 인증/SQLite 원자적 트랜잭션 API. 기존 데이터 삭제/마이그레이션 없음.
- `desktop/stage77_subscription_gui.py`: 독립 Tkinter 관리자 로그인 GUI. 기존 관리자 계정이 있어야 사용 가능. 실행: `python -m desktop.stage77_subscription_gui`. **실제 금융 서비스가 아님.**
- `scripts/stage77_subscription_gui_smoke.py`: Linux Xvfb 로그인·생성·모의 요청·로그아웃 검증.
- `tests/test_stage77_offline_subscriptions.py`: 입력 검증, 상태 전이, 멱등성, 감사 위변조 감지, 인증, SQLite 재시작 지속성 검증.

미완료: 실제 구독 관리/반복 청구, 판매 채널 및 결제사 로그인/API·웹훅 검증, 환불 실행/결제 취소/정산, 고객 개인정보·알림, Windows 실기기·실제 GGUF·장시간 자율 운영. 모두 사용자 환경에서 별도 승인/검증 필요.

단일 전체 프로젝트 pytest 및 모든 오프라인 명령 미실행; Stage63 시간 임계 실패 이력 미해결. 완전 완료 단계 **54/100**, 77단계 BLOCKED, 다음 **78단계 고객 정보 및 고객지원 업무**.

## 이전 단계 선택 회귀 참고

Stage71+72 전체 101개 선택 실행은 실제 실행했으나 **200초 도구 시간 제한으로 종료**됨(진행 표시 87/101 뒤 중단; **통과 건수로 집계하지 않음**). 해당 미완료 출력은 `pytest_selected_71_72.txt`에 기록. 이후 두 단계의 명시적 스모크 테스트 4개는 별도로 통과(`pytest_prior_71_72_smoke.txt`).

Stage73~77 선택 121개는 전부 통과(`pytest_selected_73_77.txt`). 따라서 **보고 가능한 완결 선택 pytest 수는 서로 중복 없는 125개**. 전체 회귀 완료를 주장하지 않습니다. 이전 Stage76 별도 TXT에는 ZIP 항목 수가 1,526으로 잘못 적혀 있으나 실물 Stage76 ZIP은 **1,576개**이며 이번 실행은 ZIP 실물 기준으로 보존/CRC를 다시 검증합니다.
