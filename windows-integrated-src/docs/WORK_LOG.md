# 개발 작업 기록 / 계속하기 체크포인트

프로젝트: AI Autonomous Company  
기준 문서: `docs/original_project_spec.txt`  
이번 작업 환경: ChatGPT 파일 생성 환경 (사용자의 개인 PC 아님)

## 완료 및 검증한 단계

- [x] 001. 원본 기획서의 기능·완료 조건 정리 → `docs/requirements_traceability.md`; T01~T20 추적 항목 정리.
- [x] 002. 전체 시스템 구성과 개발 순서 확정 → `docs/architecture_v0.md`, `docs/roadmap_100.md`.
- [x] 003. 프로젝트 폴더 구조 생성 → 원문 9.5절 기준 디렉터리.
- [x] 004. 개발 환경 및 설정 파일 구성 → `pyproject.toml`, `.env.example`, `backend/core/config.py`.
- [x] 005. Python 중앙 서버 기본 구현 → `backend/main.py`, GET /.
- [x] 006. 서버 실행 및 상태 확인 기능 → GET /health, GET /api/v1/health, 테스트.

## 다음 단계

- [ ] 007. 데이터베이스 연결 및 초기화. 첫 연결과 초기화 이후에 정상·오류 동작 검증.
- [ ] 008. 데이터베이스 변경 이력 관리.

## 현재 사용자 승인이 필요한 항목

사용자 PC에 필요한 프로그램·설치·비용·계정은 사용자가 PC를 켜고 요청할 때 한 번에 안내한다. 이 환경에서 PC 설치는 수행하지 않는다.

## 실행 제약

매시간 예약은 개인 PC의 켜짐/꺼짐을 확인하지 못한다. 사용자 PC에 접근하거나 자동 설치하지 않는다. 예약별 작업 환경이 다를 수 있으므로 `docs/WORK_LOG.md`와 결과 ZIP 같은 체크포인트를 보존하고, 접근 가능한 코드가 확인된 경우에만 이어 개발한다. 접근 불가한 코드를 구현했다고 주장하지 않는다.

## 테스트 기록

- `python -m pytest -q`: **9 passed**.
- 독립 프로세스 `uvicorn backend.main:app` 실행 후, `GET /api/v1/health`가 HTTP 200 및 `status=ok`를 반환하는 것을 확인.
- 사용자의 실제 PC 또는 외부 서버에서 검증한 결과는 아님.


## GitHub 통합 이후 — 2026-10-12: 8단계 구현 및 로컬 실구동 검사

- Alembic migration `0001_initial`: 최초 로컬 DB 생성, `alembic_version` 관리, 이전 7단계 DB의 데이터 보존 도입.
- `scripts/launch_local.py`, `start_windows.bat`, `start_mac_linux.sh`: 사용자 로컬 실행기.
- `/diagnostics` 화면과 DB 영구 저장을 확인하는 실제 HTTP 진단.
- `scripts/real_smoke_test.py`: Uvicorn 서버 프로세스 두 번 기동, API/HTML, 데이터 저장·재시작·재조회 검증.
- **코드/구조 pytest 17개 통과** (로컬) 및 **실제 HTTP/DB 재시작 스모크 테스트 통과**.
- 회사의 AI 에이전트 및 자율 수익 기능은 아직 미구현.
- 이후 개발: 9단계 회사 소유자 및 기본 권한 기능.

- Chromium 실제 브라우저 클릭 검증은 샌드박스 관리자 네트워크 정책(127.0.0.1 차단)으로 실행 불가. 브라우저 구문 검사 통과. 사용자 PC 실사 확인 요청.


## 데스크톱 프로그램 전환 (100단계 진행 수는 유지)

- 사용자 요청에 따라 Windows EXE가 주요 배포 형태이며 웹 UI는 배포판에서 사용하지 않음.
- `desktop/entry.py`, `desktop/app.py`, `desktop/storage.py`로 Tkinter 데스크톱 창, 로컬 SQLite, 데이터 재실행 후 보존 기능 구현.
- `scripts/desktop_gui_smoke.py`에서 실제 네이티브 창의 버튼을 호출하고 다시 열어 데이터 유지 검증.
- GitHub Actions `windows-exe.yml`로 Windows 빌드와 실행파일 자체 저장 검사 및 다운로드 가능한 Artifact 준비.
- 전체 AI 회사의 자율 동작은 미구현; 관리자 화면 로드맵의 완성으로 간주하지 않음. 진행률 8/100 유지.

## 2026-10-12 9단계 — 소유자 계정·기본 권한

- 새 owner_accounts SQLite 테이블과 PBKDF2-SHA256 salted password hash(310,000 반복). 비밀번호 원문·API 키 저장하지 않음.
- 첫 실행 계정 생성, 최초 관리자 단일 등록, 로그인, 로그아웃, 세션별 로컬 메모 접근 권한 검사, 5회 실패 시 60초 차단.
- 기존 EXE 메모 데이터는 보존; 디스크 파일 자체 암호화/비밀번호 복구는 미지원(별도 보안 고도화 단계 필요).
- 실제 GUI 시작/계정 생성/로그인 실패/정상 로그인/저장/종료/재실행을 scripts/desktop_gui_smoke.py로 점검.
- Windows PyInstaller EXE 빌드/실행은 GitHub Actions 성공 여부 별도 확인 후 보고.

다음 단계: 10단계 관리자 화면 기본 틀.

## 2026-10-12 10단계 — 관리자 화면 기본 틀

- Windows EXE의 기존 로그인 뒤에 `관리자 센터` 탭 추가. 7개 관리 영역(회사 현황/조직·직원/업무·프로젝트/사업·상품/재무·매출/승인·권한/운영·설정) 전환 제공.
- 실데이터는 로컬 SQLite 상태와 소유자 역할만 읽음. 아직 없는 사업·재무·AI 기능은 '미구현'으로 명시하여 허위 운영 현황을 표시하지 않음.
- 소유자 인증 없이는 관리자 화면에 접근 불가하며 로그아웃 직후 접근도 차단.
- 실제 Tk 창에서 7개 메뉴 버튼을 전환하고 로그아웃/재로그인/재실행/저장 보존을 점검하도록 테스트를 확장.
- 다음 11단계 회사 정보 및 운영 목표 관리.

## 2026-10-12 11단계 — 회사 정보 및 운영 목표 관리

