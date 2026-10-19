# Stage54 — 오프라인 자료 묶음 목록 생성 시점 일관성 검증 (부분 개발)

- 기준: 최신 `AIWACK_Stage54_Offline_Receipt_Reverification_Continuation_Source.zip` (978개 파일).
- 원본 검토: `docs/original_project_spec.txt`, `docs/requirements_traceability.md`, `docs/roadmap_100.csv`, `docs/roadmap_100.md`, `docs/progress.json`.
- 구현: `desktop/research_bundle_manifest.py`가 최초 파일별 SHA-256/크기를 생성한 뒤 목록 파일을 만들기 전에 **각 파일을 재판독**. 변형·삭제·심볼릭 링크 변경 시 저장 거부.
- 새로운 pytest: `tests/test_offline_research_manifest_stability.py` (정상, 중간 변경, 삭제, 링크 대체, 덮어쓰기/소켓 차단).
- Tkinter 검사: `scripts/stage54_manifest_stability_gui_smoke.py` — 원본 변경으로 저장 거부, 수정된 파일을 기준으로 다시 승인하면 새 목록 생성, 승인 전 SQLite 자료 등록 없음.
- 한계: 두 번 읽기 역시 원자적 스냅샷이 아니며 검사 직후 변경 가능. 실제 출처 검증·웹 자동 수집·Windows 실기기/EXE/GGUF 검증이 아님.
- 진행률: 로드맵 53/100 완료, 54단계 미완료. 제품 완성도 20~25%는 **미검증 주관적 추정**.

## 실제 검증 기록

실행 로그는 같은 폴더의 파일을 참고. 이번 실행에서 확인하지 못한 항목은 성공으로 기록하지 않음.

| 확인 항목 | 실제 결과 |
|---|---|
| pytest 단일 전체 | **1,300 통과**, 실패 0, 124.39초 (이 실행 자체는 소켓 차단 없이 로컬 실행) |
| 신규·관련 pytest | **45 통과** (전체 1,300건에 포함, 별도 중복 합산하지 않음) |
| 신규·관련 pytest 소켓·DNS 차단 | **45 통과** (별도 재실행) |
| 실제 Tkinter GUI | **Linux Xvfb 통과** (파일 변경 중 저장 거부·정상 재시도) |
| 오프라인 데스크톱·GUI 검사 | **57명령 통과**, `sitecustomize.py`로 Python 소켓·DNS 차단 |
| Python 컴파일 검사 | 통과 |
| 기존 원본 기획안 및 SQLite | SHA-256 불변 |

**검사 한계:** Windows 10/11 실기기, Windows EXE 빌드, GGUF 추론, 장시간 자율 운영, 실제 인터넷 수집 검증 없음. Python 네트워크 API 차단은 OS 차원의 통신 차단을 입증하지 않음. 간헐적 병렬 작업의 시간 제한 위험은 별도 근본 해결하지 않음.

- 예비 ZIP 별도 압축 해제 후 소켓·DNS 차단 pytest 45개 통과, Tkinter GUI 통과. 로그는 `reextract_*` 참조.
