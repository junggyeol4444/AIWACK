# AIWACK 54단계 추가 후속 구현 — 오프라인 조사 자료 묶음 가져오기

## 기준

- 최신 누적 기준: `AIWACK_Stage54_Offline_Continuation_Local_Source.zip`, 총 251개 파일.
- 해당 ZIP의 `docs/progress.json`: 1~53 완료, `next_step=54`, `in_progress_step=54`.
- 원본 54단계 요구: **인터넷 조사 및 자료 수집**. 사용자의 GitHub/외부 서버/클라우드 AI API 접속 금지 때문에 실제 온라인 조사는 수행하지 않음.
- 기존 Windows 오프라인 Tkinter·SQLite 프로그램 및 251개 파일을 보존하고 기존 데이터베이스를 초기화하지 않음.

## 이번에 추가한 기능

- 관리자 로그인 후 `자료 묶음(JSON) 가져오기`를 클릭해 이미 PC에 저장한 HTML/텍스트 사본 1~20개를 한 번에 로컬 SQLite에 등록.
- JSON 파일 형식: `docs/STAGE54_OFFLINE_BUNDLE_EXAMPLE.json` 참고. 해당 JSON을 실제 자료 파일과 같은 폴더에 복사하고 `file`과 `url`, `title`을 수정해야 함. `file`은 하위 폴더 구분 없는 단일 파일명.
- 목록 JSON: UTF-8, 최대 32,768바이트. 자료: `.txt/.md/.html/.htm`, 각 1~256,000바이트. 경로 탐색, 심볼릭 링크, 네트워크 공유·드라이브 검사, 누락 자료·중복 파일명·중복 URL/본문 검사.
- 각 자료의 원본 파일명·원본 바이트 SHA-256·크기·추출 본문 SHA-256 저장. 목록 원본 바이트 SHA-256·묶음 식별자·자료 순서·가져온 시각을 별도 신규 SQLite 테이블에 기록. DB에는 원본 파일 바이트를 저장하지 않음.
- 모든 항목을 성공적으로 등록하지 못하면 한 트랜잭션으로 전체 롤백(기존 기록도 보존).
- 원본 SQL 기록과 묶음 기록은 UPDATE/DELETE 금지 트리거로 보호. 기존 개별 파일 자료에는 묶음 메타데이터가 없음.
- HTML은 실행하지 않고 기존 HTMLParser로 가시 텍스트만 추출. URL은 실제 연결·검증 없이 미검증 출처 문자열로 보존.

## 실제 검증 결과

1. `python -m pytest -q --disable-warnings`: **741 passed in 88.97s**, 종료 코드 0. 신규 `tests/test_offline_research_bundles.py`: **18 passed**.
2. `xvfb-run -a python scripts/stage54_bundle_gui_smoke.py`: **통과**. 실제 Tkinter 버튼으로 2개 자료 일괄 등록, 중복 전체 거부, 상세 원본 해시·묶음 SHA-256 확인, 재로그인 후 복원.
3. `python -m scripts.verify_offline_runtime`: **24개 명령 모두 통과**, Linux Xvfb 사용; Python 소켓 연결을 차단한 환경에서 독립 실행과 기존 GUI 회귀 및 새 화면 검증.
4. `python -m compileall -q desktop` 통과. 누적 ZIP 무결성 및 이전 ZIP과의 파일 보존 검사는 별도로 실행 후 결과 기록.
5. Windows 10/11 실기기·Windows UNC/매핑 드라이브/경로 경쟁 조건·실제 GGUF 추론 **미검증**. Python 소켓 호출 차단은 OS 전체 방화벽 검증과 다름.

## 미완료 범위 및 정직한 진행 기록

- **실제 인터넷 검색·웹페이지 자동 다운로드·자동 시장 조사·원격 출처 진위 검증 미구현.** 외부 서버 접속 금지 조건을 우선 적용함.
- SHA-256은 보관한 로컬 파일 바이트의 동일성 표시일 뿐 그 자료가 실제 웹사이트에서 왔다는 증거가 아님.
- 사용자의 로컬 파일은 불변 스냅샷으로 DB에 복사되지 않음: 원본 파일 삭제 후 동일 원본 바이트 재생성은 이 DB로만 불가능.
- SQLite는 기본 상태에서 암호화되지 않음. 관리자가 입력하는 자료를 신뢰할 수 있는 명령으로 실행하지 않음.
- Windows에서 TOCTOU 경로 교체, 운영체제 네트워크 공유 탐지 등 보안 보장은 실기기 테스트 전까지 주장할 수 없음.
- **`docs/progress.json`: 완료 53/100(53%), 54단계 진행 중 유지.** 제품 실질 완성도는 약 20~25%라는 주관적 추정(정량적 기능 충족률이 아님).
