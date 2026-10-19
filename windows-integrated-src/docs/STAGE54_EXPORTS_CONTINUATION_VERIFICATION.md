# AIWACK Stage54 후속: 로컬 근거 보고서 JSON 내보내기

## 원본 요구사항 및 진행 단계

- 기존 누적 입력: `AIWACK_Stage54_Offline_Evidence_Continuation_Source.zip` (305개 파일).
- `docs/original_project_spec.txt` 원본 기획서 제6장(웹 도구·자료 수집·실제 실행), 제13장(독립 검증), `docs/requirements_traceability.md` R06/T06 등 확인.
- `docs/roadmap_100.csv`의 54단계는 **인터넷 조사 및 자료 수집**, 기존 1~53단계 완료, 54단계 미완료.
- 외부 서버 및 GitHub 사용 금지 조건을 준수하기 위해 인터넷 접속/자동 수집/온라인 진위 검증은 구현·수행하지 않음.

## 신규 기능 (완료된 하위 작업)

- `desktop/research_exports.py`: 기존 로컬 근거 발췌 보고서를 UTF-8 JSON으로 직렬화. 표준화된 보고서 JSON의 SHA-256 체크섬을 첨부하고 내보낸 JSON의 무결성 검사를 지원.
- `desktop/storage.py`: 소유자 `company:manage` 권한 확인 후 보고서 생성·파일 저장. SQLite 자료 자체는 변경하지 않음.
- `desktop/app.py`: `근거 보고서 JSON 저장` 버튼. 저장 위치는 사용자가 직접 선택. 기존 파일은 **덮어쓰지 않음** (`xb` 배타적 생성).
- `tests/test_offline_research_exports.py`: 11개 신규 테스트. 인증, 재로그인 후 내보내기, JSON 왕복, 체크섬 변조 탐지, 기존 파일/심볼릭 링크 보존, SQLite 무변경, 오프라인 소켓 차단, 보관 자료, 잘못된 입력 등.
- `scripts/stage54_exports_gui_smoke.py`: 실제 Tkinter 버튼, 재로그인, 중복 저장 차단, 소켓 차단 검사.
- `scripts/verify_offline_runtime.py`: 신규 GUI 검사를 기존 오프라인 검증 묶음에 추가.

## 사용자 사용 방법 및 보안 주의

1. Windows 데스크톱 앱에 소유자로 로그인해 54단계 오프라인 조사 자료 화면으로 이동.
2. 검색어를 입력하고 `검색어 근거 발췌 보고서`로 미리보기.
3. `근거 보고서 JSON 저장`을 누르고 **새로운** 로컬 JSON 파일 경로 선택.
4. JSON에는 등록된 자료 ID, 본문 인용 행, 해시, URL(미검증) 및 출처 진위 미검증 표시가 포함됨.

**JSON 파일은 암호화되지 않습니다.** 개인 정보나 비밀 자료를 검색하면 내보낸 파일에도 포함될 수 있으므로 보관에 주의해야 합니다. SHA-256 체크섬은 파일 내용의 우발적 변경 탐지용이며 서명, 작성자 신원 증명, 웹 원문 출처 확인, 사실 검증을 의미하지 않습니다. 공격자가 내용과 체크섬을 함께 바꾸는 행위는 방지하지 못합니다.

## 실제 실행한 검증

- `python -m pytest -q tests/test_offline_research_exports.py tests/test_offline_research_evidence.py`: **22 passed**.
- 전체 `tests/test_*.py` 56개 파일을 중복 없이 6개 묶음으로 분할 실행: **151 + 167 + 136 + 157 + 157 + 39 = 807 passed**, 실패 0. 로그: `docs/verification_stage54_exports/group_1.log` ~ `group_6.log`.
- 진행 기록 갱신 후 `tests/test_offline_research_exports.py tests/test_project_structure.py`: **16 passed**. `post_progress.log`.
- `xvfb-run -a python scripts/stage54_exports_gui_smoke.py`: **PASS**.
- Python outbound 소켓을 차단한 `python -u scripts/verify_offline_runtime.py`: **29개 명령 PASS**, 최종 요약 PASS. `offline_full.log`.
- Python compileall 검사 PASS.
- ZIP 원본 305개 파일 보존, 수정 파일은 `desktop/app.py`, `desktop/storage.py`, `docs/progress.json`, `docs/roadmap_100.md`, `scripts/verify_offline_runtime.py` 5개. 원본 기획안과 SQLite 파일은 바이트 동일.

## 미검증/미완료

- 실시간 인터넷 검색·웹페이지 자동 수집·온라인 출처 진위 확인·AI 자율 조사: **미구현**.
- Windows 10/11 실기기 GUI/설치/빌드 및 실제 GGUF 추론: **미검증**.
- 네트워크 차단 검사는 Python 소켓 차단 기반이며 운영체제 전체 방화벽 검증은 아님.
- **로드맵 53/100 완료, 54단계 진행 중.** 실질 제품 완성도 약 20~25% (주관적 추정이며 측정치 아님).