- 회사명/소개/운영 방향을 로컬 SQLite 회사 프로필 단일 레코드로 영속 저장, 수정 가능.
- 관리자 권한으로만 목표 추가·조회·수정(상태 포함)·삭제 허용. 삭제 전 사용자 확인 대화상자.
- 기존 회사 계정/메모/목표 DB를 삭제하지 않고 신규 테이블만 추가.
- `회사·목표 관리` 데스크톱 탭, 실제 GUI 폼 및 목록 조작과 프로그램 종료·재실행 후 영속성 검증.
- 실사용 상 사업 수익 목표 달성·AI 자체 운영은 아직 미구현.
- 12단계 부서 등록·수정·삭제 기능이 다음 순서.

## 2026-10-12 12단계 — 부서 생성·수정·삭제

- 기존 관리자 로그인 뒤 Windows 데스크톱 `부서 관리` 탭 추가. 부서명/담당 영역/등록 목록, 추가·수정·삭제·입력 초기화 제공.
- 로컬 SQLite `company_departments` 테이블을 후방 호환 방식으로 신설; 기존 계정·회사·목표·메모는 보존.
- 소유자 권한 필수. 빈 이름·과도한 입력·중복 이름·잘못된 부서 ID 거부. 부서 삭제에는 사용자의 명시적 확인 필요.
- 13단계 직무/역할, AI 직원·실제 부서 운영은 아직 미구현.
- 실제 데스크톱 GUI, 로컬 pytest, exe --self-test, CI/Windows 빌드는 작업별 결과 확인 후 확정한다.

## 2026-10-12 13단계 — 직급·직무·역할 정의 카탈로그

- 기존 사용자 계정, 회사 프로필, 목표, 부서 및 메모 데이터를 보존하면서 별도 SQLite `company_designations` 테이블 추가.
- owner-only CRUD 및 종류별 고유 이름 검사, 입력 정규화·예외·원자적 실패 검증.
- 네이티브 Windows EXE의 직급·직무·역할 관리 탭 구현, 선택/수정/삭제 확인 및 재실행 데이터 지속성 검사.
- 역할(role)은 직원 업무 책임 이름이며 실제 시스템 RBAC 권한 부여와 엄격히 분리. 직원 배치 기능은 아직 미구현.
- 검증: pytest, Xvfb 실제 GUI, 독립 프로세스, GitHub Windows EXE 자체 self-test가 성공한 경우에만 완료로 판정.

다음 단계: 14단계 AI 직원 정보 저장 구조.

## 2026-10-12 14단계 — AI 직원 정보 저장 구조

- 로컬 SQLite `ai_employee_profiles` 테이블에 안정적인 employee_key, 표시명, 설명, 부서 ID 및 직급·직무·역할 ID 참조, 초기 상태(draft/inactive), 생성·수정 시각을 추가.
- FK ON DELETE RESTRICT와 분류별 트리거로 유효하지 않은 부서·직급·직무·역할 연결을 차단하며 기존 13단계 데이터는 그대로 유지.
- 관리자 인증이 필요한 `add_employee_draft`, `list_employee_records`, `read_employee_record` 저장·조회 기능을 구현. AI 직원 자동 생성 GUI와 실행/비활성화는 15단계 이후의 업무로 구분.
- 실제 Windows EXE `--self-test`에 직원 메타데이터 저장·프로세스 재열기·FK 삭제 제한 검사를 추가. 관리자 센터의 직원 정보 건수는 읽기 전용 표시.
- 다음 15단계: AI 직원 생성·수정·비활성화 UI 및 라이프사이클 제어.

## 2026-10-12 15단계 — AI 직원 생성·수정·비활성화

- Windows EXE 네이티브 Tk `AI 직원 관리` 탭: 식별자·이름·설명·부서·직급·직무·역할 관리.
- 로그인한 관리자만 조작 가능; 초안 생성, 수정(식별자 고정), 비활성화, 초안 복귀.
- DB `lifecycle`을 안전한 `draft`/`inactive`로 유지. 활성 AI 실행은 향후 16~27단계에서 구현.
- 참조 무결성/부서 등 연결 삭제 방지; 기존 로컬 정보는 보존.
- Python 테스트, 실제 Tk GUI 버튼/데이터 보존 및 Windows EXE 자체 --self-test 후 GitHub 병합.

다음: 16단계 총괄 AI·부서장·직원 계층 연결.

## 16단계 — 채팅 안의 로컬 개발로 전환 (2026-10-12)

- GitHub 앱 연결 해제, 기존 로컬 `.github/workflows` 및 GitHub 관련 자동화 설정 파일을 패키지에서 제외. 원격 저장소의 예약 작업은 별도로 중지 필요.
- `ai_reporting_lines` 관계 테이블, 총괄 AI 단일성, CEO→부서장→직원 계층·부서 일치·비활성 관리자 및 하위 보고 관계 보호.
- Windows 데스크톱 `조직 지휘 체계` 탭의 트리·상급자 선택·배정·해제 버튼 추가.
- 기존 소유자·부서·직원 프로필 데이터와 호환되는 SQLite 비파괴 초기화.
- **pytest 141개 통과**, 실제 GUI 창 조작/재실행 및 로컬 SQLite self-test 통과, 호환 HTTP 독립 프로세스 검사 통과.
- 이 환경에서 Windows EXE는 미빌드. 로컬 Windows 빌드용 `build_windows_exe.bat` 제공.
- 다음 단계는 17단계 직원별 권한 및 도구 설정.

## 2026-10-12 17단계 — 로컬 AI 직원 권한·도구 설정

- 사용자 실행 경로는 데스크톱 Tkinter + 로컬 SQLite. GitHub API/원격 서버/네트워크 없이 진행.
- `desktop/access_policy.py`의 고정 권한·도구 목록과 필요 권한 매핑 도입. 동적 명령 실행 또는 외부 API 도구 없음.
- `ai_employee_capability_grants` / `ai_employee_tool_grants` 테이블에 직원별 명시적 허가를 원자적으로 저장. 기본값은 전체 거부.
- 비활성 직원에게 새 허가 금지; 비활성화 시 기존 허가 DB 트리거로 자동 취소(재활성화 시 자동 복원 안 함).
- `is_employee_allowed` / `require_employee_access`로 허가 없는 미래 실행 요청을 거부하는 정책 검사 도입.
- Tk `직원 권한·도구` 화면에서 직원 선택, 세부 허가 저장, 모두 취소, 재실행 후 유지 확인.
- 모델 실행 및 실제 도구 실행은 아직 미구현. Windows EXE 빌드 자체는 Windows PC에서 별도로 검증 필요.
- 다음 단계: 18단계 다양한 AI 모델 연결 인터페이스.

