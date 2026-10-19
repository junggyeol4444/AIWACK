# 68단계 — AI의 실제 상품·프로그램 제작 (오프라인 부분 구현)

원본 `docs/original_project_spec.txt` 제4.4절은 **기획만이 아닌 실제 상품/프로그램의 AI 제작과 운영**을 요구한다. `docs/requirements_traceability.md` R06 및 T10, 로드맵 68번의 원본 완료 조건을 축소하지 않는다. 실제 GGUF 모델·상품 제작/실행 도구·Windows 실기기 부재로 완전 구현/검증하지 못했다. Stage68은 **BLOCKED**, 완료 개수는 **54/100** 유지.

## 실제 구현 및 제한

- Stage67 카탈로그의 감사 체인 검증 후 **관리자가 직접** 정적 HTML 미리보기 시제품을 생성한다. 이것은 **AI 제작 상품/작동 프로그램이 아니다**. 등록된 이름·설명·제공 계획·미검증 가격 가정을 HTML 이스케이프한 로컬 읽기용 페이지로 표현하는 실제 `.html` 파일이다.
- `default-src 'none'` CSP를 포함하고, 사용자 제공 코드·HTML은 실행하지 않는다. 브라우저를 자동 실행하거나 외부 주소·서버에 접속하지 않는다. 출력 파일은 SQLite 파일의 형제 디렉터리 `stage68_local_prototypes` 안에 임의 고정 형식 이름으로 독점 생성한다. 외부 입력 파일 경로를 허용하지 않는다.
- 파일 크기 상한 64 KiB, SHA-256 및 바이트 크기 재검사, 파일·상위 폴더 심볼릭 링크 거부, 카탈로그 원본 버전/해시 스냅샷을 보관한다. 카탈로그 수정 후 이전 시제품은 `catalog_changed_since_build=True`로 표시하고 새 검토 요청을 차단한다.
- SQLite FK, 추가 전용 감사 이벤트, 스냅샷 해시 체인, 상태 변경 이력 및 상태 무결성 검사. 관리자 `company:manage` 로그인 권한, Tkinter 별도 탭에서 생성 취소/생성/재검사/수동 검토 요청/철회/로그아웃 검증. `review_requested`는 **품질 검수 합격이나 출시 승인 아님**.
- `prototype → review_requested/withdrawn`, `review_requested → withdrawn`만 가능하며 출시/판매/배포/결제 상태와 실행 API는 없다. HTML은 배포 가능한 서비스/완제품이 아니며 AI가 만든 결과물로 표시하지 않는다.
- SHA-256 해시 체인은 로컬 변조 탐지이며 OS 수준 파일 보안이나 외부 서명이 아니다. 악의적 로컬 관리자/파일시스템 조작을 방지하지 않는다.

## 검증

- `logs/new_tests.txt`: 신규 Stage68 27 passed.
- `logs/targeted_pytest.txt`: Stage68+구조 32 passed.
- `logs/regression55_60.txt`: Stage55~60 125 passed.
- `logs/regression61_68.txt`: Stage61~68+구조 221 passed. **비중복 선택 회귀 총 346 passed, 0 failed**.
- `logs/selected_regression_pytest.txt`: 첫 단일 선택 회귀 시도는 시간 제한 중단(약 70% 진행). 이후 위 두 분할 검사에서 전체 선택 범위 재실행 통과. **전체 프로젝트 pytest가 통과한 것은 아님**.
- `logs/gui68.txt`: Linux Xvfb 실제 Tkinter 68단계 GUI 통과.
- `logs/offline_self_test.txt`와 `logs/offline_tail.txt`: 소켓·DNS 차단 self-test 1 + Stage65~68 GUI 4 = **5 명령 통과**. 전체 73개 오프라인 명령은 실행하지 않았다.
- 최종 ZIP 압축 해제본 검사 결과는 `logs/final_extracted_pytest.txt` 및 `logs/final_extracted_gui.txt` 참고.
- 기존 Stage63 병렬 subprocess 실행시간 임계 테스트 실패 이력은 해결/재검증하지 않았다.
- Windows 실기기·EXE·실제 GGUF 모델·실제 상품 제작/품질/배포/판매·장시간 자율 운영 및 T01~T20 통합 검증은 미실행.

## 보류 및 다음 순번

실제 모델 기반 AI 상품/프로그램 제작, 안전한 임의 코드 실행, 품질 검증, 상품 운영·출시·결제 및 Windows 검증은 보류. **다음 원본 69단계 '상품 검수 및 출시 승인'**으로 이동한다. 이 단계도 외부 승인/실기기가 필요하면 로컬 가능한 범위만 구현하고 보류한다.
