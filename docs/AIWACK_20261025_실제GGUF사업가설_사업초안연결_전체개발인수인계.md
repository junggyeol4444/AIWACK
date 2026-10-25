# AIWACK 실제 기능 개발 누적 인수인계

## 2026-10-25 후속 코드 개발 — 기존 로컬 GGUF 총괄 신규 사업 기획·승인·사업 초안 연계 (append-only)
- 사용자 최우선 명령: “개발 하라고 계속 개발이 전부 끝날 때 까지”. **전체 기능 개발 먼저**, 검증/오류수정 단계는 전체 기능 개발 완료 이후로 유지. 이번 추가 개발에서도 신규 pytest/Windows EXE 실제 실행/물리 버튼 검증을 수행하지 않음(**NOT_RUN**). 완료·성공 주장 금지.
- 신규 원본 연결 모듈 `windows-integrated-src/desktop/company_business_ideas_model.py`: 기존 `desktop.chief_runtime.invoke_chief_model`을 실제 호출, 회사의 기존 활성 사업 유형 목록 및 소유자가 입력한 대상 고객·고객 문제에 한정된 **1건의 실제 GGUF 사업 가설** JSON을 엄격 파싱. 형식 오류면 가짜 가설 자동 생성 금지. 실제 모델 호출 ID와 입력/출력 SHA256 및 형식 오류의 불변 감사. 수요/시장/매출 검증으로 오인 금지, 모델 교체 없음. 생성 커밋 `1e668d6e18039c206060fc54141c35ca6daf2947`.
- 동일 모듈 추가 개발: 관리자 검토 후보 선정/기각 감사 원본 보존. 명시적으로 후보 선정한 실제 모델 가설을 별도 관리자 클릭 시에만 기존 `business_portfolio.add_business` 호출해 예산 **0원**, 상태 `draft` 로컬 사업 초안 생성. 아이디어·실제 모델 호출·사업 DB 번호를 별도 불변 링크로 저장; 중복 초안/자동 외부 실행 금지. 커밋 `0904e5a4b150191d1da5f8246bf5d9789028c287`.
- 기존 `windows-integrated-src/desktop/storage.py`: 실제 모델 가설 생성/읽기/관리자 검토와 사업 초안 인계/인계 조회 `LocalStore` API를 연결. 커밋 `64fc13fa57dfad31ee30cb4562aa339cf13dd492`, `514389b84c32d11e1b13218a7b12617de001bbd1`.
- 기존 `windows-integrated-src/desktop/company_native_owner_workflows.py`: 한국어 Tk 탭 '실제 AI 신규 사업 가설' 신규 추가, 고객/문제 입력, 백그라운드 취소 가능한 실제 GGUF 한 번 호출, 제안 목록, 소유자 별도 선정·기각, 명시적으로 선정한 가설을 기존 사업 포트폴리오에 예산 0원 초안으로 연결, 출처 조회 버튼. 기존 30업무·PG/은행 등 탭 삭제·교체 없음. 커밋 `aa726d7bfb85936d93abc7b890e207db13194840`, `f6257cc1c4e8caa0ebea813297c55de8a63b28c2`.
- 기존 `windows-integrated-src/build_windows_exe.bat`: 새 모듈 `desktop.company_business_ideas_model` 원본 EXE PyInstaller hidden-import 누적. 커밋 `b58edea408253dd7aa2687c32028ec507e74e8a4`.
- **금회 누적**: 앞선 다중 Windows GUI 중복 GGUF 잠금/자동 운영 누락 감사 개발 커밋 **11개**, 이번 실제 로컬 GGUF 사업 기획/관리자 선정/기존 사업 DB 초안 연결 개발 커밋 **7개**, 합계 **18개 실제 코드 변경 커밋**. 총 수정/추가 대상: `company_autopilot.py`, `company_continuity.py`, `company_office_gui.py`, `company_business_ideas_model.py` (신규), `storage.py`, `company_native_owner_workflows.py`, `build_windows_exe.bat` 7개 코드/설정 파일. 테스트 브랜치의 기능 개발이며 main 최종 병합 아님.
- 현재 실제 개발 **미완료**: 원본 1~21회차 1,099개와 최신 GitHub 원격 파일 간 전수 SHA·3-way 보존 대조; 원본 변경 52·추가 73개 누적 기능 유실/충돌별 병합; 원본 역사 문서 28+매니페스트 2의 GitHub 개별 보존; 원본 기획 15장, T01~T20, 15부서31AI30업무, Windows10/11 실제 EXE GUI, 실제 GGUF 전체 장기 협업, 사업/고객/상품/승인된 실도구·계정, 실제 금융 처리와 무단 거래 방지, 자율 장기 운영/회복 중 아직 미구현 요구 모두 개발. 전체 기능 개발 종료 **이후에만** 기존·신규 전체 통합검증 → 실패 수정 → 전체 재검증 → main 최종 안전 병합.
- 확인하지 않은 실기 검증/성능/24시간/T01~T20 전항목 성공과 모델 출력, Windows EXE 빌드 성공을 주장하지 않음. 별도 새 GUI, 웹/HTTP, 원본 삭제, 다른 프로젝트/예약 수정 없음.

## 후속 개발 우선 지시
테스트 브랜치 최신 기존 소스와 이 대화의 선행 전체 누적 인수인계를 읽고 아직 개발 완료하지 못한 원본 기획 기능과 누적 소스 병합을 이어서 개발한다. 전체 개발 종료 전 테스트·검증만 반복하지 않는다. 개발 완료 후 전체 통합검증→발견한 오류 수정→전체 재검증→main 안전 병합 순서를 반드시 보존한다.
