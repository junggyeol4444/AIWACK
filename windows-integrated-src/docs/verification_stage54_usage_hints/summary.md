# AIWACK Stage54 — 로컬 HTML 이용·색인 자기 표기 사전 검토

## 개발 기준

- 실제 사용한 최신 소스: `AIWACK_Stage54_Offline_Responsive_Srcset_Continuation_Source.zip`. ZIP 내부 원본 기획안, 요구사항 추적표, 100단계 CSV/Markdown, 진행 JSON 확인.
- 공식 54단계: **인터넷 조사 및 자료 수집**. 외부 서버 접속 금지로 실시간 웹 조사·자동 수집은 **미구현/미완료**. 완료 53/100 (53%).
- 실질 제품 완성도 약 20~25%는 엄밀한 품질 측정이 아닌 주관적 추정.

## 실제 추가 구현

- `desktop/research_captures.py`: 저장된 HTML의 `<meta name="robots">`(allowlist 토큰)와 `<link rel="license">`(동일/다른 출처, 형식 오류, 호스트만) 정적 분석. 파일별 최대 12건·상세 예시 4건, 숨김 script/template/noscript 무시.
- `desktop/app.py`: 기존 묶음 등록 전 Tkinter 사전 검토 및 관리자 승인 화면에 표시. 기존 승인 취소·파일 변경 감지·정확히 같은 본문 중복 차단 유지.
- `scripts/stage54_usage_hints_gui_smoke.py`, `tests/test_offline_research_usage_hints.py`, `scripts/verify_offline_runtime.py`: 실제 GUI/네트워크 차단 회귀 검사 추가.
- URL 전체·메타 자유 입력값/비밀 쿼리를 반환하지 않음. **robots meta는 robots.txt가 아니며, license 링크는 법적 이용 허가를 증명하지 않음**. 브라우저 렌더링·DNS·원격 조회 없음.

## 실제 검증 결과

- 신규/관련 pytest: **40개 통과** (`related_pytest.log`).
- 전체 테스트 파일 83개를 중복 없는 18개 그룹으로 분할 실행: **1263개 통과, 실패 0개**. `split_*_*.log`에서 개별 명령 및 결과 확인.
- **단일 전체 pytest는 약 17%에서 실행 제한으로 중단** (`full_pytest.log`), 조사 영역 대량 호출도 시간 제한으로 중단 (`research_pytest.log`). 단일 실행 통과로 주장하지 않음.
- 소켓·DNS 호출을 Python 수준에서 차단한 환경의 데스크톱 자체 검사 및 Linux Xvfb 실제 Tkinter GUI **53개 명령 모두 통과** (`offline_*.log`). 운영체제 전체 방화벽 검증은 아님.
- 중간 GUI 스모크 테스트의 표시 문구 단언이 `·`/`/` 불일치로 1회 실패해 테스트 기대값을 실제 GUI 문구와 일치시킨 후 재실행 통과 (`gui.log`).
- 기존 소스 756개 경로 모두 보존, 바이트 동일 750개, 수정 6개. 기존 SQLite 파일/원본 기획안/요구사항 추적표/CSV 로드맵 SHA-256 일치. `source_preservation.json`.
- Windows 10/11 실기기, EXE 빌드, 실제 GGUF 모델 추론, 장시간 자율 운영, 실제 원격 출처 인증은 **미검증**. 사용자 PC 접속·GitHub·클라우드 API·설치 없음.

## ZIP 재압축 해제 검사

- 예비 ZIP 905개 파일 CRC 통과, 별도 디렉터리 압축 해제 후 관련 40개 pytest 및 실제 Tkinter GUI 재검사 통과. `reextract_pytest.log`, `reextract_gui.log`.
- 최종 ZIP 검사는 외부 검증 텍스트 참조. 테스트 결과 로그를 나중에 포함하면서 바뀐 최종 ZIP의 SHA-256을 따로 계산함.
