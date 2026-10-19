# Stage 54 — 오프라인 지문 기록 재검사 안정성 개선

- 기준: `AIWACK_Stage54_Offline_Receipt_Stability_Continuation_Source.zip` (957개 파일)
- 실제 확인한 원본 문서: `docs/original_project_spec.txt`, `docs/requirements_traceability.md`, `docs/roadmap_100.csv`, `docs/roadmap_100.md`, `docs/progress.json`.
- 별도 기획안 첨부 텍스트의 직접 확인은 불가. ZIP에 보존된 원문 사용.
- 100단계 로드맵: **53/100 완료**, 54단계 인터넷 조사·자료 수집 **미완료**.

## 변경 사항

- `desktop/research_bundle_manifest.py`: 원본 파일 및 목록을 검사할 때 1차·2차 지문을 비교하며 검사 도중 변경·누락 시 일치 판정 거부. 기존 JSON 포맷 유지.
- `desktop/app.py`: 검사 중 변경 가능성에 대한 사용자 경고 추가.
- `tests/test_offline_research_receipt_reverification.py`: 정적 일치·기존 변경·검사 도중 원본/목록 변경·삭제·소켓 차단 테스트.
- `scripts/stage54_receipt_reverification_gui_smoke.py`: Linux Xvfb에서 실제 Tkinter 버튼 로그인/검사 중 파일 변경 주입 검사.
- `scripts/verify_offline_runtime.py`: 추가 GUI 스모크 검사 등록.

## 한계

- **원자적인 파일시스템 스냅샷은 아닙니다.** 두 검사 사이의 복구된 변경이나 마지막 검사 이후의 변경은 탐지 못할 수 있습니다.
- 자체 SHA-256은 전자서명·출처 신뢰 증명이 아닙니다. 로컬 데이터의 일관성 비교만 제공.
- 외부 서버, GitHub, 클라우드 모델, DNS/HTTP 요청은 사용하지 않음. 기존 SQLite 데이터와 원본 기획안은 변경하지 않음.
- Windows 실기기, Windows EXE, 실제 GGUF, 자율 장시간 동작·자동 웹 수집은 미검증/미구현.
- 실질 제품 완성도 약 **20~25%**: 기능별 인수시험이 아닌 주관적 추정.

## 실측 검증 결과

실측 로그와 파일별 해시 보존 기록을 이 디렉터리에 포함합니다. 시험 실패와 재시도는 숨기지 않습니다.

## 실제 테스트 결과 (2026-10-14)

- 신규 테스트 6개, 신규·기존 지문 기록 관련 pytest **20개 통과** (`related_pytest.log`).
- 전체 단일 pytest **1,295개 통과, 실패 0개, 135.65초** (`full_pytest.log`). Python 소켓/DNS 호출 차단 상태.
- 실제 Linux Xvfb GUI에서 로그인 후 지문 일치와 검사 중 원본 변경 경고 확인 (`gui_smoke.log`). 초기 GUI 검사는 로그인 직후 SQLite 인증 기록이 변경되는 특성을 반영하지 못해 실패했으며, 인증을 완료한 다음부터 SQLite 변경 여부를 비교하도록 테스트 스크립트를 수정한 뒤 통과함.
- 데스크톱 오프라인 실행 검사는 총 **56개 명령 통과** (`offline_runtime.log`), Python 컴파일 검사 통과.
- 이전 ZIP의 957개 파일 모두 보존, 그중 951개 바이트 동일, 기존 코드·문서 6개 변경. 원본 기획안·요구 추적표·CSV 로드맵·기존 SQLite 해시 불변 (`source_preservation.json`).
- Windows 실기기/EXE/GGUF/장시간 운용 및 실제 웹 자동 조사/수집은 검증하지 않았음. 54단계는 미완료.

## 별도 ZIP 압축 해제 재검증

- 첫 패키지를 새 폴더에 안전하게 압축 해제한 후 관련 pytest 20개 통과 (`reextract_related_pytest.log`).
- 해당 압축 해제본의 실제 Tkinter GUI 재검사 통과 (`reextract_gui_smoke.log`).
- 최종 ZIP은 로그 파일을 포함한 후 다시 생성했으며 CRC 및 파일 SHA-256을 검증했습니다.