## 2026-10-12 18단계 — 다양한 로컬 AI 모델 연결 인터페이스

- GitHub 조회·업로드·커밋·병합·Actions 호출 없이 채팅의 로컬 소스만 변경.
- `desktop/model_runtime.py`: 표준 라이브러리 기반 로컬 프로세스 모델 어댑터(`llama_cpp`, `llamafile`); 여러 GGUF 모델·실행파일 프로필, 절대 경로 검사와 GGUF 형식 머리글 검사. 등록·검사·앱 실행 시 추론 프로세스를 자동 실행하지 않음.
- 명시적 '선택 모델 추론 시험' 클릭에서만 사용자가 지정한 로컬 실행파일을 `shell=False`로 호출. 제한 시간·출력 길이·토큰 수 검사, 실행 중 중단/로그아웃/종료 시 취소 신호, 오류 표시. 독립적 백그라운드 서버 없음. 신뢰 가능한 실행파일만 등록 필요.
- `desktop/storage.py`: `ai_local_models` SQLite 테이블 신규 추가 및 소유자만 목록·추가·수정·삭제 가능, 이름 중복 거부, 기존 계정·부서·직원·권한 데이터 비파괴 보존, 재로그인 후 재열기 검사.
- `desktop/app.py`: `로컬 AI 모델` 네이티브 관리 탭, 바로가기 선택기, 로컬 파일 선택, CRUD, 경로 검사, 명시적 추론 시험/중지/응답 표시.
- 소스 기준 자동 테스트 **174 passed**, 실제 Linux Tk 창에서 모델 CRUD·명시적 로컬 시험 프로세스 실행·재시작 확인, `python -m scripts.verify_offline_runtime` 소켓 차단 검사 통과, 개발용 HTTP 호환 테스트 통과.
- **검증 한계:** 테스트에는 CLI 호출 경로 확인을 위한 매우 작은 시험 실행파일을 사용함. 사용자 PC의 실제 llama.cpp/llamafile 및 GGUF 모델 추론, GPU 최적화, Windows EXE 빌드·실기기 검사는 미검증. 로컬 실행파일이 자체적으로 네트워크 접근할 가능성은 OS 차원에서 방화벽으로 제한해야 함.
- AI 직원별 모델 할당과 호출 기록은 아직 없으며, 이는 19단계 작업.


## 2026-10-12 19단계 — 직원별 모델 배정·호출 기록 (이 대화에서 로컬 개발)

- GitHub 조회·커밋·PR·병합·Actions 사용 없음. `aiwack-stage18` 오프라인 소스를 복사해 개발.
- 직원↔로컬 모델 관계 `ai_employee_model_assignments` 및 이력 `ai_model_call_history` 추가. 소유자만 관리; 비활성 직원은 새 모델을 배정할 수 없고 비활성 전환 시 기존 배정 자동 삭제. 사용 중인 모델 등록의 삭제 제한, 사용 이력 보존.
- `desktop/employee_model_runtime.py`: 관리자가 GUI에서 직접 시험을 눌렀을 때만 Stage18 로컬 CLI 어댑터 사용. 호출 시작·성공·실패·취소·시간 초과/소요 시간과 입출력 문자 수를 기록하며 질문·응답 본문과 실행파일 경로/표준오류는 DB에 미저장.
- Tk `직원별 모델·호출` 탭에서 직원/모델 선택, 배정/해제, 수동 실행/중지 및 이력 조회. 로그인 없이 접근 불가. 기존 소유자·회사·직원·권한·조직도 데이터 보존.
- 180개 pytest, 실제 Xvfb GUI 버튼/실행/재시작, 네트워크 소켓 차단 소스 GUI+DB 검사, 독립 데이터베이스 self-test 통과. Windows EXE/GGUF 실제 추론 미검증. 다음 20단계: 총괄 AI의 기본 응답 기능.


## 2026-10-12 20단계 — 총괄 AI 기본 로컬 응답

- `desktop/chief_runtime.py`: 총괄 AI 프로필과 소유자 인증을 확인하고, 로컬 CLI 모델을 요청 시에만 실행.
- `desktop/storage.py`: `read_chief_profile` 조회와 호출 이력 트랜잭션 안에서 `ceo` 역할 조건 재확인. 일반 직원이 총괄 AI 채팅 경로로 호출될 수 없도록 방어.
- `desktop/app.py`: `총괄 AI 대화` 전용 Tk 탭; 입력, 실제 로컬 출력, 응답 중단, 대화 화면 지우기, 모델 상태 조회. 로그아웃 시 대화 화면 초기화.
- 질문/응답의 원문은 SQLite에 미저장. 기존 19단계 호출 메타데이터 이력을 재사용. 자동 비즈니스 실행·이전 대화 자동 문맥 반영은 아직 미구현.
- `desktop/entry.py --self-test`에서 임시 SQLite로 CEO 역할·모델 연결 및 이력 생성/재로그인 검증(실제 AI 가중치 필요 없음).
- `tests/test_chief_chat.py`와 실제 Tk GUI 연동 스모크 테스트에서 로컬 시험 프로그램의 실제 실행/응답 표시 및 실패·시간초과·취소, 권한 거부 검증.
- 로컬 전용: GitHub 연결/업로드/커밋/PR/병합 없음. Windows EXE 바이너리와 실제 GGUF 추론은 이 환경에서 미검증.
- 다음: 21단계 총괄 AI의 회사 상태 조회.


## 2026-10-12 21단계 — 총괄 AI의 회사 상태 조회 (PC 로컬 전용)

- `desktop/storage.py:read_chief_company_status`가 **하나의 로컬 SQLite 읽기 트랜잭션**에서 단일 `ceo`의 초안(활성) 상태와 직원별 `company:read` 및 `local_company_reader` 허가를 함께 확인한 뒤 회사 프로필, 부서, 직원의 저장 상태 집계를 조회.
- `goals:read` 및 `local_goals_reader`를 모두 따로 허가한 경우에만 목표 목록/개수 제공. 최초 기본 허가는 전체 거부이며 총괄 AI를 해제하거나 비활성화하면 접근 불가.
- Tk `총괄 AI 대화` 탭에 실제 `회사 현황 조회` 버튼 및 `대화 질문에 회사 현황 포함` 선택형 체크박스 추가. 조회는 실시간 로컬 조회이며 자동 모델 실행 없음. 동의 후 발송에 한해 PC 로컬 CLI 모델 질문에 한정된 회사 데이터를 포함.
- SQL, 모델 비밀번호/소유자 정보, 진단 메모, 원문 로그, 재무 데이터는 조회 대상에서 제외. 회사 데이터는 출처/신뢰 경계를 명시해 LLM 컨텍스트에 전달하되 프롬프트 방어가 100% 완전하다고 보장하지 않음.
- **pytest 194개 통과**, Linux Xvfb 실제 GUI 클릭/재로그인 검증, 임시 SQLite 기반 `--self-test`, 네트워크 차단 자식 프로세스의 GUI/스토리지 검사 통과.
- GitHub 접속/커밋/PR/워크플로 사용 없음. Windows EXE 제작/실제 GGUF 추론 미검증. 다음 단계: 22단계 회사 목표와 업무 계획 저장.

