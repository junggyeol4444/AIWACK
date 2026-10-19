# 67단계 — 상품 및 서비스 정보 관리 (오프라인 부분 구현)

기준: `docs/original_project_spec.txt` §4.4(상품·서비스 제작), §4.5(판매/결제), `docs/requirements_traceability.md` R06·T10/T11, 원본 로드맵 67번. 원본 완료 조건을 축소하지 않으며 원본 기획안과 요구사항 추적표는 변경하지 않는다.

## 실제 구현

- 61단계의 실제 로컬 사업 ID에 상품/서비스 정보 초안을 등록. 66단계 사업 프로젝트 ID를 선택적으로 연결하며 **동일 사업·미종료 프로젝트만** 허용한다. 기존 사업·프로젝트/업무 데이터는 수정하지 않는다.
- 종류(`product`/`service`), 명칭, 설명, **미검증 가정 가격 KRW**, 제공 계획을 저장한다. 가격은 실제 판매 가격이나 거래 금액이 아니다.
- 관리자 수동 검토 상태 `draft`, `review_pending`, `archived`. `review_pending`은 **출시/판매/결제 승인이 아니다**. 실제 `published`, `sold` 등 상태가 없다.
- `draft`에서 설명·가정 가격·제공 계획만 개정 가능. 각 변경은 버전 번호와 전체 스냅샷 감사 이벤트로 남는다. 사업/프로젝트 연결·상품 종류·이름은 생성 후 변경 불가.
- SQLite FK/유효성 제약, 감사 이벤트 UPDATE/DELETE 트리거 차단, 이전 이벤트 해시 체인 및 현재 상태 대조. 관리자 `company:manage` 인증/로그아웃 차단, 로컬 Tkinter 탭 제공. 해시는 **로컬 무결성 확인 수단이지 외부 공격을 방어하는 디지털 서명은 아니다**.
- 소켓/DNS 차단 상태에서 관리자 GUI 생성 취소/저장/개정/검토/로그아웃 확인. 이메일, 웹 게시, 결제, 외부 서비스, 실제 상품 생성/판매 코드는 호출하지 않는다.

## 미완료/보류 (원본 요구사항 유지)

AI 상품/프로그램/콘텐츠 실제 제작, 자동 상품 등록·검수·배포, 외부 판매 페이지/가격 설정, 실제 출시 승인, 주문·결제·정산·고객 정보/환불, 실제 상품 전달 및 판매/매출 검증, Windows 실기기·EXE·실제 GGUF·장시간 자율 운영 통합 검증. 67단계는 **BLOCKED**이며 완전 완료 수 54/100에 더하지 않는다. **다음 개발 순번 68단계 ‘AI의 실제 상품·프로그램 제작’**으로 진행한다.

## 검증 및 알려진 한계

- `logs/targeted_pytest.txt`: 67단계+프로젝트 구조 **37 passed**.
- `logs/selected_regression_pytest.txt`: Stage55~67+프로젝트 구조 **319 passed**, 실패 0 (선택 회귀).
- `logs/gui67.txt`: Linux Xvfb 실제 Tkinter GUI 통과.
- `logs/offline_self_test.txt`: 소켓/DNS 차단 데스크톱 self-test 1명령 통과.
- `logs/offline_tail.txt`: Stage65~67 GUI 3명령 통과. **전체 72개 오프라인 명령을 실행한 것은 아님**.
- `logs/full_pytest_attempt.txt`: 단일 전체 pytest를 시도했으나 약 13% 진행 시 실행 시간 제약으로 중단. **전체 회귀 통과 아님**. 기존 Stage63 병렬 subprocess 실행시간 임계 실패는 해결/재검증하지 않았다.
- Linux Xvfb GUI는 Windows 실기기·Windows EXE 검증이 아니다.
- 원본 기획안 T01~T20 전체 제품 검증은 별도 미완료.
