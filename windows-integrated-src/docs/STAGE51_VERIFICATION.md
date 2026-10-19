# AIWACK Stage51 — AI 작업 도구 등록 시스템

## 기준과 실제 변경

- 기준: `AIWACK_Stage50_Local_Offline_Source.zip`. `docs/progress.json`에서 1~50단계 완료, 다음 51단계 확인.
- 51/100 로드맵 기록, 다음 52단계 `도구 실행 권한 및 승인 검사`. 버전 `0.1.43`.
- `desktop/tool_registry.py`: 앱 내에서 실행되지 않는 로컬 SQLite 도구 *메타데이터* 등록부. 12개 종류, 유효성 검사, 고유 키, 명시적 요구 권한 라벨, 등록·보관 이력, 직접 수정·삭제 차단 트리거.
- `desktop/storage.py`: 기존 소유자 로그인·`company:manage` 권한 검사 API. 등록·보관은 `BEGIN IMMEDIATE` 트랜잭션으로 처리.
- `desktop/app.py`: 실제 Tkinter `AI 작업 도구 등록` 탭, 등록/목록/보관/새로고침 버튼.
- `tests/test_tool_registry.py`: 자격 검사, 유효성, 중복, 동시 접근, 트리거, 로그아웃, 재시작, 오프라인 처리 테스트 27개.
- `scripts/stage51_offline_gui_smoke.py`: 실제 GUI 버튼으로 등록, 중복 차단, 보관, 재로그인 후 감사 이력 검증.

## 실제 검증 (Linux, 2026-10-13)

- `python -m pytest -q`: **645 passed in 75.76s**. `docs/STAGE51_FULL_PYTEST.log`.
- `python -m pytest -q tests/test_tool_registry.py`: **27 passed**.
- 신규/관련 회귀 묶음: **123 passed** (tool_registry, performance_reviews, employee_access, company_knowledge, knowledge_access, admin_sections).
- `python -m compileall -q desktop scripts tests`: 통과.
- `xvfb-run -a python scripts/stage51_offline_gui_smoke.py`: 통과.
- `python scripts/verify_offline_runtime.py`: **19/19개 명령 통과**, Python 소켓 연결 차단 및 Linux Xvfb GUI 실행 검사. `docs/STAGE51_OFFLINE_SMOKE.log`.
- 기존 누적 ZIP의 **215개 파일 모두 보존**. 의도적 수정 파일 8개 이외 207개 파일은 SHA-256 바이트 수준으로 동일. 원본 기획서와 포함된 SQLite 데이터 파일도 동일.
- 기존 SQLite 파일 복사본에 새 스키마가 정상 추가되었고 기존 데이터는 삭제되지 않음을 확인.
- ZIP CRC 검사: 최종 패키징 후 확인.

## 검증하지 않은 기능과 주의사항

- 도구 등록은 **도구 실행기 또는 외부 서비스 연결이 아님**. 등록 상태 `registered`는 실제 도구를 사용할 수 있다는 뜻이 아님.
- 필요한 직원 권한은 **설명용 요구 권한**만 저장하며, 직원의 기존 권한을 자동 변경하지 않음. 실행 권한·승인 정책은 52단계 이후 별도 구현 대상.
- 등록된 분류 중 웹·상거래 등은 메타데이터 분류일 뿐 네트워크 또는 결제 기능을 구현한 것이 아님.
- 실제 Windows 10/11 컴퓨터·설치형 EXE·실제 GGUF 모델 추론은 시험하지 않음.
- Python 소켓 차단은 회귀 검사 장치이지 OS 수준 방화벽이 아님.
- 로컬 SQLite는 암호화되지 않으며 운영체제에서 파일을 직접 수정할 수 있음. 앱 내부 트리거는 악의적 OS 관리자를 막는 수단이 아님.
- 실질 제품 완성도는 **약 19~24% (주관적 추정)**. 로드맵 51%와 독립적인 값이며, 실제 자율 사업 운영·판매·결제·무인 운영은 미완성.
- 이번 개발에서는 GitHub, 외부 서버, 클라우드 AI API를 사용하지 않았음.
