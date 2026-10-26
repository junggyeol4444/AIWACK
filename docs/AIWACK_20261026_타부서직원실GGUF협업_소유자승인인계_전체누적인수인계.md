# AIWACK 실제 직원 GGUF 부서간 협업·승인된 의견 인계 개발

대상: 기존 junggyeol4444/AIWACK Windows 10/11 Tkinter/SQLite/PyInstaller EXE.
**신규 실제품**
- company_peer_consultations.py: 기존 todo·배정 직원 업무에 대해 서로 다른 부서 동료 직원의 실제 GGUF 호출. 모델 ID/근거·출력 SHA256/SQLite 호출 감사, 실패 후 중복 호출 차단, 개별 소유자 승인/반려 기록.
- company_peer_context.py: 기존 LocalStore.begin_task_execution에서 승인된 동료 AI 의견을 450자 예산 범위로 담당 직원 실제 GGUF 프롬프트에 비신뢰 참고자료로 전달; 승인 없는 의견·모델 감사 불일치·변경된 업무/모델은 배제.
- company_owner_peer_consultation_tabs.py: 한국어 관리자 모델 실행, 조회, 승인/반려 GUI.
**기존 수정**
- company_native_owner_workflows.py: 실행·취소 백그라운드 연결 및 GUI 탭
- storage.py: 업무 프롬프트 참고 인계 및 LocalStore API
- build_windows_exe.bat: 신규 모듈 3개 PyInstaller 포함
- docs/automation_full_handoff.md: 전체 누적 인수인계

총괄 원본 지시·실제 승인·업무 실행 별도 유지. 미승인 모델 자동 호출, 가짜 AI 결과, 계정 사용·실거래/고객 발송, 기존 DB·원본 삭제 금지. 전체 개발 미완료 상태. Windows 실기기 EXE/진짜 GGUF/전체 T01~T20 통합검증·일괄 오류수정 **NOT_RUN**.
남은 개발: 15부서31AI30업무 장기 자율 협업 전체 완성, 24시간 안전한 장애 복구, 승인형 실제 결제·환불·은행·고객 연동, 역사 원본 ZIP 1,099/1,171개 보존형 전수 통합.
