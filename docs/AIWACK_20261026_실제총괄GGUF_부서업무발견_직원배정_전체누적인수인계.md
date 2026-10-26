# AIWACK 총괄 실제 GGUF 부서 업무 제안·직원 배정 개발 인수인계

**기존 제품 신규 파일**
- windows-integrated-src/desktop/company_chief_department_discovery.py — 실제 SQLite 15부서/실모델 직원/회사 업무·목표 원본에서 총괄 GGUF 1회 호출, 엄격 모델 JSON 검수, 호출 감사/증빙 SHA256, 최대 5건 불활성 제안.
- windows-integrated-src/desktop/company_chief_department_dispatch.py — 관리자 개별 승인 또는 반려. 승인 시 실제 todo와 직원 업무량 기반 부서 배정 및 SQLite 불변 감사.
- windows-integrated-src/desktop/company_owner_chief_discovery_tabs.py — 한국어 Tk 관리 UI.

**기존 수정**
- company_native_owner_workflows.py 실제 모델 비동기 호출/취소 연결, storage.py LocalStore API, build_windows_exe.bat PyInstaller 포함.
- docs/automation_full_handoff.md 누적 기록.

모델 임의 변경·계정 사용·실결제·실제 매출 가정·고객 발송·기존 원본 삭제 없음. 원본 변경 감지·중복 모델 자동 시도 차단. 관리자 개별 승인 없이 직원 실행 없음.
전체 개발 완료 전 단계이므로 Windows EXE/진짜 GGUF 실행/T01~T20 통합검증/일괄 오류 수정 **NOT_RUN**.
남은 개발: 15부서31AI30업무 장기 자율 협업·24시간 안전한 운영 복구·외부 실제 판매/결제/은행/환불·기록 1,099/1,171개 ZIP 전수 보존 통합.
