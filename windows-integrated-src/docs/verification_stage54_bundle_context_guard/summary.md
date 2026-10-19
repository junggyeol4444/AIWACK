# AIWACK 54단계 부분 개발 — 로컬 묶음 승인 시 관련 SQLite 자료 변경 감지

## 개발 기준·완료 조건

- 기준: `AIWACK_Stage54_Offline_Bundle_Provenance_Continuation_Source.zip` (기존 604개 파일).
- 누적 소스의 `docs/original_project_spec.txt`, `docs/requirements_traceability.md`, `docs/roadmap_100.csv`, `docs/roadmap_100.md`, `docs/progress.json`을 실제 읽고 진행함. 별도의 원본 기획안 첨부 원문은 이 실행에서 독립 검증하지 못함.
- **완료 53/100, 진행 중 54**: 원본의 54단계 '인터넷 조사 및 자료 수집' 완료 조건을 낮추거나 완료 표시하지 않음. GitHub·외부 서버·클라우드 AI를 이용하지 않음.

## 실제 코드 변경

- `desktop/research_captures.py`: 최대 20개 명시적 로컬 묶음의 주장 URL 또는 본문 SHA-256에 대응하는 기존 SQLite 자료 ID·URL·본문 해시의 읽기 전용 지문 계산. 파일·목록 승인 토큰에 이 지문도 결합. 완전 중복은 기존 방식대로 차단하고, 검토 이후 새 관련 자료가 추가되면 **재검토 후 새 승인**을 요구.
- `desktop/storage.py`: 사전 검토의 기존 자료 비교·승인 토큰 계산을 하나의 일관된 SQLite 읽기 트랜잭션으로 수행. 실제 등록은 기존 `BEGIN IMMEDIATE`와 롤백 유지.
- `desktop/app.py`: 사전 검토 후 관련 SQLite 자료가 바뀌어도 가져오기를 거부할 수 있음을 GUI에서 설명.
- `tests/test_offline_research_bundle_context_guard.py`: 신규 11개, 동종/이종 출처 변경·무관 자료·보관 상태·완전 중복·사전 검토 읽기 전용·권한 검사·오프라인 검증.
- `scripts/stage54_bundle_context_gui_smoke.py`: Linux Xvfb 실제 GUI에서 승인 창이 열린 사이 새 동일 URL·다른 본문 자료 등록을 재현, 기존 승인 거부/재검토/재승인 검증.
- `scripts/verify_offline_runtime.py`: 신규 GUI 검사를 기존 오프라인 실행 검사 묶음에 추가.
- 기존 SQLite 테이블 변경·수정/삭제·마이그레이션 없음. 독립적인 URL 출처 인증이나 디지털 서명 아님.

## 검증

- 전체 pytest **단일 실행 1,131개 통과, 실패 0개 (129.86초)** — `full_pytest.log`; Python 프로세스에서 소켓·DNS 함수 차단 후 실행.
- 관련 pytest **67개 통과** — `related_pytest.log`.
- 실제 Tkinter GUI 재검사 통과 — `gui_smoke.log`, Linux Xvfb 사용.
- Python 컴파일 검사 통과 — `compileall.log`.
- 기존 604개 파일 전부 유지, 597개 바이트 동일 및 기존 7개 수정 — `source_preservation.json` (이 문서 추가 이전 비교).
- Python 소켓·DNS 함수 차단 오프라인 실행 검사 **43개 명령 모두 통과** — `offline_runtime.log` (기존 42개 + 새 GUI 검사 1개).
- 전체 누적 ZIP 별도 폴더 재압축 해제 후 관련 pytest **67개 통과** — `reextracted_related_pytest.log`.
- 재압축 해제한 누적 ZIP에서 실제 Tkinter GUI **통과** — `reextracted_gui.log`.
- 최종 ZIP 무결성 검사 및 원본 보존 보고서는 사용자에게 제공한 별도 검증 파일 참조.

## 제한

- 실제 웹사이트 탐색, 인터넷 자동 자료 수집, DNS·HTTP 요청 없음. 입력 URL은 관리자의 검증되지 않은 주장임.
- Python 소켓·DNS 차단은 운영체제 방화벽/모든 네트워크 가능성에 대한 증명이 아님.
- Windows 10/11 실기기·Windows EXE 빌드·실제 GGUF 추론·장시간 자율 운영 미검증.
- 실질 제품 완성도 20~25%는 기존 주관적 추정으로, 테스트 통과율이나 100단계 로드맵 완료율과 다름.
