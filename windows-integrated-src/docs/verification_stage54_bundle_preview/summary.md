# AIWACK Stage54 계속 개발 — 로컬 묶음 사전 검토 및 변경 방지

## 기준과 원본 보존

- 입력 원본: `AIWACK_Stage54_Offline_File_Custody_Continuation_Source.zip` (562개 파일), 이전 단계 1~53 완료, 54단계 인터넷 조사·자료 수집 진행 중.
- 최신 ZIP 내부의 `docs/original_project_spec.txt`, `docs/requirements_traceability.md`, `docs/roadmap_100.csv`, `docs/roadmap_100.md`, `docs/progress.json`를 실제 확인했다. 독립적으로 첨부된 원본 기획서 텍스트는 이용할 수 없어 ZIP에 저장된 원본 문서를 기준으로 했다.
- **원본 기획안, 요구사항 추적표, 로드맵 CSV, `dev_company.sqlite3`의 SHA-256을 원본과 일치하게 보존**했다. 기존 테이블과 데이터 변경 없음. 모든 기존 파일 유지, 상세 해시 비교 `source_preservation.txt`.

## 실제 코드 변경

- `desktop/research_captures.py`: 로컬 JSON 묶음 사전 검토, 1~20개 로컬 자료의 추출 본문 해시와 원본 파일 바이트 해시 확인, 기존 활성/보관 자료 및 묶음 내부의 같은 주장 URL·동일 본문 중복 조사. 검토용 묶음 SHA-256 표식 생성. 검토 후 승인한 내용과 로컬 파일/목록이 달라졌을 때 등록 거부.
- `desktop/storage.py`: 관리자 권한으로 읽기 전용 `preview_offline_research_bundle` API, 검사 토큰을 전달하는 `import_offline_research_bundle` 옵션 추가. 기존 직접 로컬 일괄 가져오기 API의 호환성 보존.
- `desktop/app.py`: `자료 묶음(JSON) 가져오기`가 즉시 저장하지 않고 **사전 검토 내용을 표시한 뒤 사용자 확인을 받고** SQLite에 일괄 저장. 중복은 확인 전 차단, 취소 시 저장 없음, 검토 후 파일 변경 발견 시 등록 거부.
- `tests/test_offline_research_bundle_preview.py` 신규 24개 테스트: 내용/원본 해시, 보관 자료 포함 중복 검사, 같은 URL의 서로 다른 버전 허용, 검토 후 파일/목록 변경 차단, 토큰 형식 오류, 승인 직전 DB 중복 생성 시 트랜잭션 롤백, 관리자 인증, 재로그인, 로컬 경로/심볼릭 링크 거부, 소켓 및 DNS 차단.
- `scripts/stage54_bundle_preview_gui_smoke.py`: Linux Xvfb에서 로그인, 승인 취소, 승인 창에서 파일 교체, 정상 등록, 중복 차단 등 실제 Tkinter 버튼 검증. 기존 배치 GUI 스모크는 새 확인 대화상자 테스트에 맞춰 갱신.
- `scripts/verify_offline_runtime.py`: 신규 GUI 스모크를 오프라인 소켓 차단 검사 목록에 편입.

## 실제 검증

- 신규 pytest: **24/24 통과** (`new_tests.log`). 기존 묶음 테스트까지 **42/42 통과** (실행 화면 기록).
- **전체 pytest 단일 실행: 1,088개 통과, 0 실패, 128.53초** (`full_pytest_retry.log`, `full_pytest_retry.exit`). 최초 전체 실행은 환경의 단일 도구 호출 제한으로 약 20% 시점에서 중단됨(`full_pytest.log`); 두 번째 전체 실행은 완료됨.
- Linux Xvfb 기존 및 신규 Tkinter GUI 스모크 실행 종료 코드 0 (`gui_smoke.log`). Python 소켓·DNS 함수를 막은 상태에서 성공.
- **소켓과 DNS 호출을 막은 오프라인 실행 검사 40개 명령 통과, exit=0** (`offline_runtime.log`, `offline_runtime.exit`). 기존 39개 검사에 신규 실제 Tkinter GUI 검사를 추가함. Python 계층 소켓 차단이며 OS 방화벽·모든 외부 연결 가능성의 입증은 아님.
- 컴파일 검사 성공(`compileall.log`).
- 실제 Windows GUI/EXE/Windows 네트워크 드라이브 교체 위험, 실제 GGUF 추론, 24시간 자율 실행, 인터넷 조사/자동 수집은 **미검증·미구현**.
- 사전 검토와 등록의 SHA-256 비교는 **무키 동일성 검사**일 뿐 승인 서명이나 웹 출처 인증이 아님. `source_url`은 사용자가 입력한 주장이다. 다른 프로세스의 동시 등록은 SQLite UNIQUE 제약을 통해 최종적으로 롤백되지만 사전 검토 자체가 등록을 예약하지는 않는다.

## 현재 단계

- 전체 100단계 중 **53단계 완료(53%)**. **54단계 진행 중**: 외부 서버 접속 금지로 원래 목표인 인터넷 자동 자료 수집을 완료로 표시하지 않음. 55단계 미착수.
- 실질 제품 완성도 **약 20~25% (주관적 추정)**. 이는 테스트 수와 다른 척도이며 원본 기획의 실제 AI 회사 운영 구현 정도에 대한 보수적 추정임.
- 각 실행은 독립적이며 1시간 실행 시간을 보장하지 않음. 사용자 PC 접근, 유료 가입, 환경 설치·변경, GitHub 또는 외부 서버 연결 없음.
