# 54단계 부분 구현 — 등록 전 오프라인 자료 묶음 바이트 지문 기록

## 기존 요구사항/진행 상태
- 출처 ZIP: `AIWACK_Stage54_Offline_Inline_CSS_Preapproval_Continuation_Source.zip`.
- 실제 확인: `docs/original_project_spec.txt`, `docs/requirements_traceability.md`, `docs/roadmap_100.csv`, `docs/roadmap_100.md`, `docs/progress.json`.
- 원래 100단계 완료 수 **53/100**, 54단계 인터넷 조사 및 자료 수집은 **미완료**. 금지된 외부 접속을 수행하지 않음.
- 실질 제품 완성도 추정 약 **20~25%** (계량 검증 없는 주관적 평가).

## 실제 변경
- `desktop/research_bundle_manifest.py`: 사용자 지정 로컬 JSON 묶음 목록 및 최대 20개 텍스트/HTML 파일의 SHA-256과 바이트 크기를 별도 자가 체크섬 JSON으로 보존; 다시 열어 목록 변경/누락과 파일 변경/읽기 불가를 구분.
- `desktop/storage.py`: 소유자 관리자 권한 검사를 적용한 읽기/저장 API 연결. SQLite 데이터·스키마에 변화 없음.
- `desktop/app.py`: Tkinter 파일 지문 기록 저장·재검사 버튼. 승인이 있어야 기록 파일을 만들며 실제 자료 등록은 실행하지 않음.
- `tests/test_offline_research_bundle_receipts.py`: 정상 동작, 손상/누락, 문서 변조, 잘못된 경로, 네트워크 금지, 사용자 인증 검증.
- `scripts/stage54_bundle_receipt_gui_smoke.py`: Xvfb 실제 버튼 조작, 취소/생성/정상/변경, 소켓/DNS 호출 금지.
- 기존 Windows 오프라인 Tkinter·SQLite 구조 및 사용자 자료 보존. 기록 파일 SHA-256은 전자서명·웹 출처 인증을 제공하지 않음.

## 검증
- 관련 pytest 30개 통과 (`related_pytest.log`).
- 전체 pytest 단일 실행 시도는 실행 환경 시간 제한으로 조기에 종료 (`single_full_attempt_incomplete.log`), **전체 단일 실행 통과 주장 없음**.
- 전체 테스트 파일 85개를 17개 서로 다른 그룹으로 실행: **1285개 통과**, 건너뜀 0개; 실패 그룹 0개 (`group_results.json`, `group_*.log`).
- Python 소켓/DNS 차단 런타임 검사: 종료 코드 0, 완료 확인 명령 55개 (`offline_runtime.log`). OS 전역 네트워크 차단 증명 아님.
- Linux Xvfb Tkinter 조작 통과. Windows 실기기 및 EXE, GGUF 모델 추론·장시간 연속 운영·인터넷 자동 조사는 미검증/미구현.
- 기존 918개 파일 모두 경로 보존: 해시 동일 911개, 의도적으로 수정 7개. 원본 기획안/요구사항/CSV 로드맵/SQLite 바이트 동일.
