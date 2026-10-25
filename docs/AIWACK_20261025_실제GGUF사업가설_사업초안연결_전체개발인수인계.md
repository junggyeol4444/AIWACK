# AIWACK 실제 기능 개발 누적 인수인계

## 2026-10-25 후속 코드 개발 — 기존 로컬 GGUF 총괄 신규 사업 기획·승인·사업 초안 연계 (append-only)
- 사용자 최우선 명령: “개발 하라고 계속 개발이 전부 끝날 때 까지”. **전체 기능 개발 먼저**, 검증/오류수정 단계는 전체 기능 개발 완료 이후로 유지. 이번 추가 개발에서도 신규 pytest/Windows EXE 실제 실행/물리 버튼 검증을 수행하지 않음(**NOT_RUN**). 완료·성공 주장 금지.
- 신규 원본 연결 모듈 `windows-integrated-src/desktop/company_business_ideas_model.py`: 기존 `desktop.chief_runtime.invoke_chief_model`을 실제 호출, 회사의 기존 활성 사업 유형 목록 및 소유자가 입력한 대상 고객·고객 문제에 한정된 **1건의 실제 GGUF 사업 가설** JSON을 엄격 파싱. 형식 오류면 가짜 가설 자동 생성 금지. 실제 모델 호출 ID와 입력/출력 SHA256 및 형식 오류의 불변 감사. 수요/시장/매출 검증으로 오인 금지, 모델 교체 없음. 생성 커밋 `1e668d6e18039c206060fc54141c35ca6daf2947`.
- 동일 모듈 추가 개발: 관리자 검토 후보 선정/기각 감사 원본 보존. 명시적으로 후보 선정한 실제 모델 가설을 별도 관리자 클릭 시에만 기존 `business_portfolio.add_business` 호출해 예산 **0원**, 상태 `draft` 로컬 사업 초안 생성. 아이디어·실제 모델 호출·사업 DB 번호를 별도 불변 링크로 저장; 중복 초안/자동 외부 실행 금지. 커밋 `0904e5a4b150191d1da5f8246bf5d9789028c287`.
- 기존 `windows-integrated-src/desktop/storage.py`: 실제 모델 가설 생성/읽기/관리자 검토와 사업 초안 인계/인계 조회 `LocalStore` API를 연결. 커밋 `64fc13fa57dfad31ee30cb4562aa339cf13dd492`, `514389b84c32d11e1b13218a7b12617de001bbd1`.
- 기존 `windows-integrated-src/desktop/company_native_owner_workflows.py`: 한국어 Tk 탭 '실제 AI 신규 사업 가설' 신규 추가, 고객/문제 입력, 백그라운드 취소 가능한 실제 GGUF 한 번 호출, 제안 목록, 소유자 별도 선정·기각, 명시적으로 선정한 가설을 기존 사업 포트폴리오에 예산 0원 초안으로 연결, 출처 조회 버튼. 기존 30업무·PG/은행 등 탭 삭제·교체 없음. 커밋 `aa726d7bfb85936d93abc7b890e207db13194840`, `f6257cc1c4e8caa0ebea813297c55de8a63b28c2`.
- 기존 `windows-integrated-src/build_windows_exe.bat`: 새 모듈 `desktop.company_business_ideas_model` 원본 EXE PyInstaller hidden-import 누적. 커밋 `b58edea408253dd7aa2687c32028ec507e74e8a4`.
- **금회 누적**: 앞선 다중 Windows GUI 중복 GGUF 잠금/자동 운영 누락 감사 개발 커밋 **11개**, 이번 실제 로컬 GGUF 사업 기획/관리자 선정/기존 사업 DB 초안 연결 개발 커밋 **7개**, 합계 **18개 실제 코드 변경 커밋**. 총 수정/추가 대상: `company_autopilot.py`, `company_continuity.py`, `company_office_gui.py`, `company_business_ideas_model.py` (신규), `storage.py`, `company_native_owner_workflows.py`, `build_windows_exe.bat` 7개 코드/설정 파일. 테스트 브랜치의 기능 개발이며 main 최종 병합 아님.
- 현재 실제 개발 **미완료**: 원본 1~21회차 1,099개와 최신 GitHub 원격 파일 간 전수 SHA·3-way 보존 대조; 원본 변경 52·추가 73개 누적 기능 유실/충돌별 병합; 원본 역사 문서 28+매니페스트 2의 GitHub 개별 보존; 원본 기획 15장, T01~T20, 15부서31AI30업무, Windows10/11 실제 EXE GUI, 실제 GGUF 전체 장기 협업, 사업/고객/상품/승인된 실도구·계정, 실제 금융 처리와 무단 거래 방지, 자율 장기 운영/회복 중 아직 미구현 요구 모두 개발. 전체 기능 개발 종료 **이후에만** 기존·신규 전체 통합검증 → 실패 수정 → 전체 재검증 → main 최종 안전 병합.
- 확인하지 않은 실기 검증/성능/24시간/T01~T20 전항목 성공과 모델 출력, Windows EXE 빌드 성공을 주장하지 않음. 별도 새 GUI, 웹/HTTP, 원본 삭제, 다른 프로젝트/예약 수정 없음.

