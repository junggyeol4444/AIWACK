# AIWACK 19단계 검증 기록 — 직원별 로컬 모델 배정과 호출 이력

기준: 2026-10-12. 사용자의 PC가 아닌 개발 샌드박스에서 검증했습니다.

## 구현 범위

- **네이티브 Windows 데스크톱 소스** `desktop/app.py`에 `직원별 모델·호출` 탭 추가. 로컬 직원 프로필↔모델 설정 배정 및 해제, 관리자 수동 실행, 실행 중단, 호출 기록 목록 조회.
- SQLite `ai_employee_model_assignments`: 직원별 단일 모델 ID, 비활성 직원 배정 거부, 비활성화 시 기존 배정 자동 삭제, 사용 중인 모델 등록 삭제 차단.
- SQLite `ai_model_call_history`: 호출 기록을 시작한 즉시 기록하고 성공/실패/취소/시간 초과를 완료 상태로 기록. 사용자 입력·생성 출력·실행파일 경로·오류 원문을 로그에 기록하지 않음. 모델 등록을 해제하거나 삭제해도 이력 보존.
- 관리자 계정 로그인과 `agents:manage` 권한으로 배정·조회·시작 제어. 직원별 도구 허가 키와는 별도이며 직원의 자율 업무 실행은 제공하지 않음.
- 로컬 모델 실행은 `desktop/employee_model_runtime.py`에서 명시적 사용자 실행 시에만 Stage18의 `subprocess` 어댑터를 호출. GitHub·웹 API·HTTP 서버는 앱 실행에 필요하지 않음.

## 수행한 검증

1. `python -m pytest -q` — **180 passed**. 직원별 모델 배정·재열기, 중복/잘못된 모델·비활성 직원 거부, 기존 DB 업그레이드/참조 보호, 실제 로컬 CLI 호출 및 프롬프트/응답 DB 미저장, 실패/시간 초과/중단 감사 기록 포함.
2. `python -m desktop.entry --self-test` — 임시 SQLite에서 관리자 등록, 직원·모델 배정·감사 기록 저장 및 재로그인, 로그 보존·연결된 모델 삭제 차단 검사.
3. `xvfb-run -a python -m scripts.desktop_gui_smoke` — 실제 Tk 창 생성, 관리자 로그인, 직원 모델 배정과 로컬 CLI 시험 버튼, 응답·로그 테이블, 프로그램 종료 후 재로그인·재조회·해제 확인.
4. `python -m scripts.verify_offline_runtime` — 네트워크 소켓 호출이 거부되는 Python 프로세스에서 실제 엔트리 `--self-test`와 GUI 스모크 검사 실행. 앱의 Python 실행 경로 검사이며 시스템 방화벽을 대신하지 않음.
5. `python scripts/real_smoke_test.py` — 레거시 개발용 API 호환 프로세스 검사(최종 사용자 EXE에서는 서버 미시작).
6. `python scripts/next_step.py` — 19/100단계 완료·다음 20단계 표시.

## 검증하지 않은 항목

- 실제 Windows `.exe` 빌드·실행 및 사용자의 Windows PC에서 버튼 직접 조작.
- 진짜 llama.cpp/llamafile + GGUF 가중치를 통한 의미 있는 AI 추론(테스트는 의도적으로 작은 로컬 실행파일만 호출함).
- 사용자가 선택한 외부 실행파일의 네트워크 행위; 앱의 Python 레벨 네트워크 차단 검사와 운영체제 방화벽은 별개.
- 자율 AI 직원 실행, 총괄 AI 대화 기능(20단계), 병렬 작업, 사업·판매·매출.

## 로컬 배포

이 ZIP에는 사용자 인증 DB, 외부 AI 실행파일/가중치, GitHub 설정을 포함하지 않습니다. Windows에서 이미 Python/PyInstaller가 준비돼 있는 경우 `build_windows_exe.bat`로 **사용자 PC에서만** 빌드할 수 있습니다. 자동 다운로드·업로드는 하지 않습니다.
