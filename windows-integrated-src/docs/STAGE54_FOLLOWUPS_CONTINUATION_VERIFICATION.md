# AIWACK 54단계 후속 개발 — 저장된 HTML 링크 수동 후속 조사 목록

## 기준과 범위

- 입력 원본: `AIWACK_Stage54_Offline_Evidence_Drift_Continuation_Source.zip` (345개 파일).
- 직접 확인: `docs/original_project_spec.txt` 제3장 시장조사·제6장 웹 도구·제12장 완료 조건, `docs/requirements_traceability.md`의 R06/T06, `docs/roadmap_100.csv`, `docs/roadmap_100.md`, `docs/progress.json`.
- **로드맵 1~53단계 완료, 54단계 진행 중, 55단계 미진입**. 이 개발은 실시간 웹 검색·자동 수집을 구현하지 않는다.

## 구현

1. `desktop/research_followups.py`: 저장된 HTML 링크 문자열을 최신 참조 자료부터 최대 **2,000개 링크**까지 읽고 URL별로 묶는다. 링크마다 로컬 미등록, 보관본만 존재, 활성 로컬 후보 여러 개, 활성 후보 1개를 구분한다. 참조 자료 수와 최신 참조 ID 최대 5개를 표시한다. 최대 40개 URL을 우선순위 순서로 반환하고, 결과 및 스캔 잘림 여부를 명시한다. URL을 DNS 조회하거나 열지 않는다.
2. `desktop/storage.py`: 소유자 권한 검사 후 읽기 전용 조회. SQLite 데이터 추가·수정·삭제 없음.
3. `desktop/app.py`: 조사 자료 화면에 `미확인 링크 후속 조사 목록` 버튼 추가. 보관 자료 포함 여부는 기존 체크박스를 따르며, **로컬 URL 일치는 실제 웹 출처 검증이 아님**을 표시한다.
4. `tests/test_offline_research_followups.py`: 14개 단위·권한·오프라인·영속성·범위 제한 검사.
5. `scripts/stage54_followups_gui_smoke.py`: 실제 Tkinter 버튼 조작, 재로그인 복원, Python socket 연결 차단 검사. `scripts/verify_offline_runtime.py`에 새 스모크 등록.

## 검증 (2026-10-13)

- pytest 전체 **59개 파일**, 중복 없는 **7개 분할 실행**, 합계 **844 passed**: 그룹별 **93 + 143 + 211 + 152 + 96 + 132 + 17**. 로그 `docs/verification_stage54_followups/pytest_group_*.log`. **단일 전체 pytest 실행 통과를 주장하지 않는다.**
- 새 테스트 **14 passed**; 관련 조사 자료 테스트 묶음 **159 passed** (신규 14개 포함).
- 실제 Tkinter GUI (Linux Xvfb) 신규 스모크 PASS. Python socket 차단 상태에서 신규 GUI·기존 참조 추적·기존 JSON 차이 검사·데스크톱 self-test **4개 명령 PASS** (`offline_subset.log`). **OS 방화벽이나 전체 실행 경로의 네트워크 차단 검증은 아니다.**
- Python `compileall` 통과. 기존 345개 파일 보존 및 원본 기획서·SQLite 데이터 바이트 동일성은 최종 ZIP 검증에서 확인.
- **미검증:** Windows 10/11 실기기, 실제 GGUF 추론, 실제 인터넷 조사·자동 자료 수집, 전체 오프라인 일괄 검사.

## 해석 제한

- '로컬 미등록'은 **스캔한 DB에서 동일 URL 문자열이 없다는 뜻**이지, 웹사이트에 자료가 없다는 뜻이 아니다.
- '활성 후보 1개/여러 개'는 **등록 URL 문자열의 정확한 일치**일 뿐 웹 출처의 진위, 자료 신뢰성, 링크 유효성, 내용의 일치 여부를 확인하지 않는다.
- 최신 링크 최대 2,000개만 스캔한다. 링크가 더 많으면 일부 결과가 생략된다. URL 보고는 최대 40개이며 잘림을 표시한다.
- 54단계 원래 완료 조건인 인터넷 조사·자동 자료 수집은 **미완료**. 완료 53/100(53%), 실질 제품 완성도 약 20~25%(주관적 추정).
