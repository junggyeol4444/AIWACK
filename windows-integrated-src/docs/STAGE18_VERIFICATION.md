# 18단계 — 로컬 모델 연결 인터페이스 검증

- 테스트 환경: 2026-10-12, 이 대화의 Linux Python 실행 환경. Windows 실행 파일을 생성하거나 테스트한 것은 아닙니다.
- `python -m pytest -q`: **174 passed**.
- `python -m desktop.entry --self-test`: 별도 테스트 DB에서 기존 계정·직원·권한 기능과 로컬 모델 프로필 생성/수정/삭제/재시작 검사, 성공 종료.
- `xvfb-run -a python -m scripts.desktop_gui_smoke`: 실제 Tk 창 조작, 로컬 모델 경로 등록/수정/검사, 로컬 임시 CLI 프로세스 호출, 결과 수신, 재로그인 후 설정 유지/삭제, 기존 관리자·부서·직원 기능 회귀 점검.
- `python -m scripts.verify_offline_runtime`: Python 자식 프로세스의 네트워크 소켓 차단 상태에서 self-test와 실 GUI 테스트 모두 성공.
- `python scripts/real_smoke_test.py`: 이전 개발용 HTTP 서버의 호환 테스트 성공 (사용자 EXE 실행 경로는 아님).
- 모델 프로세스 계약 테스트는 실제 OS 프로세스/인자/시간 초과/취소를 검사합니다. 시험 프로그램이 출력하는 `LOCAL_RESPONSE`는 **실제 AI 추론 결과가 아닙니다**.
- 실제 모델 파일의 GGUF 헤더만 검사하며 전체 모델 정상 여부는 검증하지 않습니다. 사용자 제공 llama.cpp/llamafile 엔진 및 실제 모델의 응답 정확도/속도는 아직 시험하지 못했습니다.
- 이 소스 ZIP에는 `AIWACK.exe`, GGUF 가중치, llama-cli, llamafile, PyInstaller, 개인 SQLite 데이터베이스, 클라우드 API 자격증명, GitHub 설정이 포함되지 않습니다.
- PyInstaller는 Windows PC에 미리 설치되어 있어야 하고, `build_windows_exe.bat`는 별도의 인터넷 설치 없이 빌드·EXE 자체 검사하도록 작성했습니다. 그 Windows 테스트는 아직 수행하지 않았습니다.
- 도구로서 선택한 로컬 실행파일이 네트워크를 스스로 사용하는지까지 Python socket 차단 검사가 보장하지 않습니다. 네트워크 사용이 금지된 환경에서는 신뢰할 수 있는 로컬 엔진을 선택하고 OS 방화벽도 설정하세요.
