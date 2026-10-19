# AIWACK 54단계 부분 개발: 저장 URL 오프라인 위험 신호 사전 점검

## 기준 자료·진행 상태

- 이번 기준 누적본: `AIWACK_Stage54_Offline_Host_Triage_Continuation_Source.zip` (이 대화에서 접근 가능한 최신 ZIP, 기존 499개 엔트리). 사용자의 초기 지정 `AIWACK_Stage54_Offline_Evidence_Continuation_Source.zip`보다 최신본을 사용했습니다.
- 개발 전 `docs/original_project_spec.txt`, `docs/requirements_traceability.md`, `docs/roadmap_100.csv`, `docs/roadmap_100.md`, `docs/progress.json`을 실제 열어 확인했습니다. 별도로 독립된 원본 기획안 첨부 파일은 로컬 파일 목록에 없으므로 ZIP 안의 원본을 사용했습니다.
- 원본 기획안 6.1~6.3절의 인터넷 조사 도구 요구와 14.3절의 외부 콘텐츠 신뢰 경계에 관련된 **사전 안전 검토 도구**를 추가했습니다. **웹 자동 조사/수집은 금지 조건 때문에 구현하지 않았습니다.** 로드맵 1~53단계 완료, 54단계 TODO/진행 중, 55단계 미착수.
- 원본 ZIP 엔트리 499개 누락 없음, 수정 6개, 나머지 493개는 바이트 단위 동일. 원본 기획안·요구사항 추적표·CSV 로드맵·기존 `dev_company.sqlite3`의 SHA-256은 기준 ZIP과 일치합니다. 세부 내용은 `source_preservation.txt`.

## 이번 실행의 코드 변경

1. `desktop/research_url_preflight.py` 신규: 기존 일관된 SQLite 읽기 스냅샷에서 최대 2,000개 저장 HTML 링크 문자열을 검사합니다. 루프백/사설/링크 로컬 등 비전역 IP 리터럴, 숫자형 IP 별칭, 로컬/단일 라벨 호스트명, URL 내 자격증명, 비표준 포트, IDN, IPv6 스코프, 끝 점(.)이 붙은 호스트명 및 잘못된 URL을 **수동 검토 경고**로 분류합니다.
2. `desktop/storage.py`에 관리자 권한 검사 후 읽기 전용으로 호출하는 API 추가. 기존 `all`/`pending`/`deferred` 필터 및 보관 자료 포함 옵션 유지. **필터 적용 후 전체 URL을 집계**하고 경고 URL 최대 40개만 화면에 표시합니다.
3. `desktop/app.py`의 Tkinter 조사 화면에 **저장 URL 위험 신호** 버튼 추가. 경고 유형별 건수·대상 URL·스캔 상한·필터를 표시하고, **경고 없음 ≠ 접속 안전함**을 명시합니다.
4. `tests/test_offline_research_url_preflight.py` 신규 38개 테스트. `scripts/stage54_url_preflight_gui_smoke.py` 신규 GUI 실제 버튼 검사. `scripts/verify_offline_runtime.py`에 새 GUI 검사 추가.
5. README, 로드맵 54단계 설명, `docs/progress.json`을 **부분 진행 기록으로만** 갱신. 기존 DB 스키마·데이터 및 JSON 내보내기 형식은 변경하지 않았습니다.

## 실제 테스트 및 검증

- **단일 전체 pytest: 993개 통과** (`full_pytest.log`, 108.93초, `[100%]`). 이전 누적 955개 + 신규 38개. 전체 단일 실행이 이번에는 정상 완료됐습니다.
- 신규 및 관련 3개 파일 별도 재검사: **82개 통과** (`related_pytest.log`, 6.37초). 993개에 중복 합산하지 않습니다.
- Python 컴파일 검사 `python -m compileall -q desktop scripts tests` 통과 (`compileall.log`).
- **오프라인 실행 검사 36개 명령 통과**, 종료 코드 0 (`offline_runtime.log`, `offline_runtime.exit`). Linux Xvfb에서 기존 및 신규 Tkinter GUI 실제 버튼 조작, 재로그인, 필터 전환을 검사했습니다. Python 프로세스의 소켓 연결·송신·DNS 조회를 차단한 환경에서 실행했습니다. **OS 방화벽 수준의 네트워크 차단 검증은 아닙니다.**
- 최초 `pytest -q` 직접 호출에서는 `desktop` 패키지 검색 경로가 없어 테스트 수집 오류가 발생했습니다. 이후 `PYTHONPATH=. python -m pytest`로 수정해 신규 38개 및 전체 993개가 통과했습니다. 제품 코드 오류가 아니라 테스트 실행 환경 설정 문제였습니다.
- 소스·테스트·검증 로그 포함 ZIP 전체 엔트리 무결성 검사 결과는 최종 패키징 시 기록합니다.

## 미완료 및 주의사항

- 이 기능은 **저장된 URL 문자열의 보수적 경고**입니다. DNS 조회/리다이렉트/재바인딩/실제 IP/웹사이트 소유권/콘텐츠 진위를 검증하지 않습니다. 경고가 없더라도 URL 접속을 승인하거나 안전을 보증할 수 없습니다.
- GitHub, 외부 서버, 클라우드 AI API, 유료 서비스, 사용자 PC에 접속하지 않았습니다. 실제 인터넷 자동 조사 및 자료 수집은 여전히 미구현. 54단계 완료 처리하지 않았습니다.
- Windows 10/11 실기기, Windows EXE, 실제 GGUF 모델 추론, 외부 웹 도구·결제 연동, 장시간 운영 통합 검증은 수행하지 않았습니다. 이전 병렬 작업 테스트의 간헐적 1.5초 시간 제한 초과 원인을 이번 기능으로 해결한 것은 아닙니다.
- **100단계 로드맵 완료율 53/100 = 53%**와 **실질 제품 완성도 약 20~25%(주관적 추정)**는 서로 다른 수치입니다. 원본의 실제 사업 운영·판매·결제·장시간 자율 운영 완료를 주장하지 않습니다.