## 2026-10-12 22단계 — 목표 연계 업무 계획 로컬 저장

- 기존 company_goals에 연계된 `company_work_plans`와 순서 보존용 `company_work_plan_steps` SQLite 테이블 도입. 기존 DB는 비파괴 스키마 추가.
- 관리자만 수동 계획 등록·수정·보관·삭제 가능. 각 계획에는 제목·설명·상태(draft/ready/archived)·1~30개의 순서형 작업 항목 저장.
- 연결된 계획이 있는 목표 삭제 방지, 직접 SQL 참조 무결성도 검사. 항목 변경은 하나의 SQLite 트랜잭션으로 처리.
- Tk `업무 계획` 탭에서 선택된 운영 목표에 계획 CRUD, 줄별 순서 편집 및 확인 후 삭제 구현.
- **업무 계획 항목은 실행 가능한 업무 레코드가 아님.** 실제 업무 생성·담당자 지정·자율 실행 기능은 후속 23~40단계.
- Github/외부 서버 연결, 클라우드 모델 호출, Windows EXE 원격 빌드 없음. 윈도우용 실행파일 자체는 이 환경에서 아직 미검증.
- 다음: 23단계 업무 생성 및 상태 관리.


## 2026-10-12 23단계 — 로컬 업무 생성 및 상태 관리

- 회사 목표/업무 계획 데이터와 별도로 `company_tasks`, `company_task_status_events`를 사용자 PC SQLite에 추가. 기존 테이블과 소유자 데이터 보존.
- 관리자 인증 뒤 업무 제목/설명·계획 연결을 등록·수정·수동 삭제하고 상태 `todo`/`in_progress`/`blocked`/`done`/`cancelled` 전환 및 로컬 감사 이력 기록. 잘못된 전환 및 계획 무단 삭제 차단.
- GUI에 새 `업무 관리` 탭을 추가하고 실제 버튼 조작과 창 종료·재실행 데이터 보존 점검. 작업 생성은 AI 모델을 자동 실행하지 않으며 할당/우선순위/실행은 후속 단계.
- GitHub 연결, 업로드, 원격 서비스 사용 없음. 로드맵 23/100, 실질 제품 추정 약 8% 유지.
- `python -m pytest -q`, `python -m desktop.entry --self-test`, Linux Tk 실 GUI, 소켓 차단 검사 및 ZIP 해제본 독립 재검증 결과는 `docs/STAGE23_VERIFICATION.md` 기록.
- 다음 개발: 24단계 업무 담당 AI 자동 지정. 사용자 승인 없이 실제 모델 실행하지 않음.


## 2026-10-12 24단계 — 업무 담당 AI 자동 지정 (로컬 전용)

- 기존 23단계 업무·목표·계획·직원 정보를 그대로 두고 SQLite에 `company_task_routing`, `company_task_assignments`, `company_task_assignment_events` 추가.
- 관리자가 업무별 부서/직무 조건 저장 및 `todo` 상태에서 자동 배정. 후보는 비활성화되지 않은 일반 직원/미분류 직원으로 제한하고, 조건을 모두 충족해야 함. 업무량(미완료 배정 수)이 적은 순, 동률이면 직원 ID 오름차순으로 선정.
- 기존 배정 반복 클릭은 결과 유지. 조건 변경·직원 비활성화·부서/직무 변경·관리자로 역할 변경 시 배정을 해제하고 감사 이벤트를 보존. 관리자 명시적 해제 지원.
- 담당자 자동 배정은 **로컬 데이터 저장만** 수행하며 AI 모델 호출·실제 업무 실행·인터넷 요청·과금 없음.
- 로컬 pytest, 자체 DB 재로그인 확인, Xvfb 실 GUI, Python 소켓 차단 검사 수행. Windows EXE 바이너리 자체는 이 환경에서 생성/실기기 검증하지 않음.
- 다음: 25단계 업무 우선순위 설정. 실질 완성도 ~8%는 인증된 진행 측정치가 아닌 주관적 추정치.

## 2026-10-12 25단계 — 업무 우선순위 설정 (로컬 전용)

- 기존 업무/계획/담당자 DB 행을 변경하지 않고 `company_task_priorities`, `company_task_priority_events` 테이블 추가. 기존 업무는 보통(normal)으로 읽으며 명시적 변경만 기록.
- 소유자 권한으로 `low`/`normal`/`high`/`urgent` 중 선택, 변경 이력 트랜잭션 저장, 잘못된 값/업무 번호 거부, 동일 값 반복 저장 무변경.
- 미완료 우선·긴급→높음→보통→낮음·업무 ID 순으로 업무 목록을 안정적으로 정렬. 완료/취소 업무는 뒤에 표시.
- Tk `업무 관리`에서 콤보박스·저장 버튼·정렬된 목록 열 추가. 기존 24단계 자동 배정과 독립, 모델/네트워크/자동 실행 없음.
- 실행 검증은 `docs/STAGE25_VERIFICATION.md` 참고. Windows EXE/실제 GGUF 추론은 미검증.
- 다음: 26단계 선행·후속 업무 의존성 관리. 실질 제품 완성도 추정 약 8%, 로드맵 25/100.

## 2026-10-12 26단계 — 선행·후속 업무 의존성 관리 (로컬 전용)

- 25단계 ZIP `AIWACK_Stage25_Local_Offline_Source.zip`을 압축 해제하고 `docs/progress.json`의 `next_step=26`을 확인한 뒤 개발함.
- SQLite 선행 관계 DAG, 순환 검사, 의존성 등록/해제/조회/변경 이력, 선행 완료 여부에 따른 수동 업무 상태 전환 제한을 구현함.
- 후속 업무가 시작/완료되면 선행 업무 재개 차단, 연결된 선행 업무 삭제 차단, 감사 기록 실패 시 트랜잭션 롤백을 적용함.
- 실제 Tk `업무 의존성` 탭에서 관계 등록·조회·해제, GUI 상태 전환 차단 및 재실행 보존 검사 추가.
- AI 자동 실행·외부 네트워크·GitHub 사용 없음. 다음 단계 27: AI 업무 실행기 제작.
- 테스트 수와 검증 결과는 `docs/STAGE26_VERIFICATION.md`를 참고. 실질 제품 완성도 약 8%는 비공식 추정치.

