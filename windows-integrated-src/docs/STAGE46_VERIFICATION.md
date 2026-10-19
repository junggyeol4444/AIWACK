# Stage46 — 회의 의사결정 및 후속 업무 배정

## 기준

- 입력: `AIWACK_Stage45_Local_Offline_Source.zip` (188개 파일), `docs/progress.json`의 완료 1~45, 다음 46.
- 원본 기획안의 AI 회의 제3장 3.4의 6번 결정권자 의사결정, 8번 담당자 및 업무 배정에 해당하는 **관리자 기록 기반 오프라인 초기 구현**.
- 사용자 기획서·기존 Tkinter·SQLite 구조 유지. 사용자의 현재 요구에 따라 GitHub, 외부 서버, 클라우드 AI API 미사용.

## 구현

- `desktop/meeting_decisions.py`: 예정된 회의의 실제 안건에 대한 관리자 명시적 `approved/deferred/rejected` 결정. 최소 1개 기존 의견, 의견 불일치·미제출 참석자 확인, 필수 근거. SQL 트리거/FK/UNIQUE를 통한 교차 회의 연결 방지·불변 결정 기록·결정된 안건에 추가 의견 차단.
- SQLite에 결정 시점 제출·미제출 건수 스냅샷. 승인되지 않은 결과(`deferred/rejected`)에는 후속 업무를 생성하지 않음.
- 관리자가 별도 버튼을 눌러 **채택된 결정당 최대 하나**의 `todo` 회사 업무 생성. 참석 중인 활성 실무 직원 배정, 담당·상태 이벤트 기록, 결정·업무 연결 이력 저장. `BEGIN IMMEDIATE`로 원자적 처리·중복 실행 방지.
- `desktop/app.py`: `AI 회의 결정·후속 업무` 관리 탭, 선택·검토·승인·배정·결과 조회.
- 기존 소스, 원본 문서 및 SQLite 데이터 파일은 재작성하지 않음. 새 DB 테이블은 IF NOT EXISTS로 추가.

## 검증 결과 (2026-10-13; Linux Xvfb)

- 전체 `python -m pytest -vv -x`: **517 passed in 65.29s**, 0 failed (`docs/STAGE46_FULL_PYTEST.log`). 기본 45단계 485개 + 신규 32개.
- `python -m pytest -q tests/test_meeting_decisions.py`: **32 passed**.
- 네트워크 소켓 연결 차단 환경 `python scripts/verify_offline_runtime.py`: **14개 오프라인 명령 성공** (`docs/STAGE46_OFFLINE_RUNTIME.log`). 기존 GUI 포함. Python 소켓 차단이며 OS 방화벽 증빙은 아님.
- `xvfb-run -a python scripts/stage46_offline_gui_smoke.py`: **PASS** (`docs/STAGE46_OFFLINE_GUI.log`). Tkinter 실제 버튼: 회의·안건 생성, 의견 등록, 확인 미체크 차단, 결정, 후속 업무 배정, 중복 차단, 잘못된 회의 선택 초기화, 로그아웃·재로그인 복구.
- `python -m compileall -q desktop scripts tests`: PASS.
- 기존 45단계 ZIP 항목 누락 여부 및 SQLite/기획 파일 해시 대조: ZIP 배포 검증 기록 참조.

## 정확한 기능 범위 및 제한

- 관리자가 AI 직원 **명의로 기록**한 의견을 참고해 결정하는 기능입니다. AI 모델 자체가 의견을 내거나 토론해 결정을 내리지 않습니다.
- 내부 `todo` 업무만 생성합니다. 모델 추론·작업 대기열 자동 실행·외부 앱 조작·결제·금전 지출·계약 승인 권한을 새로 부여하지 않습니다.
- 승인 후 업무가 진행 중일 때 회의 취소 및 직원 비활성화에 따른 실제 업무 중단은 기존 업무 관리 정책을 따르며 자동 취소하지 않습니다.
- Windows 10/11 실기기, Windows EXE 빌드 및 실제 GGUF 추론은 미검증.
- 로드맵 46/100=46%와 실질 제품 완성도 약 16~19%(주관적 추정)는 서로 다릅니다.
- 다음: 47단계 직원별 장기 기억 저장.
