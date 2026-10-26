# AIWACK 실제 부서장 GGUF 개별 중간 검토 — 전체 누적 인수인계

원본: 기존 junggyeol4444/AIWACK Windows 10/11 한국어 Tkinter·SQLite·PyInstaller.
신규: windows-integrated-src/desktop/company_department_head_review.py / company_owner_head_review_tabs.py.
연동 수정: company_operations.py, chief_task_runtime.py, storage.py, company_native_owner_workflows.py, company_office_gui.py, build_windows_exe.bat.
총괄 실GGUF 제안→소유자 승인→직원 실GGUF 결과물→같은 부서장 실GGUF 검토→소유자 개별 전달 승인→총괄 실GGUF 최종 검토→소유자 최종 승인. 일반 기존 30업무/직원-총괄 업무 경로 보존. 검토 실패 재시도/모델 임의 교체/결과물 자동 승인·매출 기록·실거래 없음.
SQLite 모델 호출 근거/출력 해시/원본 부서장 관계/관리자 승인 기록 연결, 한국어 GUI 조회/승인/반려.
**개발 중:** Windows EXE 실행·실GGUF·T01~T20 통합검증, 오류 수정 NOT_RUN.
**잔여:** 전사 15부서31AI30업무 장기 자율 협업 완성, 24시간 복구, 외부 결제·환불·은행·고객 실연동, 1,099/1,171 원본 ZIP 보존형 전수 통합.
