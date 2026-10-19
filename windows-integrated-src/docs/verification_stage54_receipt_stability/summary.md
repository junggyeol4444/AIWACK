# AIWACK 54단계 부분 구현 — 로컬 묶음 지문 기록 생성 시 변경 감지

## 기준 및 원본 보존

- 실제 사용한 최신 소스: `AIWACK_Stage54_Offline_Bundle_Custody_Receipt_Continuation_Source.zip` (947개 파일; CRC 정상).
- 실제 확인한 기획·추적·로드맵·상태: `docs/original_project_spec.txt`, `docs/requirements_traceability.md`, `docs/roadmap_100.csv`, `docs/roadmap_100.md`, `docs/progress.json`.
- 별도 첨부 원본 텍스트는 직접 접근하지 못하여 ZIP 안의 원문 사용.
- 원본 CSV 로드맵 기준 **1~53 완료, 54 진행 중**. 54단계 완료 조건인 실제 인터넷 조사·자동 자료 수집은 구현하지 않음.
- 실질 제품 완성도 **약 20~25%**는 경험적·주관적 추정으로 계량 평가가 아님.

## 이번 구현

- `desktop/research_bundle_manifest.py`: 기존 로컬 묶음 지문 기록 생성에서 JSON 목록과 최대 20개 원본 자료 파일을 모두 최초 검사한 뒤 **저장 직전 다시 검사**. 목록 해시/항목이나 원본 파일 SHA-256/크기의 변경·파일 누락·검사 실패를 감지하면 `ValueError`와 함께 지문 기록 JSON 생성을 거부.
- `tests/test_offline_research_bundle_receipts.py`: 목록 변경, 이미 검사한 파일 내용 변경, 원본 삭제, 변경 없는 원본 두 번 읽기 검증 4개 추가.
- `scripts/stage54_bundle_receipt_gui_smoke.py`: 실제 Tkinter 버튼에서 검사 도중 원본 변경 주입 및 JSON 생성 거부 검증 추가.
- `README.md`, `docs/roadmap_100.md`, `docs/progress.json`: 완료 수치와 제한 조건 유지, 신규 검사 기록.
- 기존 Tkinter·SQLite 구조와 SQLite 파일 변경 없음; 외부 서버·GitHub·DNS·클라우드 API 이용 없음.

## 실제 검사

- 관련 pytest: **34개 통과** (`related_pytest.log`).
- 전체 pytest **단일 실행**: **1289개 통과, 실패 0개, 132.42초**, Python 소켓·DNS 차단 환경 (`full_pytest.log`).
- Linux Xvfb 실제 Tkinter 로그인·취소·기록 생성·재검사·동시 변경 거부: **통과** (`gui_smoke.log`).
- 예비 누적 ZIP 별도 압축 해제본에서 관련 pytest **34개 통과**, 실제 Tkinter **통과** (`reextract_related_pytest.log`, `reextract_gui_smoke.log`).
- `python -m compileall -q desktop scripts tests`: 통과 (`compileall.log`).
- 입력 ZIP 파일 경로 **947개 전부 보존**, 941개 해시 동일, 기존 코드·문서 6개 의도적으로 수정 (`source_preservation.json`).
- 보호 파일: 원본 기획안, 요구사항 추적표, 로드맵 CSV, 기존 SQLite 파일 모두 SHA-256 동일.

## 정직한 제한

- 재검사는 **쓰기 직전 최선 노력 검사**이며 파일시스템 전체의 원자적 스냅샷이나 서명/출처 진위 인증이 아님. 최종 검사 직후 바이트가 바뀔 가능성은 운영체제 전반의 잠금 기능 없이 완전히 제거할 수 없음.
- Python 소켓/DNS 호출 차단 테스트는 OS 수준의 방화벽이나 모든 서브프로세스/네이티브 라이브러리 통신 차단 증명이 아님.
- Windows 10/11 실기기, EXE 빌드, GGUF 로컬 모델 추론, 장시간 자동 운용, 웹 자동 수집은 검사/구현하지 않음.
- **54단계 미완료**, 이전 **53/100 완료 상태**를 유지. 다음 단계(55) 착수하지 않음.

## 오프라인 실행 전수 검사

- `PYTHONPATH=<network-blocker>:<source> python -m scripts.verify_offline_runtime`
- 소켓 및 DNS 호출 차단 하의 실행 목록 총 **55개 명령 모두 통과**.
- 최종 출력 `PASS: desktop tests completed without a network connection` (`offline_runtime.log`).
- 실제 GUI는 Linux Xvfb; Windows 실기기 아님.