## 2026-10-12 27단계 — AI 업무 실행기 (관리자 확인·로컬 단발 텍스트 초안)

- 최신 26단계 ZIP의 `docs/progress.json` 26/100 완료, next 27을 실제 확인하고 27단계만 구현.
- 로컬 SQLite `company_task_runs` 신규 추가. 기존 테이블·업무 데이터 비파괴 유지. 기존 모델 호출 감사 이력과 함께 단일 트랜잭션으로 기록.
- 업무 상태 todo, 완료된 선행 업무, 활성 담당 직원, 부서/직무 적합성, 로컬 모델 연결을 원자적으로 검증한 뒤 수동 모델 실행. 실행 중 업무 중복/동시 실행 금지.
- 성공 후 완료 자동 처리 없음. 오류/취소/시간 초과는 차단 상태로 전환. 출력/프롬프트/오류 원문은 DB에 기록하지 않음.
- 실제 Tkinter 탭에 관리자 실행 확인, 실행·취소, 임시 응답, 실행 이력, 명시적 비정상 종료 복구 추가.
- GitHub, 클라우드 AI API, 외부 서버 사용 없음. Windows 실기기 EXE·실제 GGUF 모델 추론 미검증.
- 테스트 세부 결과: `docs/STAGE27_VERIFICATION.md`. 다음 28단계 결과물 저장 및 검수.

## 2026-10-12 28단계 — 업무 결과물 저장 및 검수

- 27단계 전체 누적 ZIP의 `docs/progress.json`에서 27개 완료, `next_step=28`을 확인하고 개발함.
- SQLite에 결과물 본문/제목/실행 ID/SHA-256/검수 상태 및 별도 검수 이력 테이블 추가. 기존 DB 스키마를 파괴하지 않음.
- 로컬 AI 성공 응답은 기본적으로 자동 저장하지 않음. 로그인한 관리자가 실행 화면에서 명시적으로 저장을 승인해야만 본문이 SQLite에 보관됨.
- 실행별 결과물은 하나만 저장하며 앱 API에서는 저장 후 본문 수정과 검수 결정 변경을 거부함. 검수는 승인/수정 요청/반려이며 업무 상태를 자동 완료하지 않음.
- `업무 결과물·검수` GUI 탭, 본문 조회, 검수 의견 및 검수 버튼 추가. 본문은 로컬 SQLite에 평문 저장되며 암호화되지 않음.
- 자동 테스트는 전체 304개를 3묶음(77+117+110)으로 나눠 모두 통과. 단일 전체 실행은 120초 제한으로 완료되지 않아 통과로 주장하지 않음.
- 실제 Tk GUI, 자체 검사, 네트워크 소켓 차단 GUI 검사 통과. Windows EXE 및 실제 GGUF 추론 미검증.
- 세부 검증은 `docs/STAGE28_VERIFICATION.md` 참고. 다음 29단계는 독립 업무 병렬 실행.


## 2026-10-13 29단계 — 독립 업무 병렬 실행

- 28단계 누적 ZIP의 `docs/progress.json`에서 28개 완료, `next_step=29` 확인 후 개발함.
- 기존 SQLite 업무 실행 단일 전역 실행 인덱스를 비파괴적으로 제거하고, 업무별·직원별 부분 UNIQUE 인덱스를 추가. `BEGIN IMMEDIATE`로 예약 원자성 보장, 동시 실행 최대 2개 제한. 기존 실행·감사 기록 보존.
- 같은 업무·같은 직원 중복 실행, 미완료 선행 업무, 3번째 병렬 실행 차단. 실행 중 직원/모델/보고 관계 변경 제한 강화.
- Tk 실행 화면에서 각각 관리자 확인 후 2개 병렬 실행, 선택 업무만 취소, 업무별 임시 초안 분리, 각 결과물 명시적 수동 저장을 구현함. 자동 완료/자율 스케줄링 없음.
- 로컬 실제 CLI 2개 동시 실행, 스레드 동시 예약·취소 격리, DB 재실행·기존 인덱스 마이그레이션, GUI 버튼 조작, 소켓 차단 검증 수행.
- Windows EXE와 실제 GGUF 추론 미검증. 로드맵 29/100, 실질 완성도 약 9~10%는 비공식 추정. 다음 30단계: 총괄 AI의 업무 지시·결과 회수 검증.
- 세부 명령과 결과: `docs/STAGE29_VERIFICATION.md`.


## 2026-10-13 30단계 — 총괄 AI의 업무 지시·결과 회수 검증

- 29단계 ZIP의 `docs/progress.json`에서 29단계 완료·다음 30단계를 확인하고, 기존 데이터·GUI·실행기를 유지하면서 확장.
- 총괄 AI가 로컬 모델로 지시 텍스트 초안을 작성하고, 관리자가 별도 버튼으로 승인할 때만 `company_chief_task_orders`에 불변 저장. 업무/담당자/총괄 AI 변경 시 승인 지시 실행 차단, 중복 실행 차단.
- 기존 직원 실행기의 SQLite 원자적 실행 예약과 연결된 `company_chief_task_dispatches` 이력 보존. 결과물은 28단계의 명시적 수동 저장을 재사용.
- 저장된 결과물만 총괄 AI에게 텍스트로 회수하여 검토 요청. 관리자가 검토 의견을 별도 저장/승인·반려, 업무 상태 자동 완료 없음.
- GUI `총괄 AI 지시·회수` 탭, 실제 Tk 버튼 테스트, 로컬 테스트 CLI와 소켓 차단 검증 추가. 지시·보고서·결과물 본문은 평문 SQLite, 실제 GGUF·Windows EXE 미검증.
- 다음 단계: 31단계 회사 상황 자동 점검. 실질 완성도 약 9~10%는 주관적 추정.


## 2026-10-13 31단계 — 회사 상황 자동 점검

