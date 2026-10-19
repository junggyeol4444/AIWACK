# 54단계 오프라인 자료 — HTML 내부 CSS 참조 사전 점검

## 공식 개발 상태
- 기준 누적 ZIP: `AIWACK_Stage54_Offline_Usage_Rights_Hints_Continuation_Source.zip` (원본 907개 파일, CRC 검사 완료).
- 실제 확인: `docs/original_project_spec.txt`, `docs/requirements_traceability.md`, `docs/roadmap_100.csv`, `docs/roadmap_100.md`, `docs/progress.json`.
- 원본 100단계 로드맵: **1~53단계 완료, 54단계 인터넷 조사 및 자료 수집 진행 중(미완료)**. 실제 외부 조사·자동 수집은 구현하지 않음.
- 제품 완성도 **약 20~25%**는 비정량적/주관적 추정이며 로드맵 완료율 53%와 다름.

## 이번 실제 변경
- `desktop/research_captures.py`: 로컬 HTML `<style>` 및 `style=` 속성에 내장된 간단한 CSS `url()` 및 따옴표로 구분된 `@import` 문자열을 검사하여 최대 12개 호스트만 반환. CSS 주석, 숨김 script/template/noscript/svg 영역은 제외.
- `desktop/app.py`: 관리자 자료 묶음 등록 전 확인 화면 및 승인 대화상자에 경고 표시; 세부 예시 4건 이내, URL 경로·쿼리·자격증명 표시하지 않음.
- `tests/test_offline_research_css_references.py`: URL 분류, 로컬·비웹 경로 오류, 유출 방지, 항목 제한, 관리자 인증, 등록 승인 중 변경 재검토 등.
- `scripts/stage54_css_references_gui_smoke.py`: 실제 Linux Xvfb GUI 버튼 조작, 취소·승인, Python 소켓/DNS 차단.
- `scripts/verify_offline_runtime.py`: 신규 GUI 검사 등록.
- 기존 SQLite 스키마와 자료·원본 기획안은 **변경하지 않음**. 원본 사용자 승인 없이 설치/접속/외부 서버 통신 없음.

## 검증
- 전체 pytest **1275개 통과**, 실패 0개, 단일 실행 130.55초 (`full_pytest.log`).
- 신규·기존 관련 pytest **22개 통과** (`related_pytest.log`).
- Tkinter GUI 실제 조작 통과 (`gui_smoke.log`, Linux Xvfb).
- 오프라인 런타임 검사 **54개 명령 통과** (`offline_runtime.log`, Python 소켓·DNS 차단 — OS 방화벽 검증 아님).
- 기존 907개 파일 모두 보존, SHA-256 동일 900개, 의도된 수정 7개 (`source_preservation.json`). 보호 대상 기획안·요구사항·CSV 로드맵·기존 SQLite 바이트 동일.
- ZIP 자체 CRC 및 별도 압축 해제 재검사 결과는 `reextract_results.txt` 참조.

## 미검증·범위
- 이 분석은 제한적 CSS 정규식 탐색이지 CSS 전체 파서나 브라우저 렌더링이 아님. 외부 스타일시트, JS 생성 CSS, 복잡한 문자열·이스케이프·중첩 문법, 모든 네트워크 리소스를 탐지하지 못함.
- 인용된 URL/호스트는 미검증 로컬 문자열. 외부 출처의 진위, 위험도, 법적 사용권을 판정하지 않음.
- Windows 10/11 실기기, Windows EXE 빌드, 실제 GGUF 모델 추론, 장시간 자율 운영, 실제 인터넷 자동 자료 수집 미검증/미구현.
