# AIWACK Stage54 — 오프라인 HTML 수동 리소스 참조 사전 검토

## 개발 기준과 단계 상태

- 기준 ZIP: `AIWACK_Stage54_Offline_Form_Control_Preapproval_Verified_Source.zip` (719개 기존 파일).
- ZIP에서 `docs/original_project_spec.txt`, `docs/requirements_traceability.md`, `docs/roadmap_100.csv`, `docs/roadmap_100.md`, `docs/progress.json` 확인.
- 원본 54단계 목표 **인터넷 조사 및 자료 수집**. 실제 웹 자료 자동 수집은 외부 서버 접속 금지에 따라 **미구현**.
- 기존 1~53단계 완료(53/100), 54단계 진행 중, 55단계 미진입.

## 이번 오프라인 구현

- 이미 저장된 HTML 사본의 `img src`, `link rel=stylesheet href`, `video poster`, `audio/video/source/track src` 정적 문자열을 검사.
- HTML 파일당 최대 12개 참조, 상세 예시 최대 4개. HTTP(S) URL을 관리자 입력 출처 주소에 대해 **같은 출처 / 다른 출처 / 형식 오류**로 분류.
- GUI에서 실제 URL 경로, 쿼리, 자격증명, 태그 데이터 대신 **호스트명만 표시**. HTTP 외 스킴, 사용자 자격증명, 비표준 포트와 지나치게 긴 URL은 형식 오류로 표시.
- 사용자 입력 URL을 상대 경로 기준으로 사용하고 HTML `<base>` 지시를 실행하지 않음. `script`, `style`, `template`, `noscript`, `svg`의 실행/숨김 영역과 주석은 검사 대상에서 제외.
- 기존 승인 토큰·명시적 관리자 동의, 사전 검토, SQLite 자료 등록/중복 방지 동작 유지. 검사 자체는 읽기 전용.
- 모든 GUI 및 단위 테스트는 웹 요청·DNS 없이 검사. **이미지/스타일/미디어 요청, 렌더링, 다운로드, 추적 여부 판정은 수행하지 않음.**

## 알려진 제한

- `srcset`, CSS `url()`, JavaScript 생성 요소/리소스, browser preloads, 응답 헤더·리다이렉트 및 실제 브라우저 네트워크 요청은 검증하지 않음. HTML에 참조가 없다는 결과도 안전을 보장하지 않음.
- 소켓 차단은 Python 수준이며, 운영체제 방화벽/시스템 호출 전체를 감시했다는 의미는 아님.
- Windows 10/11 실기기, Windows EXE, 실제 GGUF 모델, 장시간 무인 운영 검증은 수행하지 않음.
- `docs/original_project_spec.txt`는 ZIP 내부 원본 기준. 별도 원본 첨부 텍스트에 직접 접근하지 못한 경우 별도 확인으로 주장하지 않음.
- 실질 제품 완성도 약 20~25%는 성능/사업 운영의 검증된 지표가 아닌 추정.

## 검증 산출물

- `related_pytest.log`, `related_pytest.exit`: 신규 및 기존 관련 테스트.
- `full_pytest.log`, `full_pytest.exit`: 전체 pytest 단일 실행 및 종료 상태.
- `gui_smoke.log`, `gui_smoke.exit`: Linux Xvfb 실제 Tkinter 로그인·사전 검토·취소·승인. Python 소켓/DNS 호출 차단.
- `offline_runtime.log`, `offline_runtime.exit`: 소켓/DNS 차단 오프라인 실행 검사 명령 결과.
- `reextract_pytest.log`, `reextract_gui.log`: 최종 ZIP 별도 압축 해제본 검사.
- `source_preservation.json`: 이전 누적 ZIP과 경로/해시 단위 보존 비교.
- `package_verification.json`: 최종 ZIP CRC, 파일 수, SHA-256, 비교 결과.

결과 수치는 검사 종료 후 각 로그를 기준으로 판단하며, 어떤 시험이든 미완료인 경우 통과로 처리하지 않습니다.

## 확인된 실행 결과와 회귀 위험

- 신규·기존 관련 pytest: **39 통과**, `related_pytest.exit=0`.
- GUI Xvfb: 실시간 Tkinter 로그인, 미리보기·승인 취소·승인 등록 **통과**; Python 소켓/DNS 호출 차단. `gui_smoke.exit=0`.
- 1차 전체 pytest 단일 실행: **1,235 통과 / 1 실패 / 총 1,236 수집**, `full_pytest.exit=1`, **146.36초**. 실패는 기존 `tests/test_task_parallel.py::test_real_two_local_subprocesses_overlap`의 경과시간 **1.53초**가 테스트 허용 **1.5초**를 초과한 간헐적 실행 성능 실패입니다. **근본 원인은 조사·수정하지 않았습니다.**
- 기존 병렬 관련 파일 독립 재실행: **9 통과**, `parallel_recheck.exit=0`. 이전 실패를 지우거나 원인 해결로 간주하지 않습니다.
- 전체 오프라인 실행: **51개 명령 통과**, `offline_runtime.exit=0`; 기존 Tkinter 검사와 신규 Tkinter 검사 포함.
- 1차 전체 pytest의 1개 실패 때문에 1차 실행을 전체 통과로 기록하지 않습니다. 이어진 재검사 및 압축 해제본 결과는 별도 로그에 남깁니다.
- 2차 **단일 전체 pytest 재실행**: **1,236 통과 / 실패 0개**, `full_pytest_rerun.exit=0`, **127.80초**. Python 소켓/DNS 차단 상태로 수행. 1차 시간 제한 실패 가능성은 여전히 남음.
- 예비 누적 ZIP을 별도 디렉터리에서 압축 해제하여 관련 pytest **39 통과**, Linux Xvfb 실제 GUI **통과**. `reextract_pytest.exit=0`, `reextract_gui.exit=0`.
- 이전 ZIP의 719개 경로를 모두 보존했으며 보호 문서·SQLite SHA-256 일치. 파일 전체 교차 비교 및 ZIP CRC는 `source_preservation.json`, `package_verification.json` 참고.
