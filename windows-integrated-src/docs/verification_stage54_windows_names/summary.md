# AIWACK 54단계 — 오프라인 Windows 호환 자료 묶음 파일명 검증 (부분 개발)

## 실제 기준 및 불변 사항
- 입력 누적 소스: `AIWACK_Stage54_Offline_Manifest_Stability_Continuation_Source.zip` (999개 파일, ZIP CRC 확인).
- 검토한 문서: `docs/original_project_spec.txt`, `docs/requirements_traceability.md`, `docs/roadmap_100.csv`, `docs/roadmap_100.md`, `docs/progress.json`.
- 기존 1~53단계 완료, 54단계 인터넷 조사·자료 수집 진행 중. **54단계 완료 처리하지 않음**.
- 원본 기획안·추적표·로드맵·SQLite 데이터 SHA-256 변경 없음.

## 변경된 실제 코드
- `desktop/research_captures.py`: 모든 플랫폼에서 Windows에서 문제가 되는 자료 묶음 파일 이름을 사전 검증. JSON 목록 읽기에서 대소문자만 다른 파일명과 목록 파일명 충돌 차단.
- `desktop/research_bundle_manifest.py`: JSON 목록 생성, 자료 묶음 파일 지문 저장·재검사에도 같은 이름 규칙 적용. Windows 예약 장치명·금지 문자·끝 공백/마침표, 대소문자만 다른 충돌 거부.
- `tests/test_offline_research_windows_bundle_names.py`: 수동 작성 목록, 지문 기록, GUI 간접 경로, 정상 한국어/Unicode 파일명 등의 신규 테스트 32개.
- `scripts/stage54_windows_names_gui_smoke.py`: Linux Xvfb 실제 Tkinter 버튼으로 Windows 예약 이름 거부/정상 목록 생성 및 SQLite 불변 확인.
- `scripts/verify_offline_runtime.py`: 신규 실제 GUI 검사 포함.
- `README.md`, `docs/progress.json`: 이전 로드맵 완료 수치 보존하며 부분 구현 사실 기록.

## 검증
- 단일 전체 pytest: **1,332 passed, 0 failed**, 127.28초. 기록 `full_pytest.log`.
- 신규 pytest: **32 passed**. 기록 `targeted_pytest.log`.
- 소켓·DNS 차단 관련 pytest: **66 passed**, GUI 검사 통과. 기록 `network_blocked_checks.log`.
- Tkinter: **Linux Xvfb 통과**. 기록 `gui_smoke.log`.
- 오프라인 데스크톱·Tkinter 검사: **58개 명령 통과** (Python 소켓·DNS 차단). `offline_runtime.log`.
- Python 컴파일: 통과, `compileall.log`.
- ZIP 예비본을 별도 폴더에 압축 해제한 뒤 Python 소켓·DNS 차단 환경에서 관련 pytest **98개 통과**, 실제 Tkinter GUI 검사 통과. `reextract_checks.log`.
- 기존 ZIP 999개 파일 모두 유지, 그중 994개 바이트 단위 동일, 변경된 기존 파일 5개. 상세 `preservation.json`.

## 제한 및 오해 방지
- Windows 실기기 실행·EXE 빌드·실제 GGUF 모델 추론·장시간 자율 운영 **미검증**.
- Python 네트워크 호출 차단은 OS 전체 통신 차단을 증명하지 않음.
- 파일명 충돌에 대한 보수적 정적 규칙이며 모든 Windows 파일시스템/로캘 동작을 완전히 증명하는 검사는 아님.
- 웹 출처는 사용자가 제공한 주장이고 자동 인터넷 조사·수집은 **미구현**. SHA-256은 출처 인증이나 전자서명이 아님.
- 전체 로드맵 진행 53/100 = 53%, 제품 실질 완성도 약 20~25%는 미검증 주관적 추정.