- 최신 30단계 누적 ZIP의 `docs/progress.json`을 읽어 30/100 완료·31단계 미완료 확인 후 구현.
- SQLite 트랜잭션에서 업무 상태/담당자/검수/보고서/실행 지표를 일관된 시점의 건수로 집계. 점검은 업무·직원·모델 기록을 수정하지 않음.
- 관리자 로그인 시 최초 점검, 열린 Tk 창에서 5분 간격 점검, 로그아웃 시 타이머 취소. 새 `회사 자동 점검` 탭과 수동 점검/이력 화면 추가.
- 상태 변경 시 또는 최소 1시간 간격으로 이력 저장(수동 저장은 예외). 이름/본문/프롬프트를 제외한 집계 지표와 고정 코드만 저장.
- 실제 GUI, 소켓 차단, 기존 30단계 데이터 비파괴 마이그레이션, pytest 검증은 `docs/STAGE31_VERIFICATION.md` 참고.
- Windows EXE/실기기, 실제 GGUF 추론, 앱 종료 후 백그라운드 점검은 미검증/미구현. 다음 32단계 문제 및 사업 기회 감지.

## 2026-10-13 32단계 — 문제 및 내부 사업 기회 후보 감지

- 31단계 최신 누적 ZIP을 로컬에서 실제 압축 해제하고 `docs/progress.json`의 `next_step=32`를 확인함.
- `desktop/opportunity_detector.py`: 7개 고정 문제 규칙과 2개 내부 목표·계획 기반 기회 후보 규칙. 사용자 텍스트, 외부 시장 자료, 모델 추론 사용 안 함.
- `desktop/storage.py`: `company_detection_checks` 테이블, 관리자 인증, 스냅샷 읽기/중복 억제 저장/최대 100건 조회. 코드·건수만 저장하고 제목/본문/목표 ID 저장 안 함.
- `desktop/app.py`: 신규 22번째 `문제·사업 기회 감지` 탭과 로그인 직후·5분 주기 감지, 수동 저장 및 최근 기록 표시.
- `tests/test_company_detection.py`, `scripts/stage32_gui_smoke.py`: 후보 생성/해제, 문제 신호, 보안, 재실행, 실제 Tk GUI 테스트.
- 미구현: 외부 시장 수요/수익성 확인, AI의 새로운 사업 발굴/업무 생성, Windows EXE·GGUF 실제 검증.
- 다음 단계: 33단계 AI의 자발적 업무 생성.
- 검증: 개발본 3묶음 103+117+119=339 통과, 실제 Tk GUI 및 Python 소켓 차단 오프라인 검사 통과, 실제 31단계 DB 마이그레이션 통과. ZIP 압축 해제본도 339개 3묶음과 오프라인 검사 통과. 단일 전체 pytest 실행은 환경 제한으로 미완료. Windows EXE/GGUF는 미검증.

## 2026-10-13 33단계 — 자발적 업무 제안 및 로컬 AI 초안

- 실제 `AIWACK_Stage32_Local_Offline_Source.zip`과 `docs/progress.json`을 확인하고 32단계 완료/33단계 미완료 상태에서 이어서 구현.
- 관리자 로그인 후 5분마다 로컬 SQLite의 활성 목표·준비 계획·차단 업무를 검사해 중복 없는 제안 초안을 자동 저장. 자동 실제 업무 생성·실행 없음.
- 관리자 명시 승인 후에만 미배정 `todo` 업무를 원자적으로 생성. 거절/조건 변경/동시 스캔/재실행 방어, 원본 업무·계획 보존.
- 선택적 실제 로컬 총괄 AI 모델 JSON 초안 생성: 관리자 로그인 세션별 직접 동의 필요, 한 번에 하나씩 백그라운드 실행. 모델 출력은 초안 데이터이며 승인 없이 실행하지 않음.
- 테스트·실제 Tk GUI·오프라인 검사 결과는 `docs/STAGE33_VERIFICATION.md` 참조. Windows 실기기와 실제 GGUF 추론은 미검증.
- 다음 단계: 34단계 실행 가능성 및 우선순위 분석.

## 2026-10-13 34단계 — 실행 가능성 및 우선순위 분석

- 실제 최신 `AIWACK_Stage33_Local_Offline_Source.zip`의 `docs/progress.json`에서 33단계 완료/34단계 미완료 확인 후 구현. 기존 소스 및 사용자 데이터 구조 보존.
- `desktop/task_feasibility.py`: 출처 상태/업무 우선순위/계획 단계 수만 사용한 오프라인 규칙 기반 평가. 실행 준비 부족 사유·추천 우선순위·0~100 검토 점수와 근거 생성. AI의 실제 실행 가능성 판정은 아님.
- `desktop/storage.py`: 평가 이력 테이블 비파괴 추가, 관리자 전용 평가·조회·이력, 변경 시에만 추가 저장, 원본 조건 변경 시 stale 표시. 실제 업무·우선순위 자동 변경 없음.
- `desktop/app.py`: 기존 `자동 업무 제안` 탭에 검토 점수·준비 상태·추천 우선순위·근거·재분석 버튼, 점수순 정렬. 승인·거절 및 선택적 로컬 AI 초안 기능 유지.
- `tests/test_task_feasibility.py` 14개 신규 테스트, 실제 Tk GUI 검사, 기존 전체 회귀 테스트 및 소켓 차단 검사. Stage33 원본 코드로 생성한 실제 SQLite DB의 비파괴 업그레이드 확인.
- Windows EXE 실기기 및 실제 GGUF 추론 미검증. 자세한 결과는 `docs/STAGE34_VERIFICATION.md` 참고. 다음 단계는 35단계 복합 업무의 세부 계획 생성.

## 2026-10-13 35단계 — 복합 업무의 세부 계획 생성

- 실제 최신 Stage34 누적 ZIP 및 `docs/progress.json` 확인 후 다음 미완료 35단계 구현. 원본 기획과 기존 1~34단계 소스·데이터 스키마 보존.
- `desktop/task_breakdown.py`: 6~30개 준비 계획 단계의 규칙 기반 세부 업무 초안, 원본 지문, 순차 선행 조건과 관리자 확인용 완료 기준 생성. 실제 AI 추론이나 의미적 계획 수립은 아님.
- SQLite 초안/세부 항목 테이블과 관리자 전용 생성·거절·조회·명시 승인 API. 중복·원본 변경·동시 승인·부분 실패 방지. 승인 후에만 미배정 todo 업무와 의존성/상태 감사 이력 생성; 모델/업무 자동 실행 없음.
- 신규 Tk `복합 업무 세부 계획` 탭, 진입점 자체 검사, 35단계 실제 GUI 및 소켓 차단 검사 확장. 이전 Stage33 GUI 테스트의 탭 개수 검사를 새 탭 추가에 호환되게 변경.
- 테스트 상세 `docs/STAGE35_VERIFICATION.md`. Windows EXE 및 실제 GGUF 추론 미검증. 다음 36단계 정기 작업 스케줄러.

