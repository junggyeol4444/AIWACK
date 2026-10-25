# AIWACK 누적 개발 인수인계 — 실제 기능 구현, 전체 개발 우선

## 2026-10-25 후속 전체 기능 우선 개발 — 다중 Windows EXE 실제 GGUF 실행 잠금 및 4단계 자율 운영 디스크 감사 (기록 추가)
- **새 사용자 지시 원문:** “아니 개발이 다 안끝났덷 왜 검증을 하냐고 개발 하라고 계속 개발이 전부 끝날 때 까지”. 순서 변경 불가: **전체 잔여 기능 실제 개발 → 전체 통합 검증 → 실패 수정 → 전체 재검증 → main 최종 반영**. 이 회차는 새 pytest/EXE/GUI 물리 테스트를 실행하지 않음. 테스트 PASS 허위 주장 금지.
- 기존 저장소 `junggyeol4444/AIWACK`, 지정 누적 테스트 브랜치 `test/aiwack-20261023-0755-cumulative-resume-merge` 내 **기존 코드 파일 3개를 직접 수정**. 새 앱/HTML/web 도입 없음.
- `windows-integrated-src/desktop/company_autopilot.py`:
  1. Windows 다중 EXE에서 소유자 승인 자동 GGUF 동일 업무에 대한 실행 이력·미완료 잠금을 SQLite `BEGIN IMMEDIATE` 트랜잭션으로 확인하고, 최초 1건만 모델 호출하도록 소유 토큰/작업 ID/감사 ID 잠금 보존. 과거 성공/실패/미완료 호출에 대한 자동 재시도 전부 금지. 관리자 직접 실행과 구분. 커밋 `ba1a2e6305737f13c855f8c2af83b124d3db0ea5`.
  2. `aiwack_autopilot_tick_gaps`: 기존 사내 자동 운영이 비활성/중단되지 않은 채 기한을 지나 놓친 주기 횟수와 실제 다음 실행 시각을 별도 불변 감사로 영구 기록하며, 놓친 주기의 성공·모델 호출은 생성하지 않음. `skipped_tick_windows` 조회. 커밋 `3579a9a4e176cbce7121c8d27c98e7c6102c9dae`.
  3. `aiwack_autopilot_step_evidence`: 기존 로컬 자동 운영 4개 단계 (제안/반복 일정/이벤트/실제 실패 후속 제안)를 단계가 끝날 때마다 생성한 실제 SQLite 행 ID와 SHA256을 담아 append-only 저장. 중단 시 완료된 전 단계만 남고 이후 미실행 단계는 생성하지 않음. `step_history` 및 원본 해시·개수 검사. 커밋 `3487d6ea8ee61ee208a66ca5361db6e9166b8584`, `3e3b2b73a09b752401b332caf6ab19b5fb18e2ce`.
  4. `running_model_leases` 및 `approved_model_attempts_for_task`는 실제 Windows 창의 업무별 잠금, 원본 모델 자동 호출 이력을 읽기 전용 조회. 후자는 과거 자동 호출이 있는 업무를 수동 원본 감사로 확인할 수 있도록 전체 이력을 반환하나 재호출 허용을 자동 결정하지 않음. 커밋 `0e0249a13444dbc952998423fbbf6a323a8ac5dd`.
- `windows-integrated-src/desktop/company_continuity.py`: 관리자 본인 확인·180초 경과·실제 다른 프로세스 종료 수동 확인을 통한 기존 불변 복구 감사 확정 시에만 해당 모델 자동 호출 잠금을 같은 트랜잭션에서 해제. 자동 재실행 없음. 커밋 `61f4f39cfab98b936966efd69d0e46f5fbc3f064`.
- `windows-integrated-src/desktop/company_office_gui.py`: 기존 한국어 Windows Tk 자동 운영 이력 GUI에 실제 모델 잠금·누락 주기·4단계 생성 원본 표시, 기존 업무 화면에 선택 업무의 과거 GGUF 시도와 잠금 상태 버튼/조회 연결. 커밋 `54d247f7a6bfce3cdef034fe9039915a15d96466`, `c8b78e063689bd0956f848e328a275991ec0ff28`, `ca3428aa27eeab56fbf1fc8efee5f68dc5a81f9b`, `ee1f1a6e8ec73ebbb812760ba3e84c676683336c`, `d5b4d96150786930b4fcf2e6c471f73494f57eec`.
- **금회 코드 변경 총 11커밋 / 기존 파일 3개**, 모두 지정 테스트 브랜치. **전체 개발 미완료, 코드 전체 통합검증 NOT_RUN, 실제 Windows 10/11 물리 EXE GUI NOT_RUN, 24시간 연속 실행 NOT_RUN, 실GGUF 30업무 NOT_RUN, T01~T20 전체 최종 합격 NOT_VERIFIED, main 최종 병합 NOT_DONE.** GitHub 커밋 존재가 기능의 실기 성공은 아님.
- **잔여 개발:** 원본 1,099개 ZIP vs 현재 원격 main/테스트 원본의 전수 대조와 차이 52개·추가 73개 기능의 보존형 3-way 병합 미완료. 역사 원문 28개·매니페스트 2개 현재 원격 개별 복원 최종 확인 미완료. 기획안 15장과 15부서·31AI·30업무, 실제 GGUF 계획/직원 실행/총괄 검토/관리자 최종 승인, 외부 도구, 고객·상품, 결제/취소/환불/은행/재무, 자율 사업 발굴/실행/개선, 실패 복구·24시간 운영, T01~T20 전체 기능의 누락 구현을 **개발 단계에서 먼저 이어갈 것**. 정확한 남은 기능 개수/완료율은 보존 원본 최종 대조 전 추측 금지.
- 금지 유지: 원본 소스/DB/인수인계 삭제·덮어쓰기, 새 앱·웹UI, 가짜 모델/승인/수익, 사용자 승인 없는 PG·은행·게시, 임의 브랜치 생성·삭제/force push, 모델 교체, 다른 예약/프로젝트 변경, 검증 없이 main 조기 병합. 이 대화 흐름을 작업 기록 기준으로 삼는 사용자 요청 보존.

## 다음 개발
1~21회차 누적 ZIP/패치와 테스트 브랜치 간 원본 손실·충돌 후보(변경 52, 추가 73)를 원본 보존형 병합하고, 미구현 기능을 실제 Windows EXE 원본에 이어서 개발. 전체 잔여 기능 개발 종료 전 테스트/검증 단계로 이동 금지. 그 후에만 전체 통합검증→실패 수정→재검증→main 최종 반영.

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