## 후속 개발 우선 지시
테스트 브랜치 최신 기존 소스와 이 대화의 선행 전체 누적 인수인계를 읽고 아직 개발 완료하지 못한 원본 기획 기능과 누적 소스 병합을 이어서 개발한다. 전체 개발 종료 전 테스트·검증만 반복하지 않는다. 개발 완료 후 전체 통합검증→발견한 오류 수정→전체 재검증→main 안전 병합 순서를 반드시 보존한다.


## 2026-10-25 17:59 KST 후속 실제 개발 — GGUF 가설→사업→프로젝트→첫 상품 원본 보존형 연결 (append-only)
- 사용자 원문 최우선: “개발부터 다 끝내라”, “개발 하라고 그리고 main에 올리고”, “잔여 누적 소스 전체 main 병합”. **전체 개발 → 전체 통합검증 → 실패 수정 → 전체 재검증 → main 안전 병합·원격 확인** 순서를 유지. 단일 기능 테스트를 먼저 실행하거나 성공으로 기록하지 않음.
- 기존 저장소/브랜치: `junggyeol4444/AIWACK`, `test/aiwack-20261023-0755-cumulative-resume-merge`. 최초 조회 테스트 HEAD `722deaf0d009fe78359dd0d89b6c8d86605cac62`, main `f70dd72c74f4b6440ebea85501a66f4f5d85a391`, PR #9 draft·미병합.
- 실제 기능 코드: `windows-integrated-src/desktop/company_business_idea_pipeline.py` 신규. 이미 실제 총괄 GGUF 호출 원본과 관리자 후보 선정·사업 초안 링크가 존재하는 경우에만 관리자가 별도 클릭하여 기존 `business_projects.create`로 예산 0원·계획 상태 프로젝트를 생성. 다시 별도 클릭한 경우에만 기존 `product_catalog.create`로 가정가격 0원·미검증 첫 상품 초안 생성. SQLite `BEGIN IMMEDIATE`, 중복 거부, 비상정지, 기존 권한, 모델 출력 SHA/호출 ID/원본 연결, append-only 트리거, 프로젝트·상품 감사 체인 조회. 실판매·시장 검증·외부 게시·실결제 자동 실행 없음.
- 기존 코드 실제 수정: `windows-integrated-src/desktop/storage.py`에 관리자 전용 프로젝트/상품/감사 API, `windows-integrated-src/desktop/company_native_owner_workflows.py` 기존 한국어 Tk 가설 탭에 입력·별도 승인 버튼·감사 조회 추가, `windows-integrated-src/build_windows_exe.bat` PyInstaller import 누적. 기존 7개 Windows EXE Actions workflow에 두 모델 사업 모듈 hidden-import 보존형 추가. 기존 30업무·고객·금융·직원·총괄 코드 삭제/대체 없음.
- 실제 코드 커밋: `74ff903df2cb32c3ee5193055e321f0d69e3b5a1` (신규 모듈), `2612fc7b69ecf5c5dd14abf78d0d1e6ff2b0933d` (저장소 API), `15800d81f22c835e95f95bbf3aa43382c4c7d46e` (GUI 입력), `7dbce08ca86980328d7731d7092732eb3f07a8dd` (EXE 빌더), `1d27c517be236c1dd7eb178e20d95b3bba9d99be` (GUI 별도 버튼), `9d3d114f0df1e4610f508c65ef7799af0f183e9e` (Windows Actions 7개 단일 커밋).
- 검증: **NOT_RUN** (전체 기능 개발 미완료이므로 신규 pytest·Windows EXE 실기·물리 GUI 클릭·실GGUF 모델 호출·24시간·T01~T20 전체 통합검증을 이번 회차 실행하지 않음). CI 최신 신규 커밋의 완료/PASS 증빙 없음. 과거 2026-10-23 `39896550100` CI SUCCESS, `39896550237` packaged GUI SUCCESS, `39896550165` Windows EXE SUCCESS는 과거 `126cd85b` 기준이며 신규 기능의 성공 아님. `39896550108` 실 GGUF FAILURE: Windows2022 실제 15부서31역할30업무 GGUF 단계 실패, Windows2025 CPU runner 진단 실패.
- 남은 개발: 원본 1~21회차 1,099개 ZIP과 현 원격 main/테스트 파일의 전수 3-way 대조 및 기존 52개 변경/73개 추가의 기능별 보존형 병합, 역사 원문 28개+매니페스트 2개 원격 개별 원본 확인·복원, 15장·T01~T20·15부서31AI30업무·실 GGUF 총괄/직원 승인/최종 보고/관리자 승인·사업/고객/상품/실도구·외부 계정/금융·장기 복구 전체 요구의 잔여 개발. 정확한 잔여 기능 수·완료율/완료일 추측 금지.
- 금지: HTML/WebUI·대체 앱, 가짜 GGUF·가짜 성과, 기능 축소, 외부 Drive, 원본/문서 삭제·덮어쓰기, 권한·안전 차단 우회, 무단 PG·은행·외부 게시, 임의 브랜치/force push, 다른 프로젝트/예약 변경. 현재 대화 유지 우선, 메시지 게시 위치 미확인 시 같은 대화 게시 주장 금지. 사용자 요청 최고 사용 가능 모델은 설정 권한 없으면 선택했다고 주장 금지.


