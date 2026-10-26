# AIWACK 실제 제품·조직·전사 모델 운영 개발 인수인계

- 원본 기존 Windows 10/11 Tkinter/SQLite/PyInstaller EXE와 실제 사용자 GGUF 모델 유지.
- 신규 company_approved_real_products.py: 직원/총괄 실모델·관리자 이중 승인 원본을 실제 .py/.md/.txt 파일로 제작, 문법·SHA256·영속 원본 확인. AI 코드 실행/출시/전송 자동화 없음.
- 신규 company_chief_staff_strategy.py: 실제 실패 직원 모델 실행으로 총괄 GGUF 인력 조정 제안 1건, 관리자 검수/별도 기존 직원 이동 최종 승인 요구. 모델/부서 자동 변경 금지.
- 신규 company_owner_operating_rounds.py: 승인된 직원 GGUF 작업 1~30건과 부서장 전달 승인된 총괄 GGUF 회수 1~10건을 소유자 실행 회차 한 번에 처리, 중단 안전/영속 감사. 자동 승인·재실행·금전 행동 없음.
- 신규 company_owner_completion_tabs.py: 한국어 GUI. 기존 company_native_owner_workflows.py / storage.py / build_windows_exe.bat 연동, docs/automation_full_handoff.md 누적 기록.
- 전체 원본 개발 미완료. Windows EXE/실GGUF/T01~T20 통합검증·오류 수정 NOT_RUN. 역사 1099/1171 ZIP 보존형 병합, 실제 24시간 중단 복구, 외부 PG·환불·은행·고객 전달, 15부서31AI30업무 완전 자율 운영 등의 요구는 남음. 공식 100단계 054 및 056~086도 전부 완료로 주장하지 말 것.
- 순서 전체 개발 먼저 → 전체 Windows/모델/사업 통합검증 → 오류 일괄 수정 → 전체 재검증. 추가 개발은 새 브랜치 없이 최신 main HEAD 재조회 후 expected SHA·비강제 fast-forward로만 반영.
