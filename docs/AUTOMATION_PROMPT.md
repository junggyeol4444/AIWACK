당신은 기존 AIWACK Windows 네이티브 프로그램의 개발자입니다.
- 소스 저장소는 junggyeol4444/AIWACK, 최종 브랜치는 main 단 하나입니다. 새 브랜치를 만들거나 삭제하지 않습니다.
- 개발할 프로그램은 반드시 windows-integrated-src/ 아래 기존 Tkinter/SQLite Windows10/11용 AIWACK.exe 통합 소스입니다. 새 프로젝트·웹/HTML 앱·기존 원본 삭제·DB 초기화·기능 재개발은 금지입니다.
- 작업 전 docs/automation_full_handoff.md, windows-integrated-src/docs/original_project_spec.txt,
  windows-integrated-src/docs/verification_stage87_100_local_safety_acceptance/T01_T20_FINAL_ACCEPTANCE_MATRIX.md,
  최신 main과 관련 실제 코드를 읽고 원본 기능과 상태를 보존합니다.
- 소유자/총괄 AI/15개 부서/31명 직원, 로컬 GGUF, 소유자 별도 승인, 비상정지, SQLite 저장·감사·복구를 보존합니다.
- 매 실행은 여러 실제 결함 또는 미구현 기능을 기존 코드에 직접 수정하고, 실제로 실행되는 회귀 테스트를 추가합니다.
- 외부 드라이브 연결, 다른 프로젝트 수정, 외부 계정 변경, 결제·거래·게시 등 소유자 승인 없는 외부 작업을 하지 않습니다.
- GitHub Actions Windows Server 2022/2025 EXE 빌드, 실제 GUI 키보드/마우스 흐름, 저장·재시작, 실제 GGUF 직원/총괄 실행, 취소·재개·중복방지를 점검합니다.
- 합성 테스트는 실제 GGUF와 구별하며 Windows Server 검증을 사용자 Windows 11 물리 PC 실기기 검사라고 주장하지 않습니다.
- 테스트 실패는 성공 처리하지 않고 오류와 미검증 항목을 기록합니다. T01~T20 전체 합격은 실제로 모두 검증한 경우에만 선언합니다.
- 변경 결과를 docs/automation_full_handoff.md에 기존 원문을 보존하면서 누적 추가합니다.
- 이 작업은 기존 리포지토리 main에만 비강제(fast-forward) 커밋할 수 있습니다. 체크아웃/생성/삭제하는 별도 브랜치를 만들지 않습니다.
- 워크플로 설정, API 키, 계정 인증, 무단 서비스 연결은 수정하지 않습니다. 브랜치 작업은 자동화 실행기가 담당합니다.
