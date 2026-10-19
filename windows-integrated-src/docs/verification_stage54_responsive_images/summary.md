# AIWACK Stage54 — 오프라인 HTML 반응형 이미지 srcset 사전 검토

## 기준과 완료 조건

- 기준: `AIWACK_Stage54_Offline_Passive_Resource_Preapproval_Continuation_Source.zip` — 실제 ZIP 내부 원본 기획안, 요구사항 추적, CSV/Markdown 로드맵 및 progress.json 확인.
- 원본 개발 로드맵 54단계는 **인터넷 조사 및 자료 수집**이며 외부 서버 접속 금지 상태에서 **여전히 미완료**.
- 완료 53/100 (53%), 54단계 진행 중, 제품 실질 완성도 **약 20~25% 주관적 추정**.
- 기존 Windows 오프라인 Tkinter/로컬 SQLite 아키텍처 유지, 원본 기획안·SQLite·로드맵 5개 핵심 파일 해시 보존.

## 실제 구현

- 저장한 로컬 HTML의 `<img srcset>`과 `<source srcset>` 후보를 파일당 최대 12개 정적 검사, 예시 최대 4건 표시.
- 관리자 입력 출처 URL을 기준으로 동일/다른 출처/형식 오류 분류. 노출 데이터는 태그 종류·유효한 descriptor·호스트뿐, 경로·쿼리·원본문자열 비출력.
- 관리자 묶음 사전 검토 및 등록 승인 대화상자 경고에 연결. 취소 시 SQLite 변경 없이 종료, 기존 승인 후 파일 변경 탐지 재사용.
- 이미지 로딩·웹 요청·DNS 조회·브라우저 실행 없음. srcset 내 data URI·쉼표가 있는 URL 및 복잡한 srcset 문법은 완전한 브라우저 파서가 아니므로 보수적으로 형식 오류 취급. 경고 없음이 안전을 증명하지 않음.

## 검증

- 새 관련 pytest: `tests/test_offline_research_responsive_images.py` + 기존 passive-resource tests **30개 통과**.
- 조사 영역 pytest **568개 통과**.
- 조사 외 전체 영역 pytest **685개 통과**. 중복 없는 두 그룹 합계 **1,253개 통과, 실패 0개**.
- 단일 전체 pytest는 이번 실행에서 약 17% 시점 환경 시간 제한으로 중단: 전체 단일 실행 통과를 주장하지 않음.
- Linux Xvfb/Tkinter 실제 로그인, srcset 호스트 및 경고 표시, 취소 후 DB 미변경, 명시적 승인 등록 통과. Python-level connect/DNS 함수 차단 사용.
- Windows 10/11 실기기/EXE, 실제 GGUF 추론, 24시간 운용, 실제 외부 인터넷 조사 미검증. Python 연결 차단은 OS 방화벽 검증이 아님.
- 기존 간헐적 병렬 시간 제한 문제의 근본 원인은 이번 변경에서 해결했다고 주장하지 않음.

## 보존

- 기존 파일 **741개 경로 모두 유지**. 바이트 그대로 **736개**, 기존 변경 **5개**.
- 변경 파일: README.md, desktop/app.py, desktop/research_captures.py, docs/progress.json, scripts/verify_offline_runtime.py.
- 원본·SQLite 등 보호 파일별 비교값은 `source_preservation.json`.
- 사용자 PC 접속, 설치, 설정 변경, 유료 가입, GitHub·원격 API·외부 서버 호출 없음.

## 추가 완료 검증

- Python 소켓/DNS 차단 오프라인 런타임 검사 **52개 명령 통과**, 종료 코드 0. `offline_runtime.log`, `offline_runtime.exit`.
- 별도 폴더 예비 ZIP 압축 해제 후 관련 pytest **30개 통과**, Linux Xvfb 실제 Tkinter **통과**. `reextract_pytest.log`, `reextract_gui.log`.
- 오프라인 Python 후킹 범위 밖의 모든 운영체제 네트워크 사용을 입증하는 검사는 아님.
