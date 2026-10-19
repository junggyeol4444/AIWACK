# Stage54 부분 개발 — 오프라인 묶음 JSON 목록 생성 도우미

## 기준 및 한계

- 입력 누적본: `AIWACK_Stage54_Offline_Bundle_Preapproval_Continuation_Source.zip` (578개 파일).
- ZIP 내 `docs/original_project_spec.txt`, `docs/requirements_traceability.md`, `docs/roadmap_100.csv`, `docs/roadmap_100.md`, `docs/progress.json`를 실제 검토. 이 대화에서 ZIP과 별개인 원본 기획서 첨부 텍스트는 확인되지 않아 ZIP에 보관된 원본을 기준으로 함.
- 원본 제6장 실제 작업 도구 및 100단계 로드맵의 54단계 **인터넷 조사 및 자료 수집** 완료 조건은 바꾸지 않음. 원격 조사 및 자동 수집은 외부 접속 금지로 여전히 미구현.
- 기존 `dev_company.sqlite3`, `docs/original_project_spec.txt`, `docs/requirements_traceability.md`, `docs/roadmap_100.csv`를 바이트 단위 보존. 테스트는 임시 SQLite 데이터베이스를 사용함.

## 구현

- `desktop/research_bundle_manifest.py`: 사용자가 선택한 **같은 로컬 폴더의** 1~20개 UTF-8 TXT/MD/HTML 파일을 검사해 기존 `aiwack-offline-research-bundle-v1` 스키마의 JSON 목록 파일 생성. URL과 제목은 **관리자가 직접 제공**. 입력 파일의 허용 형식·본문·바이트 크기/해시 확인, 최종 JSON 최대 32KB 제한, 기존 파일 원자적 덮어쓰기 방지(`O_EXCL`), 심볼릭 링크/Windows 접합점/공유 드라이브 경로 거부. 생성 과정에서 파일 내용은 JSON에 복사하지 않음.
- `desktop/storage.py`: 관리 권한이 있어야 호출할 수 있는 생성 API. 목록 생성 시 SQLite 쓰기 없음.
- `desktop/app.py`: `로컬 묶음 JSON 목록 만들기` 실제 Tkinter 버튼, 파일 선택·자료별 URL/제목 입력·사용자 생성 승인·로컬 저장 다이얼로그. 이후 기존 `자료 묶음(JSON) 가져오기`를 **별도로 눌러 사전 검토 및 등록 승인**해야 실제 자료 등록.
- `tests/test_offline_research_manifest_builder.py`: 신규 20개 테스트(취소/저장, 호환성, 중복 파일/잘못된 URL/위험 경로/심볼릭 링크, 인증, DNS·소켓 차단 등). 기존 목록 생성 전 수동 JSON 작성 기능 및 가져오기 동작과 호환.
- `scripts/stage54_manifest_builder_gui_smoke.py`: Linux Xvfb에서 실제 Tkinter 버튼으로 취소·목록 생성·덮어쓰기 거부·명시적 별도 승인 등록 검증.
- `scripts/verify_offline_runtime.py`: 새로운 실제 GUI 검사를 네트워크 호출 차단 회귀 명령에 추가.

## 실제 테스트

- 묶음 생성 및 기존 호환 관련 pytest: **62개 통과**. 로그: `related_pytest.log`.
- 전체 pytest 단일 실행: **1,108개 통과, 실패 0개 (121.06초)**. 로그: `full_pytest.log`.
- Linux Xvfb에서 신규 GUI와 기존 묶음 GUI 실제 버튼 조작: 통과. 신규 GUI는 Python 소켓 및 DNS 함수를 차단한 상태에서 수행.
- `python -m compileall -q desktop scripts tests`: 통과. 로그: `compileall.log`.
- 네트워크 소켓 차단 오프라인 명령 검사: 별도 `offline_runtime.log` 참조.
- 원본 보존: `source_preservation.txt`; 패키지 CRC 및 SHA-256: 외부 검증 TXT 및 `package_integrity.json` 참조.

## 미구현·미검증

- 실제 웹 자동 자료 수집, HTTP/DNS 접속·진위 인증 미구현; 등록 출처 URL은 관리자 주장일 뿐 사실성 보장 없음.
- 입력 자료를 준비하거나 파일/출처 URL을 생성하는 자동화 없음. 로컬 파일 바이트 검사와 JSON 생성만 구현.
- Windows 10/11 실기기, Windows EXE 빌드, Windows 파일 경쟁 조건 및 네트워크 공유 드라이브 실기기, 실제 GGUF 추론, 장시간 자율 운영은 미검증.
- Python 소켓·DNS 차단은 테스트 프로세스 내 검사로 OS 방화벽이나 모든 가능한 네트워크 경로 차단을 보증하지 않음.
- 로드맵은 **53/100 완료(53%), 54단계 진행 중**, 실질 제품 완성도 **약 20~25%**(주관적 추정)로 별도 기록.

## ZIP 재압축 해제 재검증

- 별도 새 폴더로 누적 ZIP 전체 압축 해제 후 **관련 pytest 62개 통과**, 실제 Linux Xvfb Tkinter 생성/승인 버튼 검사 통과. `reextracted_related_pytest.log`, `reextracted_gui.log` 참조.
- 초기 패키지의 파일 588개에 본 재검증 기록 2개를 추가해 최종 ZIP을 다시 작성했으며 CRC 검사를 통과함. 이 추가는 소스 코드와 DB를 변경하지 않음.
