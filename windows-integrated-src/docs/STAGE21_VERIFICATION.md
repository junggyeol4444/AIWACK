# 21단계 — 총괄 AI의 회사 상태 조회 검증 기록

- 개발 방식: ChatGPT 대화의 로컬 소스에서 진행. GitHub에 접속하거나 커밋/병합하지 않음.
- 저장소: 사용자의 `%LOCALAPPDATA%\AIWACK\aiwack.sqlite3` (Windows). 계정 및 기존 데이터 무손실 스키마, 새 테이블 없음.
- 핵심 구현: `desktop.storage.LocalStore.read_chief_company_status`, `desktop.company_status`, 총괄 AI GUI 조회 버튼과 선택형 컨텍스트 포함.
- 허가 경계: 소유자 로그인 + 총괄 AI(ceo) 역할 + draft 상태 + `company:read` 및 `local_company_reader`; 목표는 `goals:read`와 `local_goals_reader` 둘 다 필요. 최초 거부, 비활성/역할 해제/권한 취소 시 접근 차단.
- 조회 범위: 회사명·설명·운영 방향, 부서 이름(최대 15개) 및 전체 개수, 직원 초안/비활성 건수, 별도 허용된 목표의 제목·상태(최대 15개) 및 건수. 실제 직원 모델/자율 AI 실행 현황이 아님.
- 모델 실행은 **관리자의 수동 발송**에서만 일어남. 체크박스 비선택 시 이전과 같은 독립 질문. 선택하면 승인된 SQLite 회사 현황을 표시된 구분자로 구성하여 로컬 CLI에 전달. 회사 텍스트가 AI 지시로 오인될 위험을 완전히 제거할 수는 없음.
- SQL은 하나의 읽기 트랜잭션을 사용하며 상태 조회는 데이터베이스를 수정하거나 호출 이력을 남기지 않음. 실제 모델 호출의 메타데이터는 이전 19단계 기록에 저장됨. 소유자 비밀번호·진단 메모·질문/응답 본문은 모델 컨텍스트에 넣지 않음.
- 코드 테스트: `python -m pytest -q` → **194 passed**.
- 임시 SQLite EXE 엔트리 자체 검사: `python -m desktop.entry --self-test` → 종료 코드 0.
- Linux 네이티브 Tk 직접 조작: `xvfb-run -a python -m scripts.desktop_gui_smoke` → PASS (현황 버튼 거부·허용, 회사 정보 실표시, 로컬 에코 실행, 재로그인 데이터 유지).
- 네트워크 차단 검사: `python -m scripts.verify_offline_runtime` → PASS (자식 프로세스의 Python 소켓 연결 차단; OS 전체 방화벽 또는 사용자가 지정한 외부 실행파일의 통신 차단은 아님).
- 실제 GGUF 추론 성능과 Windows EXE 빌드/Windows PC 구동은 **이 Linux 개발 환경에서 검증되지 않음**. 소스 ZIP은 Windows EXE가 아님.
- 미구현: 회사 목표별 업무 계획 생성, AI 자율 스케줄러/작업 도구 실행/수익 사업, 웹·클라우드 연동.
