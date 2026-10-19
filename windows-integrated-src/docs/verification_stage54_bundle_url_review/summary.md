# AIWACK 54단계 부분 개발 — 등록 전 로컬 자료 묶음 URL 사전 경고

## 기준 및 단계 유지

- 기준: `AIWACK_Stage54_Offline_Bundle_Custody_Continuation_Source.zip` (633개 파일), 최신 접근 가능한 누적본.
- ZIP 내부 `docs/original_project_spec.txt`, `docs/requirements_traceability.md`, `docs/roadmap_100.csv`, `docs/roadmap_100.md`, `docs/progress.json` 확인. 별도의 독립 첨부 원문은 이 실행에서 확인되지 않았으므로 ZIP 내 보존된 원본 기준.
- 원래 54단계는 **인터넷 조사 및 자료 수집**. 외부 서버 연결 금지로 미구현·진행 중, 1~53 완료(53/100) 유지.

## 신규 기능

- 기존 등록 후 HTML 링크 URL 위험 신호 검사기 `classify_stored_url`을 자료 묶음 **가져오기 전 읽기 전용 사전 검토**에 재사용.
- 각 자료별 `url_warning_codes`, 경고 자료 수 `url_warning_item_count`, 코드별 건수 `url_warning_category_counts` 제공.
- 사설/로컬/비전역 IP 리터럴, 숫자형 호스트명, 내부 도메인, 국제화 호스트, 끝점 등의 문자열 기반 경고만 제공. 기존 URL 검증에서 자격증명·비표준 포트·localhost는 이미 차단함.
- GUI에서 URL 경고를 상세 표시하고 승인 대화상자에 경고 건수 추가. 사용자가 취소하면 SQLite 쓰기 없음. 소유자 승인 없이 등록되지 않음.
- 기존 동일 URL/본문 중복 등록 차단, 출처·버전 차이 경고 및 승인 토큰 무효화 로직은 유지.
- 동일한 SHA-256이라고 진짜 웹 원본임을 증명하지 않으며, URL 경고가 없더라도 **안전한 사이트/접속 가능 여부를 보증하지 않음**. DNS 조회, IP 연결, 자동 다운로드, 클라우드 AI 요청 없음.
- 기존 SQLite 테이블·파일 내 자료를 변경하지 않음.

## 실제 검증

검증 기록은 이 폴더에 포함하며 실제 실행 후 채운다. 일괄 테스트 성공 여부는 로그/exit 코드로 판정한다.

## 제한

- Python 수준 네트워크 차단은 운영체제 방화벽에 대한 증거가 아님.
- Windows 10/11 실기기, Windows EXE 생성, 로컬 GGUF 모델 추론, 장시간 무인 자율 운영 검증 없음.
- 54단계 실시간 인터넷 수집과 자동 조사는 접속 제한으로 미구현. 제품 실질 완성도 20~25%는 주관적 추정일 뿐 단계 완료율 53%와 다름.

### 실행 완료 기록

- 전체 pytest 단일 실행: **1,160 통과 / 0 실패, 136.96초** (`full_pytest.log`, `full_pytest.exit=0`).
- 신규 16건 포함 관련 범위 pytest: **63 통과 / 0 실패** (`related_pytest.log`).
- Linux Xvfb Tkinter 실제 버튼: URL 경고 표시, 승인 거절 DB 0건, 별도 승인 1건 등록 (`gui_smoke.log`).
- Python 소스 컴파일: 성공 (`compileall.log`).
- 기준 633개 파일 보존, 기존 파일 626개 바이트 동일·7개 변경. 원본 기획안·요구사항 추적표·CSV 로드맵·SQLite 데이터 SHA-256 일치 (`source_preservation.json`).
- `scripts/verify_offline_runtime.py`: Python 소켓·DNS 호출을 차단한 **45개 명령 통과** (`offline_runtime.log`, `offline_runtime.exit=0`). Linux Xvfb에서 실제 UI 검사 포함.
- 누적 ZIP을 새 폴더에 압축 해제한 후 관련 pytest **63개 통과** (`reextract_related_pytest.log`) 및 실제 Tkinter GUI 검사 통과 (`reextract_gui.log`). ZIP CRC 검증 통과.
- 이전 ZIP 633개 파일 모두 보존 및 기존 원본 문서·SQLite 해시 일치(`source_preservation.json`).