## 사용자 지시 및 후속 개발: 2026-10-25 — 내부 개발 후 main 반영
- 사용자 명시: 테스트 브랜치는 **테스트할 때만** 만들고, 기능 개발은 내부에서 수행해 누적 소스를 GitHub main에 반영. 사용자가 모든 구 테스트 브랜치 4개 삭제 명령을 내렸으나 GitHub 연결 도구는 branch-ref 삭제 동작을 제공하지 않고 별도 로그인 브라우저도 미연결이므로 **삭제 미실행**, 완료 주장 절대 금지. 기존 4개 브랜치의 main 대비 미포함 커밋 모두 0건 확인.
- 내부 작성 소스 신규 `windows-integrated-src/desktop/company_failure_ai_analysis.py`: 실제 직원 실패 기록(실패·시간초과·중단)을 소유자 직접 승인 하에서 실제 로컬 총괄 GGUF 1회 원인 분석. 원본 실행 ID, 조회 가능한 기존 실패 메타데이터, 입력 해시, 실제 모델 호출 ID, 출력 해시·원인/개선안/위험을 SQLite에 영구 감사. 다른 EXE 동시 실행 시 동일 후속 ID UNIQUE claim 차단, 미완료 원본 남김. 미승인 업무 재실행/외부 결제/게시/가짜 성공 없음.
- 기존 `company_native_owner_workflows.py` 한국어 Tk 원본에 '실패 업무 총괄 AI 원인 분석' 탭, 대기 실패 후속 목록·관리자 단일 실GGUF 실행·원본 감사 버튼 추가. 기존 백그라운드 모델 스레드·취소·관리자 별도 확인 유지. 기존 `build_windows_exe.bat`에 신규 모듈 hidden-import 누적.
- **현재 상태: 개발만 진행, 전체 기능 개발 미완료, 본 회차 코드 실행 테스트/Windows EXE 실기검증/장기 GGUF 검사 미수행.** 개발 완료 이후 전체 통합검증 → 오류 수정 → 재검증. 기존 main 원본·DB·사용자 기타 프로젝트·예약 보존.
