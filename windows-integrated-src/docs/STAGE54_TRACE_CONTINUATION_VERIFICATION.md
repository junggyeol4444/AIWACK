# AIWACK 54단계 진행본 — 로컬 참조 연결 추적 (미완료 유지)

## 기준과 범위

- 기준 ZIP: `AIWACK_Stage54_Offline_Links_Continuation_Source.zip` (277개 파일).
- 실제 `docs/progress.json`: 1~53단계 완료, 54단계 진행 중. 이 완료 상태를 변경하지 않음.
- GitHub·외부 서버·클라우드 AI API를 호출하지 않음. 웹 URL은 미검증 문자열/메타데이터.
- 기존 Windows Tkinter·SQLite 아키텍처와 기존 데이터 파일을 그대로 유지.

## 실제 구현

- `desktop/research_captures.py`: 저장된 HTML 링크 URL과 별도로 등록된 로컬 자료의 출처 URL 문자열을 연결, 깊이 1~3, 50개 자료/150개 링크까지 폭넓이 우선 탐색. 순환 링크 방지, 다중 로컬 후보/누락/보관 문서 표시. 읽기 전용, 네트워크 접속 없음.
- `desktop/storage.py`: `company:manage` 관리자 권한 검사를 통과한 경우에만 추적 결과 조회.
- `desktop/app.py`: `오프라인 조사 자료 수집`의 `로컬 참조 연결 추적` 버튼과 상세 뷰. 실제 온라인 출처 진위 미검증 경고.
- `tests/test_offline_research_trace.py`: 12개 테스트 (길이 제한, 순환·다중 후보, 보관, 권한, 오프라인, 기존 문서 보존 등).
- `scripts/stage54_trace_gui_smoke.py`: 실제 Tkinter 등록/조회/로그아웃 재로그인 검사. Python 소켓 연결 차단.
- `scripts/verify_offline_runtime.py`: 신규 GUI 스모크 명령 추가.

## 실제 검증

- 신규 테스트 12개 + 기존 HTML 링크 테스트 16개 = **28 passed**.
- 전체 pytest 단일 실행: 제한 시간으로 **18% 지점에서 종료**. 완료로 간주하지 않음 (`verification_stage54_trace/pytest_full.log`).
- 전체 테스트 파일 54개를 **중복 없이 분할 실행**, 총 **785 passed**: 그룹1 151, 그룹2 167, 그룹3 136, 그룹4 157, 그룹5 157, `tests/test_local_models.py` 별도 17. 로그는 `docs/verification_stage54_trace/`에 보관.
- 전체 `scripts/verify_offline_runtime.py` 일괄 실행은 시간 제한으로 종료되어 **일괄 통과를 주장하지 않음**.
- 독립 실행·GUI 5개 명령을 소켓 차단 환경에서 분리 수행하여 **5개 통과**: `desktop.entry --self-test`, 기존 Stage53/54 GUI, HTML 링크 GUI 및 신규 참조 추적 GUI. (`offline_commands.log`)
- `python -m compileall -q desktop` 통과.
- 테스트에 사용한 GUI는 Linux Xvfb. Windows 실기기, 실제 GGUF 추론, 인터넷 수집은 미검증/미구현.

## 오해 방지

- `source_url`은 관리자가 주장한 출처 주소일 뿐, 검증된 원본 웹사이트가 아니다. 동일 URL을 공유한 로컬 자료는 모두 **후보**로만 표시한다.
- 예전 HTML 등록 시 원본 HTML 바이트가 보존되지 않은 자료의 링크를 추정하거나 소급 생성하지 않는다.
- 순환 관계 추적, 로컬 자료 유무 표시가 실제 인터넷 검색/수집을 대체하지 않는다.
- 54단계는 계속 **IN_PROGRESS**이며 완료 로드맵 **53/100 (53%)** 유지. 실질 제품 완성도는 추정 **20~25%**로만 보고.
