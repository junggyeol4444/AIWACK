# AIWACK 57단계 — 제한형 AST 코드 테스트: 실제 구현 및 검증

기준 누적 ZIP: `AIWACK_Stage56_Offline_Code_Authoring_Continuation_Source.zip` (1,082 파일). `docs/original_project_spec.txt`, `docs/requirements_traceability.md`, `docs/roadmap_100.csv`, `docs/roadmap_100.md`, `docs/progress.json` 실제 열람 후 변경. 원본 기획안과 요구사항 추적표를 변경하지 않았습니다.

## 구현
- `desktop/restricted_code_tests.py`: 관리자 승인 저장된 Python을 임의 Python 바이트코드로 실행하지 않고, 허용 AST만 수작업으로 해석. 상수 대입, 단순 함수, return/if, 산술, 비교, 단언식 지원. Python `eval`/`exec`/`compile`/import 사용하지 않으며, 파일·네트워크·서브프로세스 접근 구문 자체를 거부.
- 제한: 최대 20건 `assert`, 4KiB 테스트, 240 AST 노드, 1,200 해석 단계, 128비트 정수, 값 길이 4,096자, 직접/간접 재귀 거부.
- `desktop/storage.py`: 저장된 코드 파일·DB 버전 SHA-256 재확인, 관리자 로그인 권한 검사, 결과를 추가 전용 SQLite 실행 이력으로 보관. 검사 원문은 로그에 기록하지 않음.
- `desktop/app.py`: 관리자 전용 Tkinter 탭에서 코드 ID 선택 후 명시적 검사 실행 승인·기록 조회. 기존 Stage56 코드 저장 탭과 분리.
- `scripts/verify_offline_runtime.py`: 전체 기존 검사 목록 보존, Stage57 GUI 회귀 검사 하나 추가. 긴 검사를 나눠 실행하기 위한 선택적 환경 변수(`AIWACK_OFFLINE_START`, `AIWACK_OFFLINE_END`) 지원. 설정 없으면 전체 62개 명령 수행.

## 검증 결과
- `python -m pytest -q`: **단일 전체 실행 시간 제한으로 중단**, 통과 주장하지 않음(상세 로그 첨부).
- 전체 **92개 서로 다른 테스트 파일**, **19개 중복 없는 그룹**, **1,410개 통과, 실패 0**. 그룹별 결과는 `group_01.json`~`group_19.json`.
- 신규 테스트 관련 Stage57 + Stage56: **57개 통과**. 최종 Tkinter 대시보드 수정 후 Stage57/Stage56/기존 데스크톱 관련: **73개 통과**.
- Python socket/DNS guard 하의 기존 Tkinter GUI·데스크톱 오프라인 검사 **62개 명령 통과**, 8개 구간. 각 `offline_??_??.log` 참조. Linux Xvfb에서 실제 Stage57 버튼 실행/취소/로그아웃·재조회 확인.
- 기존 1,082개 파일 경로 보존. 원본 기획안·요구사항 추적표·사용자 SQLite 기존 데이터 SHA-256 일치. 나머지 변경 목록은 `verification.json` 참조.
- 최초 신규 테스트 중 사전 화이트리스트가 등록되지 않은 Python 함수 호출을 허용한 문제를 발견해 수정 후 57개 재실행 통과. 이 사항은 최초 결함과 수정 내역으로 기록합니다.

## 보류 / 정직한 한계

**이 구현은 임의 Python의 OS 격리 실행이 아닙니다.** 허용된 AST만 관리자 프로세스에서 해석하며, 실제 Python 임의 코드 테스트, OS 수준의 파일·네트워크·메모리/CPU 격리, 악의적 네이티브 코드 실행 검사는 제공하지 않습니다. 따라서 57단계 **부분 구현·BLOCKED**, 사용자 또는 안전한 Windows 격리 런타임 확보 후 재검증 필요. 54단계 인터넷 자동 수집과 56단계 실제 GGUF 추론 검증도 계속 보류합니다. 55단계는 기존 완료로 유지합니다.

로드맵 완료 **54/100** (1~53과 55), 다음 개발은 **58단계 — 이미지·영상·문서 도구 연결 구조**, 실제 제품 완성도 **20~25%** (정량 측정이 아닌 주관 추정).
Windows 10/11 실제 PC, Windows EXE 빌드, 실제 GGUF 모델, 장시간 자율 운영은 미검증. 어떤 외부 서버·GitHub·클라우드 AI API에도 접속하지 않았으며 사용자의 PC에 접속하거나 설치하지 않았습니다. Python 수준 네트워크 차단은 OS 방화벽을 증명하지 않습니다.
