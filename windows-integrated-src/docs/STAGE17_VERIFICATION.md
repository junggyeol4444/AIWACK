# AIWACK 17단계 — 로컬 직원 권한·도구 설정 검증 기록

검증일: 2026-10-12. 운영체제: 이 대화의 Linux 실행 환경, Python 3.13.

## 구현 범위

- `desktop/access_policy.py`: 직원별 허용 가능한 작업 권한/향후 도구 종류를 미리 정의하고 유효성을 확인. 외부 서버 URL, 쉘 실행, 무제한 임의 도구 등록 불가.
- `desktop/storage.py`: SQLite 기반 직원별 허가 목록(기본 거부), 저장·조회, 권한 부족 시 거부, 직원 비활성화 시 허가 자동 철회, 다시 활성화해도 자동 복원하지 않음.
- `desktop/app.py`: 관리자 로그인 후 `직원 권한·도구` 탭에서 직원 선택, 권한·도구 체크, 저장, 전체 취소 및 오류 표시.
- `desktop/entry.py`: 별도 테스트 DB로 프로그램 시작/종료 중 저장·로그인·직원 접근 정책을 확인하는 자체 검사.
- `tests/test_employee_access.py`: 관리자 인증, 저장 원자성, 직원 간 격리, 비활성 직원 제한, SQL 직접 조작 시 방어, 이전 데이터 보존, 잘못된/중복/미허가 도구 방어.
- `scripts/desktop_gui_smoke.py`: 실제 Tk 창에서 버튼을 누르고 다시 열어 설정 확인, 잘못된 도구 저장 거부, 권한 모두 취소.

## 실제 이 환경에서 실행한 명령과 결과

- `python -m pytest -q` — **157 passed**.
- `python -m desktop.entry --self-test` — 종료 코드 0. 별도 생성 SQLite 파일에 기록 후 인스턴스를 교체하여 데이터와 권한 상태 검사.
- `python -m scripts.verify_offline_runtime` — **PASS**. `sitecustomize.py`에서 Python의 외부 socket 연결을 차단한 별도 프로세스로 EXE용 저장 검사와 `xvfb-run` 실제 Tk GUI 검사 둘 다 실행.

## 아직 검증하지 않은 것

- 이 환경은 Windows가 아닙니다. 이번 결과물은 **Windows EXE가 아니라 소스 ZIP**입니다. Windows에서 EXE 생성/실행·글꼴·보안 제품/실사용 PC 검증은 하지 않았습니다.
- 실제 AI 모델 추론, 도구 실행, 외부 결제/서비스는 **구현하지 않았습니다**. 17단계는 권한·도구 **설정 및 검사** 기능입니다.
- 소켓 차단 테스트는 전체 운영체제 방화벽 또는 외부 프로세스 트래픽을 검증하는 테스트가 아닙니다.
- SQLite 파일 암호화, 다중 사용자 로그인, AI 직원 자동 실행은 후속 기능입니다.
- 기존 데이터나 비밀번호는 ZIP에 포함되지 않습니다. 사용자 PC의 `%LOCALAPPDATA%/AIWACK/aiwack.sqlite3`는 새 버전에서 계속 재사용됩니다.

GitHub 저장소, GitHub Actions, GitHub API는 빌드/실행 필수 구성 요소가 아닙니다. 이 소스 ZIP에 `.github` 파일이 포함되지 않으며, 원격 서비스 호출 없이 개발·검증했습니다.
