# Stage54 부분 구현 — 후속 조사 JSON 재검사 (0.1.53)

## 원본 기준과 범위

- 입력: `AIWACK_Stage54_Offline_Followup_Export_Continuation_Source.zip` (444개 원본 엔트리, 가장 최신 접근 가능한 누적 ZIP).
- 코드 수정 전에 ZIP 내 `docs/original_project_spec.txt`, `docs/requirements_traceability.md`, `docs/roadmap_100.csv`, `docs/roadmap_100.md`, `docs/progress.json`을 열어 확인. 별도 원본 기획안 첨부 텍스트는 이 실행 환경에서 독립 파일로 확인할 수 없어 ZIP에 보존된 원본을 사용.
- 로드맵 54단계는 실제 인터넷 조사·자료 수집이며 미완료. 완료 단계 1~53 유지; 55단계로 이동하지 않음.
- 기존 444개 엔트리 전부 보존, 소스 변경 7개(`source_preservation.txt` 참고). 원본 기획안·요구사항 추적표·CSV 로드맵·기존 SQLite DB는 바이트 단위 일치.

## 실제 변경

- `desktop/research_followup_verification.py` 신규: 명시적으로 선택한 후속 조사 JSON을 체크섬 검사하고 저장된 필터·보관 범위로 현재 로컬 SQLite 결과를 재계산. URL 추가/누락/변경 수와 각각 최대 20개 미리보기, 나머지 메타데이터/순서 차이 식별.
- `desktop/research_verification.py`: 기존 안전한 로컬 JSON 읽기 함수에 파일별 상한 매개변수 추가 (기존 근거 1MB, 후속 조사 12MB). 절대 로컬 경로, 심볼릭 링크·비정상 파일·경로 교체 감지, UNC/네트워크 드라이브 차단 유지. Windows 경쟁 조건은 완전 제거가 아님.
- `desktop/storage.py`: 관리자 권한 검사 후 읽기 전용 검사 메서드 추가.
- `desktop/app.py`: `후속 조사 JSON 재검사` 버튼, 체크섬/로컬 DB 일치·불일치 및 URL별 차이 출력, 취소·오류 처리.
- `scripts/stage54_followup_recheck_gui_smoke.py` 신규; `scripts/verify_offline_runtime.py`에 새 GUI 검사 등록.
- `tests/test_offline_research_followup_verification.py` 신규 (13개): 변경/추가/누락/필터·보관 범위/체크섬 변조/파일 크기/심볼릭 링크/인증/재로그인/오프라인/DB 보존 등.

## 실제 검증

- 64개 중복 없는 테스트 파일, 7개 그룹의 **최종 재실행 기준 932개 통과** (group 1: 117 passed, group 2: 101 passed, group 3: 129 passed, group 4: 157 passed, group 5: 148 passed, group 6: 117 passed, group 7: 163 passed). 그룹별 로그와 파일 목록 포함.
- **초기 그룹 1에서는 116개 통과·1개 실패**: `test_real_two_local_subprocesses_overlap` 1.53초로 기존 1.5초 제한 초과. 이후 해당 테스트 단독 재실행 1개 통과(1.42초), 그룹 1 재실행 117개 통과. 원인 분석/수정은 완료하지 않았으므로 간헐적 회귀 위험 존재.
- Linux Xvfb 실제 Tkinter 버튼 조작, 재로그인, JSON 일치/불일치, 취소 및 Python 소켓 차단: `gui_smoke.log` 통과.
- Python 소켓 `connect`/`connect_ex`/`sendto`/`sendall`/`getaddrinfo` 차단 환경에서 오프라인 자체 검사 + 신규 GUI + 기존 근거 JSON GUI **3개 명령 통과** (`offline_subset.log`). 이는 OS 수준 네트워크 차단을 뜻하지 않음.
- `python -m compileall -q` 성공. 새 13개 테스트 별도 재실행 통과 (`new_tests.log`).
- `python -m scripts.verify_offline_runtime` 전체 검사는 실행을 시도했지만 시간 제한으로 중단되어 **전체 오프라인 검증 통과로 보고하지 않음**. 단일 전체 pytest도 이번 실행에서 완료하지 않았음.
- Windows 10/11 실기기, Windows EXE 빌드, 실제 GGUF 모델 추론, 외부 인터넷 조사/자료 수집, 웹 출처의 진위: **미검증·미구현**.

## 완성도와 제한

- 로드맵 완료: **53/100 (53%)**; 54단계 진행 중.
- 실질 제품 완성도: **약 20~25%** (정량 검증이 아닌 주관적 추정).
- 체크섬은 자기 일관성 검사일 뿐 전자서명·온라인 출처 증명이 아니며, 재계산 가능한 JSON의 악의적 조작을 막지 못함. URL 차이는 원인 진단이 아닌 현재 로컬 데이터의 비교 결과.
- 외부 서버·GitHub·클라우드 AI API·사용자 PC에 접속하지 않았고, 유료 가입/설치/환경 변경도 하지 않았음.
