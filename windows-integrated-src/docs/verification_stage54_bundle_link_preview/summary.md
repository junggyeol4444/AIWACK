# AIWACK 54단계 오프라인 HTML 링크 등록 전 분류 — 부분 개발 기록

## 기준 문서와 진행 상태

- 입력 누적 소스: `AIWACK_Stage54_Offline_Bundle_URL_Preapproval_Verified_Source.zip` (647개 파일).
- 입력 ZIP 내부 `docs/original_project_spec.txt`, `docs/requirements_traceability.md`, `docs/roadmap_100.csv`, `docs/roadmap_100.md`, `docs/progress.json` 확인.
- 별도 독립 원본 기획안 첨부 텍스트는 이번 환경에서 접근하지 못함. ZIP 안의 원본 문서 변경 없음.
- 원본 로드맵 54단계: **인터넷 조사 및 자료 수집**. 외부 서버 접속 금지이므로 미완료, **53/100 완료 / 54 진행 중** 유지.

## 실제 신규 작업

- `desktop/research_captures.py`: 로컬 HTML 본문의 비활성 `<a href>`를 이용해 등록 *전* 링크 대상에 대응하는 로컬 후보를 찾음. HTML마다 최대 100개, 묶음 최대 20개, 예시 항목당 최대 5개.
- 링크 상태: 현재 묶음에 주장 URL 일치 자료 존재 / 기존 SQLite 활성 자료 존재 / 기존 SQLite 보관 자료만 존재 / 등록된 자료 없음. 후보 자료 ID/묶음 순번은 최대 3개만 예시로 제공.
- 사용자 승인 전 읽기 스냅샷에서 분류하고, 승인 토큰에 HTML 링크 대상의 등록/보관 상태를 포함함. 승인 화면이 열린 동안 그 상태가 바뀌면 등록 거부 후 재검토. 무관한 조사 자료 추가는 승인 무효화하지 않음.
- `desktop/app.py`: Tkinter 사전 검토 화면에 범주별 전체 건수와 자료별 예시를 표시. 미등록 로컬 링크가 존재할 때 승인 대화상자에도 경고.
- `scripts/stage54_bundle_link_preview_gui_smoke.py`: Xvfb 실제 버튼 클릭 검사; `scripts/verify_offline_runtime.py`에 신규 GUI 검사 등록.
- `tests/test_offline_research_bundle_html_links_preview.py`: 네트워크 차단, 중복, 경고, 승인 변경, 보관 상태, 상한 및 권한 검증.

## 제한 및 보존

- 링크 문자열 일치 = 외부 웹 링크 작동/웹사이트 신뢰성/자료 출처 진위 검증 아님.
- 네트워크·DNS 조회·클라우드 AI 호출·GitHub 조작 없음. SQLite 스키마 변경 없음.
- Windows 10/11 실기기, Windows EXE, GGUF 실제 추론, 장시간 자율 운영은 검증하지 않음.
- Python 네트워크 함수 차단 테스트는 OS 전체 방화벽 검증은 아님.
- 실질 제품 완성도 약 20~25%는 주관적 추정으로, 로드맵 완료율 53%와 별개임.

## 실제 검사 기록

테스트 로그, 종료 코드, 원본 SHA-256 확인 결과는 같은 폴더의 별도 파일에 기록함. 실패 또는 미완료는 성공으로 기재하지 않음.

### 실제 실행 완료 기록 (2026-10-14, Asia/Seoul)

- 전체 pytest 단일 실행: **1,169 통과 · 0 실패**, 137.92초 (`full_pytest.log`, exit 0).
- 신규 테스트 파일: **9건**; 신규/관련 4개 테스트 파일 **60건 통과** (`related_pytest.log`, exit 0).
- 실제 Tkinter GUI: Linux Xvfb에서 로그인, HTML 링크 집계 표시, 취소 시 DB 불변, 명시적 승인 후 등록 통과 (`gui_smoke.log`, exit 0).
- Python 컴파일 검사 통과 (`compileall.exit` 0).
- `scripts/verify_offline_runtime.py`: Python 소켓/DNS 함수 차단 하에서 **46개 명령 통과** (`offline_runtime.log`, exit 0).
- 최종 소스와 동일한 코드의 예비 ZIP을 별도 디렉터리에 압축 해제한 후 관련 pytest **60건 통과** 및 Tkinter GUI 검사 통과 (`reextract_related_pytest.log`, `reextract_gui.log`). 예비 ZIP CRC 통과.
- 기존 누적 ZIP의 647개 파일 모두 유지, 641개 바이트 단위 일치, 기존 파일 6개 변경. 원본 기획안, 요구사항 추적표, 100단계 CSV 및 기존 SQLite 데이터 SHA-256 불변 (`source_preservation.json`).
- Windows 실기기, EXE, 실제 GGUF 모델, 장시간 무인 자율 운영 및 웹 자동 수집 **미검증/미구현**.
