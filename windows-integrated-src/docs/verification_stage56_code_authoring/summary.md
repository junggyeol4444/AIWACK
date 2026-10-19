# AIWACK 56단계 개발·검증 (2026-10-14)

## 기초 파일 점검
- 기준 최신 누적 파일: `AIWACK_Stage55_Offline_Browser_Continuation_Source.zip` (1067개 파일)
- 실물 검토: `docs/original_project_spec.txt`, `docs/requirements_traceability.md`, `docs/roadmap_100.csv`, `docs/roadmap_100.md`, `docs/progress.json`
- 원본 56단계: **AI 코드 작성·수정 기능**. 57단계: **격리된 코드 실행 및 테스트**. 54단계 인터넷 조사/자동 수집은 계속 **BLOCKED**.

## 실제 구현 내용
- 관리자 직접 입력 또는 로컬 AI 모델 CLI로 생성하는 Python 코드 초안 화면 (Tkinter).
- 로컬 모델 등록 ID를 사용자 자신이 선택하고 **명시적으로 생성 버튼 클릭**. 유효한 Python만 코드 초안으로 인정. 모델 응답은 저장·실행하지 않음.
- 별도의 정적 AST 구문 검사 및 통합 diff 비교·승인 필요. 승인 때까지 파일 및 SQLite 코드 이력 미변경.
- 데이터 폴더의 `code_drafts/` 단일 `.py` 파일에만 생성/버전 수정. `.py` 파일명 검증, Windows 예약 이름/경로 이동·symlink·hardlink 차단, 파일 SHA-256 비교, 버전 충돌 검사.
- SQLite에 버전 원본/해시/출처 종류(관리자가 검토한 모델 초안 vs 직접 입력)를 보관하며 수정/삭제 불가 트리거로 이력 보호.
- 생성 코드 자동 실행·컴파일·import·설치 금지. 프로젝트 자체 소스 파일 수정 기능 아님. 57단계 실행 기능과 엄격히 분리.
- **실제 모델 AI 생성은 검증하지 못함.** 모델 호출 테스트는 mock 응답을 사용했고 실제 GGUF 및 Windows 검증 대기. 따라서 56단계 **BLOCKED / 부분 구현**이며 다음은 57단계로 이동.

## 보존/보안 범위
- 사용자 PC에 접속하거나 설치/설정 변경하지 않음.
- 외부 사이트·GitHub·클라우드 API 호출하지 않음.
- 로컬 모델 CLI 자체의 네트워크 통신을 운영체제 수준에서 봉쇄한다고 주장하지 않음. 신뢰된 사용자 보유 런타임만 선택해야 함.
- Python AST 구문 검사 = 안전성·동작 정확성 검증 아님. 새로 생성된 코드라도 수동 검수 필요.
- SQLite와 OS 파일 시스템 사이에 전체 트랜잭션 원자성은 없음; 중단 시 운영자 점검 필요.
- 원본 기획안, 요구사항 추적표, 기존 사용자 SQLite 데이터 보존 검증은 패키지 검사에서 별도 기록.

## 실증 범위
- `pytest -q tests/test_stage56_code_authoring.py`
- `xvfb-run -a python -m scripts.stage56_code_authoring_gui_smoke`
- `python scripts/next_step.py`
- 전체 pytest와 네트워크 차단 GUI 검사 결과: 같은 폴더의 개별 로그에서 확인
- Windows 10/11 실기기/EXE, 실제 GGUF 모델 성능·추론, 장시간 운영: **미검증**
