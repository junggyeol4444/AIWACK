# AIWACK 54단계 부분 개발 — 묶음 가져오기 전 출처·버전 차이 경고

## 원본 기준 / 단계 유지

- 입력: `AIWACK_Stage54_Offline_Manifest_Builder_Continuation_Source.zip` (590개 파일; ZIP CRC 검사 통과).
- 누적 ZIP의 `docs/original_project_spec.txt`, `docs/requirements_traceability.md`, `docs/roadmap_100.csv`, `docs/roadmap_100.md`, `docs/progress.json`을 읽고 작업함. 독립적으로 첨부된 원본 기획서 텍스트는 본 실행에서 별도 확인되지 않음.
- 원본 제6장 도구·정보 수집 목적과 로드맵 54단계 **인터넷 조사 및 자료 수집**을 그대로 유지함. 원격 자동 조사/자료 다운로드 기능은 구현·검증하지 않았음. 완료 **53/100**, 54단계 진행 중.
- GitHub, 외부 서버, 클라우드 모델 API 접속하지 않음. 사용자 PC에 접근하거나 설치하지 않음.

## 변경한 실제 기능

- 기존의 `desktop/research_captures.py` 묶음 사전 검토 로직에 정확한 URL+본문 해시 중복 검사 외에 **로컬 유사 출처/버전 차이 후보 경고**를 추가함.
- 항목별 4개 경고 유형: `existing_url_other_body`, `existing_body_other_url`, `bundle_url_other_body`, `bundle_body_other_url`. 각 유형당 최대 3개 기존 자료 ID 또는 묶음 순번 사례를 표시하며 전체 경고 항목 수와 유형별 항목 수도 반환.
- **중요**: 정확히 동일한 URL과 본문은 기존처럼 가져오기 차단; 본문 버전 차이나 다른 URL에 반복된 본문은 등록 차단이 아니라 관리자가 승인하기 전에 보이는 경고. URL과 본문이 서로 다른 점은 웹 출처의 신뢰성·동일 법적 저작권·독립성 증명이 아님.
- `desktop/app.py`: Tkinter 가져오기 사전 검토 화면과 명시적 등록 확인 대화상자에 경고·증거 자료 ID 또는 묶음 순번을 표시함. 경고가 없으면 기존 승인 흐름 그대로 유지.
- SQLite 스키마와 기존 데이터 수정 없음. 검토는 SELECT 전용이며 URL 요청/DNS 조회 없음. 최대 20개 파일·최대 3건 예시 경계 유지, 보관 자료도 증거 후보에 포함.
- `tests/test_offline_research_bundle_provenance_preflight.py` 신규 12개; `scripts/stage54_bundle_provenance_gui_smoke.py`의 실제 Tkinter 경고·취소·승인 GUI 검사; `scripts/verify_offline_runtime.py`에 GUI 스크립트 추가.

## 실제 검증 결과

- 전체 pytest **단일 실행 1,120개 통과, 실패 0개, 131.97초**. `full_pytest.log`. 테스트 프로세스의 `sitecustomize`로 Python 소켓 연결 및 DNS 함수를 차단한 환경에서 실행.
- 신규 테스트 12개. 신규+기존 관련 테스트 **56개 통과**(`related_pytest.log`), 신규+기존 사전 검토 테스트 36개(`new_related_pytest.log`).
- Python 컴파일 검사 통과(`compileall.log`). Linux Xvfb 실제 Tkinter 경고 표시/승인 취소/등록 승인 통과(`gui_smoke.log`).
- 네트워크 소켓/DNS 차단 오프라인 자체 검사 **42개 명령 통과**(`offline_runtime.log`), 신규 GUI 검사 포함.
- 원본 ZIP 590개 경로 전부 보존, 기존 584개 파일 바이트 일치, 코드/문서 6개 파일 수정. 원본 기획안·요구사항 추적표·로드맵 CSV·기존 SQLite SHA-256 일치 (`source_preservation.txt`).

## 검증 및 미검증

- 테스트 로그: `new_related_pytest.log`, `full_pytest.log`, `offline_runtime.log`, `gui_smoke.log`, `compileall.log`.
- 원본 바이트 보존과 변경 파일 기록: `source_preservation.txt`. 최종 패키징 무결성: `package_integrity.json` 및 외부 verification txt.
- Windows 10/11 실기기, EXE 빌드, 실제 GGUF 추론, 인터넷 자료 수집, 장시간 자율 운영은 검증하지 않았음.
- Python 내부 소켓·DNS 차단 검사는 테스트 프로세스 수준이며 OS 방화벽과 모든 시스템 네트워크 경로를 보증하지 않음.

## 누적 ZIP 별도 재압축 해제 검증

- 실제 ZIP 전체를 새로운 폴더로 추출해 신규·관련 pytest **56개 통과** (`reextracted_related_pytest.log`).
- Linux Xvfb 실제 Tkinter 경고/승인 취소/승인 등록 GUI 재검사 통과 (`reextracted_gui.log`).
- 최종 ZIP을 다시 작성한 뒤 파일 수·CRC와 원본 보존 조건을 재검사함.