## Stage 36
Implemented opt-in offline interval scheduler, durable occurrences, Tkinter management tab, bounded due checks, no AI auto-execution. See STAGE36_VERIFICATION.md.


## 2026-10-13 Stage43 — 프로젝트별 협업 대화방

- Stage42 누적 ZIP 및 진행 기록을 검사하고 43단계를 구현. 기존 원본 기획/SQLite 데이터 파일 보존.
- `desktop/project_chat.py` 프로젝트 공간/참여자/메시지 영구 저장, 소속 부서와 무관한 협업, SQLite 삽입 시 참여/활성 상태 검증, 메시지 수정/삭제 방지.
- `desktop/storage.py` 관리자 전용 API 및 비파괴 스키마 초기화.
- `desktop/app.py` Tkinter 프로젝트 관리/참여/메시지 화면.
- `tests/test_project_chat.py`, `scripts/stage43_gui_smoke.py`와 오프라인 실행 검사 추가.
- 해당 기능은 관리자 대리 메시지 기록이며 자율 AI 메시지/현실 사업 운영 미구현.
- 검증 결과 및 한계는 `docs/STAGE43_VERIFICATION.md` 참조. 다음 44단계는 AI 회의 안건 및 참석자 관리.

## 2026-10-13 Stage45 — 회의 의견 수집·비교

- 실제 Stage44 누적 ZIP의 진행 기록(44 완료/45 다음)을 검증 후 45단계 신규 작업 수행. Tkinter·SQLite 로컬 프로그램 유지.
- `desktop/meeting_opinions.py`: 회의 예정 확정 뒤 안건/활성 참석자에 대한 찬성·보류·반대/근거/출처/대안을 1인·안건당 하나씩 원자 저장. SQLite 트리거와 유일 제약으로 중복/월권/수정/삭제 방지.
- `desktop/storage.py`: 관리자 권한 필요 API, DB 비파괴 초기화. `desktop/app.py`: 로컬 의견 작성/비교 탭.
- 비교는 제출 현황·입장 분포·의견 차이·미등록 참석자만 기술하며 자동 의사결정/승인/업무 배정 없음.
- `tests/test_meeting_opinions.py`: 29개 테스트; 전체 485개, 관련 82개 통과. Linux Xvfb GUI 버튼/재시작 검증 및 소켓 차단 검사 수행.
- 원본 SQLite/기획서 보존, 44단계 파일 누락 여부 및 ZIP 무결성 검사 결과는 `docs/STAGE45_VERIFICATION.md` 참조.
- Windows 실기기와 GGUF 모델 실제 추론 미검증. 다음 46단계: 회의 의사결정 및 후속 업무 배정.

## 2026-10-13 Stage48 — 회사 공동 지식 저장소

- 실제 Stage47 누적 ZIP의 `docs/progress.json`을 확인하고 48단계만 구현했습니다. 기존 데이터 및 원본 기획 보존.
- `desktop/company_knowledge.py`: 공통 지식 문서 9개 분류, 로컬 SQLite 영속 저장, 제목·본문·출처 검증, 원문 수정/삭제 제한 및 보관 처리.
- `desktop/storage.py`: 관리자 인증 API 및 비파괴 스키마 초기화. `desktop/app.py`: 회사 공동 지식 저장소 탭.
- `tests/test_company_knowledge.py`와 `scripts/stage48_offline_gui_smoke.py`: 신규 검증 및 오프라인 GUI 실조작.
- 자동 지식 활용·실제 직원 세부 권한·출처 검증·DB 암호화는 미구현. Windows 실기기와 실제 GGUF 추론 미검증.
- 실제 전체 테스트/검증 결과는 `STAGE48_VERIFICATION.md` 참조.

## 2026-10-13 Stage49 — 지식 검색·출처·접근 권한 관리

- Stage48 baseline progress 1–48 complete confirmed. Owner-managed SQLite-only literal search, provenance annotations (`unverified`), visibility and employee read grant previews added.
- Stage47 Markdown roadmap checkbox corrected; CSV/progress already indicated done.
- Verified 585 pytest cases, 17 network-blocked offline commands including native Tkinter GUI with restart persistence; details in `STAGE49_VERIFICATION.md`.
- No true employee principal or model-integrated ACL; no web source verification, network connections, cloud API or GitHub actions. Windows and GGUF not checked.

## 2026-10-13 Stage50 — 성과 평가와 업무 개선 제안
- 실제 완료/차단 업무의 상태를 근거로 관리자가 수동 평가 기록(점수, 근거, 교훈)을 등록하고 SQLite에 불변 보관.
- 회사 업무 상태별 건수와 취소 제외 완료 비율을 화면에 표시함 (AI 품질 및 사업 성과 추정치 아님).
- 기록된 평가를 참조하는 개선안을 생성, 소유자가 채택/반려 결정과 근거를 기록. 승인해도 실제 업무나 외부 행위 자동 실행 없음.
- 데스크톱 성과 평가·업무 개선 탭, 권한 검사, 재시작 복원, 중복·위변조 방지 테스트 추가.

## 51단계 — AI 작업 도구 등록 시스템
- 기존 50단계 ZIP과 `docs/progress.json` 확인 후 신규 구현.
- `desktop/tool_registry.py`: 12개 분류의 로컬 도구 등록 메타데이터 및 관리자 등록·조회·보관, SQLite 감사 이력.
- `desktop/storage.py`: 인증된 관리자만 호출 가능한 API; 기존 업무 실행기와 별도.
- `desktop/app.py`: 도구 목록·등록·보관 Tkinter 탭.
- 등록한 도구는 실제 실행되거나 권한이 추가되지 않음; 승인·실행은 이후 개발 대상.


## Stage52 — 도구 실행 권한 및 승인 검사 (2026-10-13)
- 관리자 요청·승인·반려 이력, 직원 권한/기존 도구 허가/도구 보관 상태를 재확인하는 SQLite 정책 사전 검사 및 Tkinter 화면. 도구 실행은 미구현.
- 전체 pytest 659 통과; 네트워크 차단 오프라인 검사 20/20 통과; Windows 실기기·GGUF 미검증.

