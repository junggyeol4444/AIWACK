# AIWACK — AI Autonomous Company

원본 **「자율 운영형 AI 회사 시스템 개발 기획안」** 을 기준으로 진행하는 로컬 실행형 다중 AI 회사 시스템 프로젝트입니다.

> **현재 8/100단계** — 개발 중인 초기 프로토타입입니다. 서버·데이터베이스 마이그레이션·로컬 진단 화면·실제 데이터 저장/복구까지만 동작합니다. **총괄 AI, 직원 AI, 자율 업무 생성, 사업 및 매출 기능은 아직 없습니다.**

## 내가 직접 PC에서 구동해보기

**Windows**: [코드 ZIP 다운로드](https://github.com/junggyeol4444/AIWACK/archive/refs/heads/main.zip) 후 압축 풀고, Python 3.11 이상이 준비된 PC에서 `start_windows.bat`을 더블클릭합니다. 처음 실행 시 Python 패키지 설치가 진행됩니다. 터미널에 `Uvicorn running on http://127.0.0.1:8000`가 나타나면 브라우저에서 [http://127.0.0.1:8000/diagnostics](http://127.0.0.1:8000/diagnostics)를 엽니다.

**macOS / Linux**: Python 3.11 이상을 준비하고 터미널에서 `sh start_mac_linux.sh` 를 실행합니다. 위 주소에서 화면을 확인합니다.

**개발자 명령어** (Python 3.11 이상):

```bash
python -m pip install -e '.[dev]'
python scripts/launch_local.py
```

### 실제 기능 확인 (단순 테스트 코드 통과와 구분)

1. `/diagnostics` 페이지에 **API 상태 `ok` 및 DB 상태 `ok`**가 표시되는지 확인합니다.
2. 메시지를 입력하고 **메시지 저장** 버튼을 누릅니다. 성공 문구가 표시되어야 합니다.
3. 터미널에서 `Ctrl+C`로 서버를 종료하고 다시 시작합니다.
4. 같은 페이지에서 앞서 저장한 메시지가 유지되는지 확인합니다.
5. 이 성공은 **프로그램 서버와 로컬 저장 기능**이 정상이라는 의미이지, AI 회사 전체가 작동함을 증명하지 않습니다.

**주의:** 인터넷 외부에 노출하지 마세요. 진단 API에는 아직 사용자 인증이 없습니다. 기본 실행 주소는 내 PC에서만 접근 가능한 `127.0.0.1`입니다. 개인 정보나 비밀번호를 입력하지 마세요.

## 실제 환경 검증

아래는 서로 다른 검사입니다.

```bash
python -m pytest -q                    # 코드/구조 테스트
python scripts/real_smoke_test.py      # 실제 서버 subprocess, HTTP, DB, 재시작 검사
```

검증 로그: [docs/RUNTIME_VERIFICATION.md](docs/RUNTIME_VERIFICATION.md). 로컬 SQLite만 검증했습니다. PostgreSQL 연결/배포는 미검증입니다.

## 진행 및 예약 개발

- [원본 개발 기획서](docs/original_project_spec.txt)
- [100단계 계획](docs/roadmap_100.md) · [작업 기록](docs/WORK_LOG.md)
- [GitHub Actions CI](.github/workflows/ci.yml) / [예약 개발](.github/workflows/hourly-development.yml)
- 예약 시각: **한국시간 매시 30분**, PC 전원과 독립적으로 GitHub에서 실행됩니다. AI 코딩을 사용하려면 저장소 Secret `OPENAI_API_KEY`를 별도로 승인·등록해야 합니다. 등록 전에는 안전하게 테스트 및 상태 확인만 합니다.
- AI가 작성한 단계는 변경 브랜치 및 PR로 제안하며 `main` 자동 병합은 하지 않습니다.

## 기술 환경

- Python 3.11+, FastAPI, SQLAlchemy, Alembic
- 개발 DB: SQLite 파일 `dev_company.sqlite3`
- 향후 운영 DB: PostgreSQL (미연결)
- 비밀값 및 로컬 DB 파일은 GitHub에 올리지 않습니다.

**다음 단계: 9단계 — 회사 소유자 계정 및 기본 권한 구성.**
