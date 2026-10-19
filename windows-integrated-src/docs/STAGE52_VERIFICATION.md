# AIWACK 52단계 — 도구 실행 권한 및 승인 검사

## 기준 및 범위

- 원본: `AIWACK_Stage51_Local_Offline_Source.zip` 내부 `docs/progress.json` (1~51단계 완료, 52단계 대기).
- 기존 Windows 오프라인 Tkinter·SQLite 아키텍처, 설정, 포함된 데이터, 원본 기획 유지.
- 실제 구현: `desktop/tool_approvals.py` 승인 요청·반려·승인·권한 사전 검사·감사 기록. 단일 관리자 `company:manage` 인증 필수.
- 요청은 `request_key` 유일성 및 `BEGIN IMMEDIATE`로 중복 방지. 결정은 1회만 가능하고, 원장·감사 로그는 직접 수정/삭제 트리거 차단.
- 관리자 승인은 직원 권한을 **추가하지 않는다**. 승인은 이미 부여된 직원 capability, 생존 직원, 등록 상태 도구 및 내장 도구 사용 허가를 재확인한 후 기록된다.
- 승인 뒤 직원 권한을 회수하거나 등록 도구를 보관하면 사전 검사에서 실패한다. `required_capability` 빈 등록도 fail-closed.
- Tkinter `도구 사용 승인 검사` 탭: 요청 등록, 목록, 승인, 반려, 현재 권한 재검사.

## 보안상 중요한 제한

- **실제 도구 실행은 한 건도 연결하지 않았다.** `check_ai_tool_use()` 반환값은 현재 등록 상태/권한/관리자 승인에 대한 사전 검사 결과일 뿐 OS 명령, 브라우저, 파일, 네트워크, 결제·지출 기능을 실행하는 허가 토큰이 아니다.
- 이후 단계의 실행기에는 재검증 및 재사용·만료·동시성 제어, 작업별 정확한 도구 인수 허가, 고위험 액션 분리 승인, 멱등성이 필요하다. 이번 단계가 이런 실행 안전성까지 보장하지 않는다.
- 직원별 실제 런타임 로그인은 미구현. 관리자 GUI가 직원 ID를 지정한다.
- DB 암호화와 OS 레벨 악의적 SQLite 파일 변경에 대한 보호는 제공하지 않는다.
- Windows 10/11 실기기, 설치형 EXE 및 실제 GGUF 모델 추론은 미검증.

## 검증 로그

- `tests/test_tool_approvals.py`: 승인·반려·퇴직 도구·직원 권한 회수·관리자 로그아웃·중복·동시성·SQL 감사 불변성·프로세스/네트워크 차단 검사.
- `scripts/stage52_offline_gui_smoke.py`: 실제 GUI 버튼 조작 및 DB 재시작 보존, Python 소켓 연결 차단.
- `scripts/verify_offline_runtime.py`: 기존 검사 목록 유지하면서 Stage52 검사 추가.
- 전체 pytest: **659 passed in 77.54s**, `docs/STAGE52_FULL_PYTEST.log` (상세 -vv 결과). 첫 -q 실행은 시간 제한으로 중단됐지만 -vv 재실행은 전체 종료 및 통과.
- 신규 테스트: **14 passed**; Stage52·도구 등록·직원 권한 관련 테스트 **57 passed**.
- `xvfb-run -a python scripts/stage52_offline_gui_smoke.py`: 통과.
- `python scripts/verify_offline_runtime.py`: **20/20개 명령 통과**, `docs/STAGE52_OFFLINE_SMOKE.log`에 `EXIT:0` 기록.
- `python -m compileall -q desktop scripts tests`: 통과.
- 기존 51단계 ZIP 파일 **221개 누락 없이 보존**, 변경된 기존 파일은 6개. 원본 기획서와 기존 SQLite 파일 바이트 단위 일치.
- Linux Xvfb와 Python 소켓 차단을 사용했으며 실제 Windows 실행 또는 OS 차원의 네트워크 차단은 검증하지 않았다.

## 로드맵/제품 추정

- 로드맵: 52/100단계 (52%).
- 실질 제품 완성도: 약 20~24% (주관적 추정, 이전 단계의 19~24%와 큰 변화 없음).
- 다음 단계: 53단계 — 문서·파일 생성·수정 기능.