## 2026-10-13 Stage54 추가 후속 — JSON 오프라인 자료 묶음
- 최신 54단계 진행 ZIP, progress 1–53 완료 확인 후 동일 54단계를 계속 개발. JSON 목록 기반 1~20개 로컬 파일 일괄 등록, 목록/파일 SHA-256 및 순서 불변 저장, 실패 전체 롤백.
- 신규 단위 테스트 18개와 Tkinter GUI 스모크 추가. 전체 pytest 741 통과; 네트워크 차단 GUI/독립 실행 24개 명령 통과.
- 실제 인터넷 수집 금지 및 미구현. 54단계 완료로 표시하지 않음. `STAGE54_BATCH_CONTINUATION_VERIFICATION.md` 참조.

### 2026-10-13 · Stage54 offline evidence drift continuation (partial)

- Rechecked original specification, requirements traceability, 100-step roadmap and `docs/progress.json` from latest cumulative ZIP.
- Implemented bounded offline evidence JSON drift hints and strengthened local file inspection; added Tkinter detail view, 12 unit tests and real Xvfb GUI smoke.
- Stage54 remains in progress because real internet research/collection is not implemented under external access prohibition. See `docs/STAGE54_DRIFT_CONTINUATION_VERIFICATION.md`.

## Stage54 follow-up — offline link review queue (2026-10-13)
- Source: latest Stage54 evidence drift cumulative ZIP; original specification, traceability, roadmap and progress reviewed.
- Added bounded read-only cross-capture link inventory; status counts and missing/archived/ambiguous local-copy candidates; no network access.
- Stage54 remains IN PROGRESS, 53/100 complete. See STAGE54_FOLLOWUPS_CONTINUATION_VERIFICATION.md.

## 2026-10-13 54단계 후속 — 로컬 HTML 링크 수동 검토 메모

- 기준 누적 ZIP: `AIWACK_Stage54_Offline_Followup_Queue_Continuation_Source.zip`.
- `desktop/research_followup_notes.py`: 이미 등록된 HTML 링크 URL에만 관리자 수동 검토 메모를 추가 전용으로 기록. `noted` / `deferred` / `reopen` 동작은 로컬 작업 표시이며 실제 웹 확인이나 출처 검증을 뜻하지 않음.
- SQLite `offline_research_followup_notes`: 삭제·수정 금지 트리거, 시간순 이력, 기존 자료 테이블/해시 변경 없음.
- `desktop/research_followups.py`: 최대 40개 표시 항목에 최근 메모를 덧붙이며 기존 우선순위/상태와 집계는 변경하지 않음.
- Tkinter: 링크 URL·메모 입력, 수동 검토 기록 버튼, URL별 최근 20건 이력 버튼.
- 원본 기획안 제12장 실제 도구 연결 완료 조건은 여전히 미충족. 인터넷 접속·실시간 자동 수집 미구현. 54단계 진행 중, 53/100단계 완료 유지.
- 검증 세부 내용은 `docs/verification_stage54_followup_notes/`에 기록.

## 2026-10-14 Stage54 추가 후속 — 자료 묶음 URL 위험 신호 등록 전 점검
- 최신 54단계 누적 ZIP의 5개 필수 원본/로드맵/진행 문서와 기존 코드 확인.
- 이미 구현한 저장 URL 오프라인 분류를 JSON 묶음 승인 이전에 연동. 사설 IP/숫자형 별칭/내부 호스트 등 수동 확인 경고. GUI 상세 및 승인 문구 강화.
- 외부 네트워크 접속·자동 자료 수집 없음. 기존 1~53 완료, 54 진행 중. 실제 테스트 결과는 `docs/verification_stage54_bundle_url_review/`에 별도 보존.


### 54단계 부분 구현: 오프라인 HTML base/refresh 이동 지시 사전 경고 (2026-10-14)

- 자료 묶음 등록 전 HTML의 `<base href>`와 `<meta http-equiv="refresh">` 중 URL 이동 지시를 텍스트로 분석. 최대 HTML당 8건 검사, 4건 예시 표시.
- 관리자 입력 URL을 기준으로 동일 출처·다른 출처·형식 오류로 구분하여 사전 검토 상세 화면과 승인 대화상자에서 경고. `base`는 기존 상대 경로 분석기에 적용하지 않음.
- 스크립트·템플릿 등 숨김 영역 무시, `javascript:`/`file:` 및 로컬·비표준 URL의 실행·열람 없이 형식 오류 표시. 단순 시간 재로드는 이동 지시에서 제외.
- 기존 파일 승인 토큰, 중복·출처 버전 비교, SQLite 스키마 및 관리자 명시적 승인 유지. 외부 서버/웹/DNS 브라우저 접근 일절 없음.
- HTML의 이동 지시 표기는 저장 문서의 **자체 주장**일 뿐 출처 안전·진위 증거가 아님. 실시간 인터넷 조사·자동 자료 수집 미구현으로 **54단계 미완료, 53/100단계 완료** 유지.
- 검증 및 제한: `docs/verification_stage54_navigation_directives/summary.md`.

## 2026-10-14 Stage54: HTML 내부 CSS 참조 정적 검사
- 최신 907파일 누적 ZIP에서 원본/요구사항·100단계 로드맵·진행 상태 확인. 기존 사전 검토의 CSS 참조 누락 영역만 보완.
- `<style>`/`style=` 안 `url()`과 단순 `@import` URL을 12건/HTML까지 검사하여 URL을 열지 않고 대상 호스트만 표시. CSS 실행·외부 조회 없음.
- SQLite 스키마 및 기존 자료 무변경, 기존 사전 승인/재검토 로직 보존. 테스트 결과/제한은 `docs/verification_stage54_inline_css/summary.md`.


### 54단계 부분 개발: 오프라인 자료 묶음 **목록 생성 중 파일 변경 거부** (2026-10-14)

자료 묶음 JSON 목록 생성 시 선택한 TXT/MD/HTML 원본 파일 최대 20개를 순차 판독한 뒤,
**목록 저장 직전에 모든 원본을 한 번 더 확인**합니다. 원본의 SHA-256·바이트 크기가
달라졌거나 누락·심볼릭 링크 교체로 재검사할 수 없으면 목록 생성을 거부합니다.
기존 목록의 형식·저장 위치·덮어쓰기 방지·관리자 승인 및 SQLite 구조는 변경하지 않습니다.
파일 검사 사이의 변경을 줄이는 최선 노력 검증이며 **원자적 파일시스템 스냅샷은 아닙니다.**
로컬 파일 작업만 수행하며 원격 웹 조사/자동 수집/출처 인증은 하지 않습니다.
기존 **53/100 완료, 54단계 진행 중** 유지. 세부 검증은
`docs/verification_stage54_manifest_stability/summary.md`를 참고하세요.
