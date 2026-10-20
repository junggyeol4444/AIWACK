# AIWACK — 매시간 개발 자동예약 누적 인수인계 (2026-10-19 KST)

> 이 문서는 원래 대화 유지가 예약 시스템에서 보장되지 않는 경우에도 개발 소스와 사용자의 지시가 유실되지 않도록 **GitHub `main`에 남기는 지속 인수인계**다.
> **대화창 연속성은 플랫폼에서 확약할 수 없다.** 문서를 읽지 않고 읽었다고 주장하지 말 것. 매 회차 최신 GitHub 커밋·Actions 기록을 재조회하고 아래를 갱신할 것.

## 0. 사용자 최신 요청 및 최우선 운영 규칙

- 사용자는 AIWACK **이 예약이 만들어진 원래 대화 안에서** 매시간 계속 개발·수정·검증하기를 원한다. 대화 길이 한도에 걸리는 경우에만 새로운 대화를 허용한다. **예약 결과를 같은 대화에 쓰도록 강제할 수 없다면 가능하다고 거짓말하지 말 것.** 다른 대화로 넘어갈 경우 **작업 시작 전 이 문서와 관련 모든 기획·검증·소스, 기존 로그를 읽고, 종료 시 최신 인수인계를 반드시 갱신**하라.
- 사용자 PC가 꺼져 있어도 매시간 가능한 **GitHub 및 서버 기반 작업**을 반복하는 것이 목적이다. PC에서 실제 실행했다고 꾸미지 말 것.
- **Google Drive를 비롯한 외부 드라이브 연결 불필요·금지**. 사용자가 요청하지 않았으며 추가 연결이나 계정 인증을 요구하지 말 것. 인수인계는 이 GitHub 저장소에서 관리한다.
- **한 번에 여러 기능 개발·수정·검증**하라. 작은 파일 하나나 CI 문구만 수정하고 전체 개발을 했다고 주장하지 말 것.
- 사용자 지시를 재해석하거나 기존 기능을 임의로 삭제·초기화·재개발하지 말 것. 정확히 모르면 모른다고 명시. 사용자가 이미 답한 질문 다시 묻지 말 것.
- **`main`이 유일한 최종 코드 및 작업 브랜치다.** 타 브랜치 전체 삭제를 대비해 2026-10-19 이전 8개 feature tip을 octopus 부모로 보존한 이력이 있다(merge-parent commit `919d163c75285ac0182043c243af79d26ada72d5`). 마지막 확인 시 **브랜치는 main 하나만 존재**. 새 브랜치를 만들거나 삭제하지 말고 **`main`만 비강제 fast-forward 수정**하라.
- AIWACK는 별도 프로젝트 **AISTING, MYVOCAL, AI-NOVEL, AGI2**와 혼동하면 안 된다.
- HTML/웹앱으로 대체하지 않는다. Windows 10/11 **로컬 네이티브 EXE**, 실제 GUI 버튼·저장·재실행 사용자 경험을 최우선한다.
- 위험한 외부 작업, 결제, 실거래, 서비스 게시, 권한 변경 등에는 사용자(소유자) **별도 승인**을 유지한다. 임의 자율 실행·가짜 성공·미검증 제품 배포 불가.

## 1. 정확한 저장소와 현재 기준점

- GitHub: https://github.com/junggyeol4444/AIWACK
- 기존 통합 Windows 애플리케이션 실제 소스: `windows-integrated-src/`
- 메인 실행 엔트리: `windows-integrated-src/desktop/entry.py`
- GUI/회사업무: `windows-integrated-src/desktop/company_office_gui.py`, `windows-integrated-src/desktop/company_operations.py`, `windows-integrated-src/desktop/app.py`
- 데이터: `windows-integrated-src/desktop/storage.py` 및 SQLite
- 모델: `windows-integrated-src/desktop/model_runtime.py`, `windows-integrated-src/desktop/chief_task_runtime.py`
- 원본 사용자 기획안: `windows-integrated-src/docs/original_project_spec.txt`
- 원본 T01~T20 인수 기준: `windows-integrated-src/docs/verification_stage87_100_local_safety_acceptance/T01_T20_FINAL_ACCEPTANCE_MATRIX.md`
- 통합 당시 851개 원본 앱 소스 파일에 관한 매니페스트: `windows-integrated-src/VERIFIED_SOURCE_MANIFEST.json` (초기 통합 출처를 기술한 스냅샷이며 이후 모든 변경을 포함하는 최신 매니페스트라고 주장하지 말 것).
- **이 문서를 만들기 직전의 main**: `ee2b77b00d9305e993530b3dead108baedab36d1`.
- 이 인수인계 문서 생성 커밋부터는 HEAD가 변경된다. **매 회 최신 HEAD를 직접 확인하라.**

## 2. 원래 프로젝트의 목표와 보존 사항

- AGI 없이 자율 운영형 다중 AI 기업 시스템: 소유자 → 총괄 AI → 부서장/직원/전문 AI, 15개 부서, 31명 초기 직원 프로필 지향.
- 회사 목표와 상황 분석, 직원·직무·권한·모델 관리, AI 업무 발견/지시/실행, 총괄 검수, 관리자 승인, 재실행 후 기억, 사고 복구, 운영 GUI, 비상정지.
- 사업 발굴부터 상품 제작·마케팅·판매·매출/지출/이익까지 이어지는 장기 기획. **실제 자율 사업, 외부 서비스 연동, 실거래, 수익 창출, T01~T20 전체 인수 합격은 현재 증명되지 않았다.**
- 프로그램은 Windows EXE 실행 → 소유자 최초 생성(1회) → 다음부터 저장 계정 로그인 → 기존 회사/AI 인력/업무/결과 상태 유지 → 사용자 버튼으로 작업/검수/복구/승인하는 실제 사용자 흐름이어야 한다. 코드 단독 테스트로 전체 기능 완성을 주장 금지.
- 로컬 GGUF llama.cpp를 사용할 수 있으나 실제 모델 E2E와 synthetic/stub 테스트 결과를 명확히 구분해야 한다.
- 외부 도구 호출, 구매·판매·계약·외부 계정 변경은 사용자 승인 없이 실행하지 않는다.

## 3. 기존 코드 누적 작업과 실제 확인된 검증

- GitHub `main`의 `windows-integrated-src/`에 851개 원본 앱 소스 추출·검증본을 포함하도록 소스 보존/통합했고, 삭제될 feature 브랜치의 독립 커밋들이 main 이력에 편입되었다.
- 관리자 생성·로그인, 회사명·운영 목표 설정/저장, SQLite 종료·재시작 유지, 직원 수행 → 총괄 AI 평가/보고 → 소유자 별도 승인/최종 완료 흐름에 대해 Windows 패키지 GUI E2E를 여러 차례 검증했다.
- 실제 직원 결과물이 저장된 뒤 프로그램이 강제 종료되면 직원 AI를 **다시 실행하지 않고 저장된 감사 결과물에서 총괄 AI 검토만 사용자 명시적 버튼 클릭으로 복구**하도록 구현/검증했다.
- 관리자 승인형 **총괄 검토 중단 업무 최대 3건 일괄 복구**, 후보 목록 표시, 불필요한 중복 직원 추론 방지, 실패 시 다음 후보 중단, 비상정지 및 취소 보호를 추가했다.
- `llama-completion.exe`/llama.cpp에 `--single-turn`을 적용해 실제 Windows 실행기의 EOF 이후 비정상 종료 문제를 개선했다. 비정상 종료를 성공 처리하거나 무조건 재시도하지 않는다.
- `ee2b77b...`에서는 운영센터의 완료되지 않은 running 직원 작업 감사/복구 GUI와 상태 지속/권한 검사 영역 추가.
- **검증된 Actions**:
  - 동일 main `ee2b77b...` CI **success**: https://github.com/junggyeol4444/AIWACK/actions/runs/39214755481
  - 해당 SHA Windows 2022/2025 EXE 빌드 + GUI 실행 흐름 **success**: https://github.com/junggyeol4444/AIWACK/actions/runs/39214755500
  - 해당 SHA Windows 2022/2025 회사 설정 저장·재로그인 **success**: https://github.com/junggyeol4444/AIWACK/actions/runs/39214755525
  - **해당 SHA 실제 GGUF 직원/총괄 승인형 업무 2건 실행 E2E 양쪽 success**: https://github.com/junggyeol4444/AIWACK/actions/runs/39214755617
  - 이전 SHA 실제 GGUF 업무 2건 양쪽 success: https://github.com/junggyeol4444/AIWACK/actions/runs/39213259946
  - 이전 SHA 장애 직후 EXE 강제 종료·재개 실사용 검증: https://github.com/junggyeol4444/AIWACK/actions/runs/39210713639
- 성공한 것은 각 테스트가 확인한 **일부 범위**다. 사용자 Windows 11 물리 PC의 실제 설치/사용, 모든 31명 직원의 장기 자율 운영, T01~T20 종합 최종 합격은 별도로 미검증.
- `T01_T20_FINAL_ACCEPTANCE_MATRIX.md`는 초기 시점의 검증 문서이므로 일부 행의 'Windows EXE 미검증' 표기는 이후 Windows CI 성공으로 부분 개선되었다. 그렇다고 모든 행을 PASS로 바꾸지 말 것. 원본 행의 전체 인수 기준을 다시 평가해야 한다.

## 4. 다음 매시간 개발에 반드시 지킬 작업 방식

1. GitHub 연결만 이용하여 현재 `main` SHA/브랜치 목록/최신 Actions/기존 소스/이 문서를 읽는다. **드라이브 연결하지 않는다.**
2. T01~T20 원본 성공 조건과 실제 현재 코드 차이 확인. 여러 실질적인 결함 및 미구현 기능을 한 묶음으로 처리한다.
3. 실제 코드와 필요한 테스트를 `main`에 안전하게 커밋한다. 기존 앱, 개인 사용자 데이터, 명세, 원본 자산, 관리자 승인·비상정지 흐름을 파괴하지 않는다. `main` HEAD가 변경됐으면 충돌을 재확인한다.
4. GitHub Actions Windows Server 2022/2025에서 EXE 빌드, 실제 GUI 키보드/마우스 조작, 저장·재실행, 권한/승인/비상정지, 모델(GGUF/합성 구분), 강제 종료·복원·중복 실행 여부를 검증한다. 로그·실패 화면을 조사해서 수정한다.
5. 실패, 진행중, 성공, 미검증을 구분해 SHA와 URL을 보고한다. 장시간 미완료는 다음 회차에 이어 확인한다.
6. 마지막에 **이 파일 내용을 반드시 현재 HEAD, 변경 내역, 신규 테스트 URL, 미완료/다음 작업에 맞게 갱신**한다. 갱신 실패 시 저장했다고 주장하지 말고 답변에 새 전체 인수인계를 명시한다.
7. 예약 시스템이 다른 채팅을 만들면 '원래 채팅에서 진행 중'이라고 허위 보고하지 말고, **이 파일부터 읽은 후** 동일 저장소 `main`의 현재 상태에서 이어간다.

## 5. 아직 해결/검증할 사항

- 원본 T01~T20 전체 인수 기준을 **부분 구현 / 실제 합격 / 미검증**으로 재측정. 과거 문서에서 전 항목 최종 승인 보류라고 표기되어 있음.
- 최신 운영센터에서 실제 중단 작업 running 감사 표시·수동 복구 버튼을 Windows GUI 사용자 클릭으로 물리 검증 강화.
- 다양한 크래시 시점, SQLite 동시성 및 작업 사이드 이펙트/복구 부작용, 모델 실행기 오류와 장기 안정화, 스케줄러의 신뢰성.
- 실제 31명 직원 협업·자율 업무 발견·계속 운영·장기 기억 및 병렬 모델 실행 증명.
- 사용자 개인 Windows 10/11 PC 설치·실행 검증. GitHub Windows Server 가상 실행은 동일하지 않음.
- 실제 외부 도구/판매/매출/자동 업무 24시간 운영은 사용자 승인 및 별도 위험 통제 없이 구현·검증 완료로 간주하지 말 것.

## 6. 예약의 실제 한계와 인수인계 보존 정책

- 자동화 예약은 2026-10-19 17:10 KST부터 매시간으로 등록되어 있다(실제 예약 시스템에서 시간·활성 여부를 조회하여 확인).
- 원래 대화에 계속 메시지가 이어붙는다는 **플랫폼 보장 없음**. 사용자 요청은 같은 대화 최우선, 길이 초과만 대화 이동 허용이라는 점을 명시적으로 보존한다. 불가능한 부분을 감추지 말 것.
- 계속 작업하는 프로젝트는 AIWACK **딱 하나**이며, 이 작업을 위해 다른 프로젝트 예약, 외부 드라이브, 다른 GitHub 저장소를 건드리지 말 것.
- **단순 자동화 프롬프트 자체는 소스/인수인계 보존을 대신하지 않는다.** 이 GitHub 문서와 main 커밋 이력을 기준으로 누적 업데이트하여 새 대화에서도 이전 소스와 작업 단계를 읽고 복구할 수 있도록 한다.

## 7. 2026-10-20 실제 기존 프로그램 수정·테스트 누적 (이번 대화에서 검증한 사실)

- 주의: 이 문서의 2026-10-19 이전 내역과 10월 20일 신규 작업은 구분한다. 이번 대화에서 실질 수정 성공 여부를 GitHub main에서 재조회함.
- 작업 전 GitHub main HEAD는 `71f104e8821411508058c0ca92eaeff415c32e47` (인수인계 문서 생성 커밋)이었고, 2026-10-20 신규 실제 커밋이 이후 생성되었다. 아래는 **기존 main의 기존 파일을 수정한 내역**이다.
- 코드 수정 3개 파일: `windows-integrated-src/desktop/model_runtime.py` (출력 20000자 초과/빈 응답 실패 처리 및 링크가 가리키는 UNC 공유 차단) → `147692e948aafd672a26ce9df0253ed380372794`; `windows-integrated-src/desktop/company_operations.py` (running 감사 DB 조건 조회; 총괄 복구 관리자가 확인한 ID 목록 비교) → `8dabac793019b76453425a14e6d00a59b5846410`; `windows-integrated-src/desktop/company_office_gui.py` (누락을 막는 표시 및 확인한 업무 ID 전달) → `de0ef31c10a6f406dd5a799058b429301fc9d01b`.
- 기존 회귀테스트 2개 파일에 새 테스트 추가: `windows-integrated-src/tests/test_company_chief_review.py` → `f3101134597694a44f5ebb25790d9cdc4b534518`, `windows-integrated-src/tests/test_local_models.py` → `d3bc4d1dc0995c446334d9f353f98ec7d89b15bd`. 테스트에 synthetic/stub 사용됨을 실제 GGUF E2E와 혼동하지 않는다.
- GitHub main 전용 자동 개발 범위 문서 `docs/AUTOMATION_PROMPT.md` 수정 → `916218d54028138abf7db764b4e1d29b1b0fcf5a`. `.github/workflows/hourly-development.yml`에서 `automation/*` 생성/푸시/PR 로직 제거, 보호된 현재 main HEAD 비교 후 같은 main에 비강제 push, native 코드와 인수인계만 변경하도록 제한 → `0572947fa5b15eea0f9ab9b65c1617b0384dd7a7`. 실제 pyproject 경로 기준으로 설치 오류 바로잡음 → `f0d33fed81043eb52e2dd5a749e2076f6acd824e`. 이는 GitHub Actions 워크플로 변경이며, ChatGPT 예약 상태를 수정한 것이 아니다.
- `.github/workflows/ci.yml`에 기존 `windows-integrated-src` 회귀테스트 설치 및 실행 단계 추가 → `21f94fff5bfddaed78252864779ceb9f5ded2674`. **이전 성공한 일반 CI는 이 신규 native 회귀테스트 성공의 증거가 아니다.** 신규 변경된 CI 실행 결과를 확인해야 한다.
- **검사 구분/실제 상태(이 문서 업데이트 시 조회)**:
  - 기존 신규 소스 SHA `8dabac...` CI success: https://github.com/junggyeol4444/AIWACK/actions/runs/39346471157
  - 신규 소스 SHA `de0ef...` CI success: https://github.com/junggyeol4444/AIWACK/actions/runs/39346479664
  - 신규 소스 SHA `de0ef...` Windows 포장 EXE 회사 설정 저장·재시작 GUI success: https://github.com/junggyeol4444/AIWACK/actions/runs/39346479494
  - 5개 소스/테스트 누적 SHA `d3bc4...` 신규 CI **queued**: https://github.com/junggyeol4444/AIWACK/actions/runs/39346604557
  - SHA `d3bc4...` Windows 2022/2025 EXE 시작 GUI **queued**: https://github.com/junggyeol4444/AIWACK/actions/runs/39346604596
  - SHA `d3bc4...` Windows 2022/2025 회사 저장·재로그인 **queued**: https://github.com/junggyeol4444/AIWACK/actions/runs/39346604543
  - SHA `d3bc4...` Windows 2022/2025 실제 GGUF 승인 업무 2건 **queued**: https://github.com/junggyeol4444/AIWACK/actions/runs/39346604586
  - `21f94...`에 신규 native 테스트 실행 단계가 추가됐으나 결과는 이 문서 업데이트 시 **미확인**; 반드시 최신 CI 재조회.
- 한계: Windows Server 2022/2025 Actions 실행 결과만 검증된 것이고, 사용자의 Windows 11 물리 PC에서 검증된 것이 아니다. T01~T20 전체 최종 인수는 미완료. queued/in_progress를 PASS로 변경하지 않는다.
- 본 대화에서 사용자 직접 지시로 **ChatGPT AIWACK 매시간 예약이 비활성화**된 상태. 사용자가 명령하지 않으면 예약 활성화/비활성화 등의 설정을 다시 변경하지 않는다. GitHub Actions의 자체 cron과 ChatGPT 예약은 별개다.
- 외부 드라이브와 다른 프로젝트 예약/저장소는 사용하지 않음.
- **다음 작업:** 이번 신규 main의 CI, Windows 2022/2025 실제 EXE GUI/SQLite/실제 GGUF 두 업무 승인/재시작 결과를 run SHA별로 재조회. 실패 시 코드를 고치고 main에 커밋. T01~T20 최종 검증 매트릭스를 각각 실제 검증/미검증으로 갱신. 사용자 Windows11 물리 PC 확인은 실제로 접속/실행할 수 없으므로 미검증 유지. 다음 인수인계는 본문을 삭제하지 않고 누적한다.

## 8. 2026-10-20 추가 개발·검증: 실제 Windows EXE 호환성 강화 (누적)
- 이번 회차 시작 main HEAD: `ca9f9f99f434b7bd48e0a04c57ff464f12a5146b`. 실제 Windows EXE 검증 로그 재조회.
- `d3bc4d1dc...` SHA Windows 2022/2025 EXE 빌드·시작 양쪽 PASS: https://github.com/junggyeol4444/AIWACK/actions/runs/39346604596
- 같은 SHA 회사 GUI·저장·재시작 양쪽 PASS: https://github.com/junggyeol4444/AIWACK/actions/runs/39346604543
- 같은 SHA 실제 GGUF 승인 업무 2건: **Windows 2025 PASS, Windows 2022 FAIL**: https://github.com/junggyeol4444/AIWACK/actions/runs/39346604586
- 실패는 Windows 2022 실제 GGUF GUI 테스트 이전, 공식 `llama-completion.exe` 직접 실행 단계에서 `0xC0000374 / STATUS_HEAP_CORRUPTION` 발생. 해당 액션 artifact `12230849965`의 `aiwack-llama-preflight.txt`로 비정상 종료 코드와 출력을 확인. **앱 자체 결함으로 아직 단정할 수 없고, 실행기 호환성 또는 네이티브 런타임 문제로 분리 조사 필요. 재시도해 성공한 것처럼 꾸미지 말 것.**
- 기존 `model_runtime.py`에 0xC0000374 진단 오류 메시지를 추가하고, 비정상 종료를 성공·자동 재시도 처리하지 않는다. 실제 윈도우 2022 실행기 충돌의 근본 원인을 해결했다고 주장하지 않는다.
- 기존 `company_operations.py`에 관리자 승인된 총괄 복구 대기열 ID를 **매 업무 시작 전 다시 비교**하여 다른 세션이 후보를 변경하면 다음 업무 실행을 중단하는 검사를 추가.
- 기존 `company_office_gui.py`의 소유자 업무 승인 확인창에서 리터럴 백슬래시+n이 출력되던 잘못된 줄바꿈 두 군데를 수정.
- 기존 테스트 `test_local_models.py`에 Windows 힙 손상 종료·중복 추론 금지 테스트(합성), `test_company_chief_review.py`에 배치 진행 중 다른 창의 후보 변경을 감지해 다음 업무를 실행하지 않는 테스트(합성)를 추가.
- 사용자 Windows 11 실제 장치 테스트는 미검증. 이번 추가 패치에 대한 Windows 2022/2025 실행 검사 결과는 다음 Actions 실행 후만 확정. 기존 PASS를 새 수정 코드 PASS로 대체해서는 안 됨.
- 다음 과제: 이 커밋의 native CI와 Windows EXE/GGUF 워크플로 결과 확인, 실패라면 구체적 로그와 스크린샷·모델 프리플라이트 진단을 기반으로 기존 소스 수정. T01~T20 실제 사용자 흐름 전체 미완료. 사용자 요청 없이는 ChatGPT 예약 설정을 변경하지 않는다. 다른 프로젝트나 외부 드라이브 사용 금지.

## 9. 2026-10-20 10시 KST 추가 개발·실제 EXE 빌드 확인 누적

- 이번 회차 시작 main `ca9f9f99f434b7bd48e0a04c57ff464f12a5146b`에서 시작해 기존 통합 Windows EXE 소스·실제 GitHub Actions 로그를 재조회했다.
- 기존 SHA `d3bc4d1dc0995c446334d9f353f98ec7d89b15bd`의 [EXE 빌드+GUI+재시작](https://github.com/junggyeol4444/AIWACK/actions/runs/39346604596) Windows 2022/2025 양쪽 PASS. [회사 GUI·SQLite 저장 후 재시작](https://github.com/junggyeol4444/AIWACK/actions/runs/39346604543) 양쪽 PASS.
- 같은 SHA의 [실제 GGUF 두 업무 승인 흐름](https://github.com/junggyeol4444/AIWACK/actions/runs/39346604586): **Windows 2025 PASS, Windows 2022 FAIL**. 실제 Windows 2022 실패 artifact `12230849965`의 `aiwack-llama-preflight.txt`를 다운로드해 확인했으며, 공식 `llama-completion.exe`가 앱 GUI 이전 직접 실행에서 종료 코드 `3221226356`(`0xC0000374`, 힙 손상)로 비정상 종료했다. AIWACK GUI 자체 실패라고 단정 금지. 사전 진단 실패를 무시해 합격 처리하거나 자동으로 재실행하지 말 것.
- 새 코드 커밋 `6f8d1e23e8d70b90bb6d8beb9f62a9fdedd0a553`: 기존 `model_runtime.py`의 GGUF 비정상 종료 메시지 진단·안전 실패, `company_operations.py` 복구 업무 각 시작 전 소유자 승인 목록 변경 감지, `company_office_gui.py` 승인 대화상자 줄바꿈 수정. 기존 회귀 테스트 2개 파일에 이 조건의 합성 회귀 검사를 추가했고, 인수인계 누적. 신규 [CI PASS](https://github.com/junggyeol4444/AIWACK/actions/runs/39351984840).
- `windows-integrated-src/build_windows_exe.bat`의 PyInstaller 숨겨진 company office/operations/model connect UI import를 성공한 GitHub Windows 빌드 설정과 맞춤. 커밋 `2385537b619f5285016a5d3c3b2704fb8bd05c6b`; [CI PASS](https://github.com/junggyeol4444/AIWACK/actions/runs/39352141058).
- **중요한 실패 및 복구 기록(숨기지 말 것):** `f7f3230eb893351e411b7574cdf4d43f1d81b4df` 성능 인덱스 작업의 Git tree 작성 오류로 기존 `storage.py`와 `test_company_chief_review.py`의 내용이 뒤바뀌어 신규 [CI FAIL](https://github.com/junggyeol4444/AIWACK/actions/runs/39352319557) 및 EXE 검증 실패가 발생. 기존 정상 커밋 `2385537b...`의 두 원본 파일을 재조회해 내용을 복구하고, SQLite `running` 인덱스와 테스트 변경을 **각자 올바른 파일에** 다시 적용. 복구 커밋 `5b11ff579ca3c6c9e5889b631a1304eb4f032a8c`. 이후 GitHub main 파일을 다시 조회해 storage는 `Durable offline SQLite data` 및 `class LocalStore`, 테스트 파일은 `Owner-gated chief re-review`로 원상복귀 확인. [해당 복구 커밋 신규 CI PASS](https://github.com/junggyeol4444/AIWACK/actions/runs/39352518884). 실패한 `f7f323...`을 검증된 배포 버전으로 취급하지 말 것.
- 현재 복구 SHA `5b11ff...`의 Windows 2022/2025 [실제 EXE 시작·GUI·SQLite](https://github.com/junggyeol4444/AIWACK/actions/runs/39352518873), [회사 설정 저장·재시작](https://github.com/junggyeol4444/AIWACK/actions/runs/39352518857), [실제 GGUF 승인 업무](https://github.com/junggyeol4444/AIWACK/actions/runs/39352518882)는 이 문서를 작성할 당시 **in_progress**. CI PASS만으로 세 Windows 검사 전체 PASS라고 주장하지 말고 작업 종료까지 상태별로 다시 확인할 것.
- 사용자 개인 Windows 11 장치에서 설치·실사용 검증하지 못했으며, T01~T20 전 항목 종합 인수 합격도 미완료. 외부 계정·자동 판매·무단 게시·데이터 초기화는 수행하지 않음.
- 다음 회차/후속 작업: latest main HEAD를 새로 확인하고 `5b11ff...` Windows Actions 검사 2022/2025 각각의 최종 상태와 로그를 확인. 실패한 워크플로가 있으면 정확한 실패 단계와 artifact를 읽고 기존 소스 수정 후 다시 검증. Windows 공식 GGUF 실행기 자체의 `0xC0000374` 환경 호환성은 원인을 격리·검증한 뒤에만 처리. 최신 배포 파일을 정상이라고 표시하려면 그 **같은 SHA**에서 EXE 빌드·GUI 검사 및 해당 범위의 GGUF 테스트를 구별해 통과해야 함. 사용자 명령 없이 ChatGPT 예약 설정/다른 프로젝트를 수정하지 말 것.

## 10. 2026-10-20 개발 계속: EXE/실제 GGUF 검증 후 취소 경계와 총괄 복구 정상 경로 강화

- 이번 회차 시작 GitHub main HEAD: `2f6e119c4524c8f79cbdd48c0407ef79219a3f39`. 기존 이 문서(1~9절)와 최신 CI/Windows Actions를 다시 읽었다.
- 이전 수정 SHA `5b11ff579ca3c6c9e5889b631a1304eb4f032a8c`에서 네 종류 검증 **최종 success**: [네이티브 회귀 CI](https://github.com/junggyeol4444/AIWACK/actions/runs/39352518884), [Windows 2022/2025 실제 GUI·SQLite 회사 저장/재시작](https://github.com/junggyeol4444/AIWACK/actions/runs/39352518857), [Windows 2022/2025 EXE 빌드·GUI·승인·종료·재실행](https://github.com/junggyeol4444/AIWACK/actions/runs/39352518873), [Windows 2022/2025 실제 GGUF 직원·총괄 업무 2건과 모델 검사](https://github.com/junggyeol4444/AIWACK/actions/runs/39352518882). 성공한 범위는 GitHub Windows Server 가상 실행으로 사용자의 개인 Windows 11 실기기 보장이 아니다.
- 실제 EXE 파일이 포함된 성공 아티팩트: Windows 2022 `12233853144`, Windows 2025 `12234635733`, run `39352518873`. 이는 `5b11ff...` 소스 버전이고 아래 신규 코드와 동일하지 않다.
- **신규 결함 수정**: `windows-integrated-src/desktop/model_runtime.py`에서 `communicate()` 도중 소유자가 취소를 눌러도 하위 프로세스가 성공 종료하면 모델 답변을 정상 반환할 수 있던 경계 조건을 수정했다. 완료 직후 `cancel`을 다시 확인하고 취소가 되었으면 `InterruptedError`로 결과를 폐기한다. commit `99f76aea439865ba8239eba2d0f5dba160ef623d`.
- **신규 회귀 테스트**: `windows-integrated-src/tests/test_local_models.py`에서 하위 프로세스가 응답을 반환하는 순간 취소가 설정되는 synthetic 시나리오를 추가, 결과를 반환하지 않고 1회 실행만 하는지 점검. commit `3c6b97a82ae8e2234ec54f70f42dbd4323f34be2`.
- **소유자 승인 정상 경로 강화**: `windows-integrated-src/tests/test_company_chief_review.py`에서 소유자가 확정한 복구 ID 3개에 대해 총괄 AI 검토만 수행하고 직원 중복 추론 없음·자동 승인 없음·SQLite 저장 및 재로그인 후 pending 검토 유지함을 확인하는 synthetic 회귀 테스트 추가. commit `335071010d85cc4fee28e47362718ae82fdf26f3`.
- 실행 시점 확인: `99f76aea...` CI [success](https://github.com/junggyeol4444/AIWACK/actions/runs/39353661186), GUI Windows 두 플랫폼 [success](https://github.com/junggyeol4444/AIWACK/actions/runs/39353661211). `335071010...` 최신 코드의 [CI](https://github.com/junggyeol4444/AIWACK/actions/runs/39353715116), [Windows EXE 빌드](https://github.com/junggyeol4444/AIWACK/actions/runs/39353715118), [회사 GUI·SQLite](https://github.com/junggyeol4444/AIWACK/actions/runs/39353715141), [실제 GGUF](https://github.com/junggyeol4444/AIWACK/actions/runs/39353715139)는 마지막 조회 시 queued 또는 in_progress. **앞선 버전의 PASS를 이번 추가 테스트 버전의 PASS라고 주장 금지**. 실패 시 로그 확인 후 기존 코드만 안전 수정.
- 중단 금지/금지 행동: ChatGPT 예약 설정, 다른 프로젝트, 외부 드라이브 연결·브랜치 신설·원본 삭제 등은 이번 회차 건드리지 않았다. 사용자 개인 Windows 11 실기기와 원본 T01~T20 전체 최종 인수는 여전히 미검증. 미래 회차마다 main/최신 Actions 재조회하고 정확한 PASS/FAIL/미검증을 보존한다.

### 10절 후속 Actions 결과 재조회 (2026-10-20 KST, 완료/진행 구분)

- 신규 소스 `335071010d85cc4fee28e47362718ae82fdf26f3`의 [CI 39353715116](https://github.com/junggyeol4444/AIWACK/actions/runs/39353715116)는 **success**. 로그에서 기존 루트 테스트 **133 passed**, Windows 통합 소스의 총괄 복구·모델 실행 타깃 회귀 테스트 **48 passed**를 확인. 이는 GUI/실제 GGUF 검사 성공과 별개임.
- 동일 코드에서 [Windows 2025 회사 GUI·SQLite 로그인/저장 검사](https://github.com/junggyeol4444/AIWACK/actions/runs/39353715141)의 Windows 2025 job은 **success**; Windows 2022 job은 당시 **진행 중**.
- 동일 코드에서 [Windows 2022/2025 EXE 배포 실행](https://github.com/junggyeol4444/AIWACK/actions/runs/39353715118)과 [실제 GGUF 전 직원 호출/두 업무](https://github.com/junggyeol4444/AIWACK/actions/runs/39353715139)는 당시 **진행 중**, 결과 확인 전 PASS 금지.
- 인수인계 문서만 갱신한 후속 main `0e144bb5c4f0bd7637afbb5c6e455bdb3c716267`의 [CI 39354006241](https://github.com/junggyeol4444/AIWACK/actions/runs/39354006241)도 **success**. 이는 기능 검증 범위를 추가로 넓힌 것은 아님.
- 이번 실행의 저장소 비교 결과 `2f6e119c...` → `0e144bb5...`는 기존 원본 파일 **삭제 없이** `model_runtime.py`, `test_company_chief_review.py`, `test_local_models.py`, 이 인수인계 문서만 수정됨. 최신 Actions 상태는 새 회차마다 반드시 다시 조회한다.

## 11. 2026-10-20 다중 미완료 항목 통합 개발·검증

- 본 회차는 개별 기능 하나를 수정하고 검증한 뒤 다음으로 넘어가는 방식 대신, 기존 Windows 네이티브 프로젝트의 **여러 미완료 작업을 한 Git 커밋에 묶어** 개발하고 변경된 코드와 기존 복구·배치·모델 흐름을 함께 검증했다.
- 변경 1: `company_operations.py`에 로그인한 소유자에게 현재 실행 가능한 총괄 승인/직원 모델 연결 업무 목록을 읽기 전용으로 보여주는 `list_approved_chief_queue_candidates` 추가. 단순 목록 조회는 AI를 실행하거나 DB를 변경하지 않는다.
- 변경 2: `execute_approved_chief_queue`에 `expected_task_ids` 검증 추가. GUI의 실제 소유자 확인과 실행할 업무 번호를 고정해, 확인창 열린 도중 또는 배치의 첫 실행 후 다른 세션이 업무를 추가/삭제/교체하면 남은 업무 실행을 차단한다. 보고서·결과물 자동 승인 및 중복 직원 실행 불허 유지.
- 변경 3: `inspect_recovery_state`에서 과거 `ai_model_call_history.status='running'` 기록을 별도 SQL 조건/최대 200건으로 읽기 전용 집계하여 총괄 호출/진단 중단 잔재를 놓치지 않도록 함. 소유자 확인 없이 종료, 재실행, 실패 상태로 덮어쓰기 금지.
- 변경 4: `company_office_gui.py`의 승인 대기열 시작 팝업에 **정확한 승인 업무 ID·제목** 표시, 확인된 ID만 실행 함수로 전달. 결과물 보기 요약에 미종료 모델 호출 감사와 조회 상한 초과 상태 표시. 소유자 기존 흐름과 계정 저장 보존.
- 기존 `tests/test_company_approved_autocycle.py`와 `tests/test_company_chief_review.py`에 경계 조건 테스트 3개 추가: read-only 승인 목록/재로그인/소유자 승인 정상 실행, 배치 중 대상 교체 후 다음 모델 차단, 미종료 모델 감사/프로그램 재시작.
- 커밋 전 최신 실제 통합 소스 아티팩트 `AIWACK_Integrated_Source_windows-2022`를 풀어 원본 GUI/SQLite/직원 모델을 보존하고 이 4개 소스/테스트 파일을 한 번에 수정함. 실행: `python -m compileall -q desktop` 성공; `pytest tests/test_company_approved_autocycle.py tests/test_company_chief_review.py tests/test_local_models.py` **59 passed**; `python -m desktop.entry --self-test` 0; `PYTHONPATH=. xvfb-run -a python scripts/company_office_gui_smoke.py` PASS. 이 로컬 테스트는 리눅스 호환/합성 모델 시험이며, 사용자 Windows11·실제 GGUF 통합 시험을 대체하지 않는다. Python 전체 `pytest -q`는 3%에서 180초 타임아웃으로 완료 판정 불가. 더 넓은 선택 테스트도 65%에서 제한 시간 도달; PASS라 선언하지 않는다.
- 실제 GitHub main의 테스트는 최신 수정 소스 커밋과 **동일 SHA**로 실행되는 Windows 2022/2025 GUI·EXE·실제 GGUF Actions를 별도 확인해 갱신. 이전 `335071010...`의 네 Actions [CI](https://github.com/junggyeol4444/AIWACK/actions/runs/39353715116), [EXE](https://github.com/junggyeol4444/AIWACK/actions/runs/39353715118), [회사 GUI](https://github.com/junggyeol4444/AIWACK/actions/runs/39353715141), [실제 GGUF](https://github.com/junggyeol4444/AIWACK/actions/runs/39353715139)는 이전 커밋에서 모두 PASS였음. **이번 새 소스의 PASS가 아님**.
- T01~T20 전체 완료 판정 보류. 24시간 자율 반복/직원 31인 실질 협업/Stage63 고부하 병렬 추론/실제 외부 도구·거래/사용자 개인 Windows10·11 물리 장치 검증은 남음. 예약, 다른 프로젝트, 새 브랜치, 원본 삭제, 사용자 DB 초기화 없음.

### 11절 추가 통합 회귀 오류 발견·수정 및 자동화 검증 범위 확대
- 최초 다중 기능 변경을 저장한 `c78f3171c1a8397443130a152d428affbc8d7a8a`의 [CI](https://github.com/junggyeol4444/AIWACK/actions/runs/39357210767)는 PASS. 실제 Windows 2022·2025 EXE GUI·SQLite 및 GGUF workflow는 이 문서 추가 당시 진행 중이므로 별도 최종 결과 확인 필요.
- 통합 로컬 pytest를 회사 승인 업무·총괄 복구·GGUF 어댑터·회사 운영센터·모델 연결·업무 실행·병렬 실행 **7개 기존 테스트 파일 전체로 확대**하자 **101 passed / 1 failed**. 실패: `test_real_two_local_subprocesses_overlap`가 실제 프로세스 실행은 겹쳤을 수 있으나 프로세스 준비+SQLite+스레드 시간을 합친 1.5초 절대 기준에 1.57초가 걸려 FAIL. 단일 병렬 테스트만 실행했을 때는 통과하던 취약한 검증 기준임.
- `tests/test_task_parallel.py` 기존 Linux 로컬 실제 실행기 fixture는 subprocess `time.monotonic()` 시작·종료 값을 출력하도록 수정. 두 실제 모델 프로세스의 작업 구간에 **실제 교집합이 있는 경우만** 병렬 실행 PASS. CPU/SQLite 인증 지연 시간을 순수 모델 병렬도 검증에 더하지 않음. 하위 프로세스를 가짜 호출로 바꾸지 않았고, 모형 GGUF 테스트임을 그대로 표시.
- 동일 **7개 묶음 테스트를 수정 후 전체 재실행 결과: 102 passed (41.94s)**. 병렬 단독 9 passed, 기타 관련 회사 GUI 3개 Xvfb 실제 Tkinter 스모크 PASS, EXE 데이터 진입점 self-test 0. **이 결과는 Linux 로컬 테스트이며 Windows 2022/2025 실제 EXE/GGUF 결과를 대체하지 않는다.**
- `.github/workflows/ci.yml`의 Windows 통합 코드 기본 회귀 명령을 2개 파일에서 위 7개 파일로 확대하여 매 push마다 과거 승인 대기열·총괄 복구·병렬 업무·모델 연결과 기존 회사 운영 기능을 다시 검증. 단일 기능 수정 후 과거 기능 오류가 방치되지 않도록 함.
- 다음 검증: 이 소스/CI 커밋 SHA에서 [CI](https://github.com/junggyeol4444/AIWACK/actions) 결과와 실제 Windows Server 2022/2025 회사 GUI·EXE 빌드·진짜 GGUF 검증 결과 및 실패 로그를 동일 SHA 기준으로 확인, 오류 발생 시 재수정. 개인 Windows10/11 물리 PC와 T01~T20 전체 인수는 미검증 유지.

### 11절 최종 통합 테스트·실제 Windows 검증 업데이트

- 최초 기능 통합 코드 `c78f3171c1a8397443130a152d428affbc8d7a8a`는 다음 두 GitHub Windows Server 매트릭스 검사에서 **2022/2025 양쪽 PASS**: [EXE 빌드·실제 시작·GUI 클릭·SQLite 재시작](https://github.com/junggyeol4444/AIWACK/actions/runs/39357210770), [회사 GUI 설정 저장·종료·재시작](https://github.com/junggyeol4444/AIWACK/actions/runs/39357210723). [실제 GGUF](https://github.com/junggyeol4444/AIWACK/actions/runs/39357210772)는 마지막 조회 시 아직 실행 중.
- 그 뒤 병렬 프로세스 실행 구간 검사와 7개 테스트 파일 CI 자동 포함을 반영한 새 커밋 `ffa8931b56f0cbc17cf7d05973b6f623705261c1`. [CI #39357846210](https://github.com/junggyeol4444/AIWACK/actions/runs/39357846210) **최종 SUCCESS**. 로그에서 기존 루트 **133 passed**, `windows-integrated-src` 승인 업무/복구/실제 subprocess 병렬/직원 모델 연결/회사 운영 7개 기존 테스트 파일 **104 passed**, 합계 **237 passed**를 실제 확인. Linux 호환/합성 측정 포함, Windows 실물 사용자의 테스트와 혼동 금지.
- 같은 `ffa8931b...`의 [Windows 회사 GUI #39357846337](https://github.com/junggyeol4444/AIWACK/actions/runs/39357846337)은 **Windows2022/2025 양쪽 SUCCESS**. [Windows EXE 배포 검증 #39357846331](https://github.com/junggyeol4444/AIWACK/actions/runs/39357846331) 및 [실제 GGUF 직원/총괄 추론 #39357846294](https://github.com/junggyeol4444/AIWACK/actions/runs/39357846294)는 이 기록 당시 **in_progress**, PASS 판정 금지. 실제 종료 여부 재조회할 것.
- 재현 가능한 로컬 검증 결과는 `102 passed in 41.94s` (초기 101 passed/1 failed 병렬 절대시간 경계 오류를 **실제 subprocess 실행구간 중첩 검사로 수정 후**), GUI `COMPANY_OFFICE_LIVE_GUI_PASS`, `PHYSICAL_CHIEF_REVIEW_OWNER_ACCEPT_NO_AUTO_TASK_COMPLETION_PASS`, `REAL_MOUSE_CHIEF_ORDER_OWNER_APPROVAL_WITHOUT_EXECUTION_PASS`, `desktop.entry --self-test` 반환 0. **전체 네이티브 프로젝트 무제한 pytest**는 작업상 시간 초과로 완결하지 못함; 성공이라고 주장하지 않음.
- 다음 작업 우선순위: 최신 `ffa8931b`의 Windows EXE·실제 GGUF 2플랫폼 최종 결과/아티팩트 확인→로그 기준 오류 수정 및 7개 묶음 재검사. 이후 Stage63 장시간 병렬 추론·강제 종료 복원 전체 흐름, 24h 자율 반복, 31명 실질 협업, 도구/사업 흐름, 원본 T01~T20 실제 통합검증을 기존 Windows EXE에서 완성. 사용자 직접 요청 없이 예약/다른 저장소/드라이브/브랜치 변경 금지.

## 12. 2026-10-20 배치 구현: 비상정지/취소 후 모델 및 직원 결과 영속 저장 차단

- 개발 시작 `main` HEAD `8e77045f1b9e033f918b1a21e9d2fa7b0e3a600d`. 이전 `ffa8931b...` Windows 2022/2025 EXE 빌드와 회사 GUI 테스트는 PASS, 실제 GGUF 새 검사 `39357846294`는 이 회차 조회 시 실행 중.
- 이번에는 다섯 개 기존 런타임 소스(`task_runtime.py`, `employee_model_runtime.py`, `company_operations.py`, `storage.py`)에 하나의 연관된 안전 수정 묶음을 적용했다.
- 실제 로컬 직원 추론/수동 직원 모델 진단은 하위 프로세스 정상 종료 직후에도 관리자 취소 플래그와 SQLite 비상정지 여부를 다시 확인한다. 취소/정지 후 응답은 실패/취소 감사 기록을 보존하고 결과를 반환하지 않는다.
- `storage.py`의 `finish_task_execution` / `finish_employee_model_call`는 SQL `BEGIN IMMEDIATE` 경계에서 비상정지 발생 이후 성공 처리 및 출력 길이 저장을 막는다. 상태를 실패로 기록·기존 감사 보존 후 PermissionError로 caller에 전달한다. `save_task_artifact`에도 같은 SQLite 트랜잭션 내부 stop guard를 추가하여 late-result 저장 경합을 막는다.
- `company_operations.py`의 execute_task는 진단 모델 호출이 끝났더라도 취소/비상정지가 뒤늦게 적용되면 결과물 저장을 하지 않는다.
- 기존 테스트의 위험했던 가정(모델 추론 도중 취소나 비상정지를 해도 결과물을 저장한다)을 안전한 실패/차단 기대 결과로 수정함. 기존 `test_task_execution.py`에 4개, `test_company_model_onboarding.py`에 2개 새 안전 회귀 테스트를 추가.
- **원본 전체 7개 통합 테스트 파일 재실행: 110 passed**. 처음 점검 중 `PermissionError`가 `OSError` 처리보다 뒤에 있어 감사 오류 레이블이 거부되는 FAIL을 실제로 발견, 처리 순서를 변경하여 재검사했다. Linux 테스트 subprocess 실행기 Python 시작 지연 때문에 한 차례 타임아웃이 발생하여 child PATH를 Python 기본 시스템 실행기로 고정 후 동일한 110개 검사를 다시 완료했다. 비상정지/취소와 하위 모델 프로세스의 트랜잭션 경합을 모의한 합성 검증이며 Windows Server EXE 실사용 성공 근거가 아님.
- EXE 진입점 `python -m desktop.entry --self-test`: PASS. 회사 운영센터 Tkinter `xvfb-run -a python -m scripts.company_office_gui_smoke`: PASS.
- 남은 의무: 동일한 새 커밋에서 루트/네이티브 통합 CI, Windows 2022/2025 실제 EXE·SQLite·직원·총괄 GGUF 실사용 액션 결과를 확인하고 FAIL이면 전체 배치 오류 수정 후 재검사. 사용자 개인 Windows 10/11 실기기 직접 검증은 불가/미검증. T01~T20 전체 인수, 장시간 자동 운영/다수 AI 협업/외부 도구 및 사업 거래는 미완료.
- 사용자 요청 없이는 예약 상태와 다른 프로젝트/드라이브/브랜치를 변경하지 않는다.

### 12절 Windows 2022 실제 GGUF 네이티브 종료 오류의 검증 경로 보강
- 실제 Windows Server 2022 [GGUF Actions #39360004947](https://github.com/junggyeol4444/AIWACK/actions/runs/39360004947)는 공식 `llama-completion.exe`의 사전 진단 단계에서 FAIL. 성공한 텍스트가 stdout으로 생성됐지만 종료 코드 `3221226356 / 0xC0000374` (Windows heap corruption)를 반환함. artifact `12236818257`의 `aiwack-llama-preflight.txt` 직접 확인. **AIWACK GUI는 해당 실패 회차에서 실제로 실행되지 않았으므로 E2E PASS가 아님.**
- 기존에 실제로 다운로드·SHA256 확인하는 **동일한 공식 llama.cpp CPU 배포 ZIP** 내의 `llama-cli.exe`를 다른 후보로 엄격히 검증할 수 있는 `validation/real_gguf_preflight.py` 추가. 우선 `llama-completion.exe`로 진짜 GGUF를 추론하고 정상 종료/비어있지 않은 응답일 때만 허용. 힙 손상 등 비정상 종료이면 해당 실패를 증거에 남기고 같은 검증 배포본의 `llama-cli.exe`를 1회 진짜 추론. 대체 실행기가 정상 종료/출력한 경우에만 실제 GUI/E2E 단계로 진행하고 선택한 경로를 GitHub 환경변수로 넘김. 두 실행기가 모두 실패/출력 공백이면 **FAIL을 유지**하며 모델 응답 텍스트만으로 성공을 위조하지 않음.
- 기존 `validation/windows_packaged_real_gguf_queue_e2e.py`는 위 사전 진단에서 선택한 공식 `llama-completion.exe` 또는 `llama-cli.exe`를 허용. 31명 실 GGUF 호출, 두 승인 업무, 실제 GUI 마우스 클릭, SQLite 결과 감사 등 **기존 강제 검증 조건은 완화하지 않음**.
- `tests/test_real_gguf_preflight.py`에 모의 subprocess 기반 5개 안전/호환성 테스트 추가. **로컬 5 passed**. 이는 실제 Windows 2022 대체 실행기 성공을 증명하지 않는다. 최종 Windows Server 2022/2025 액션에서 결과 확인 필요.

### 12절 CI/Windows 실제 실행 결과 재확인

- 현재 제품 코드 기준 commit `165b6255f73087160ddd7579f876398f5b76b332`: [CI #39360520281](https://github.com/junggyeol4444/AIWACK/actions/runs/39360520281) **최종 SUCCESS**, 로그에서 루트 **138 passed** + 기존 Windows 네이티브 승인·복구·직원 모델·병렬·회사 운영 **110 passed** = 통합 두 묶음 **248 passed** 직접 확인. 새 root 5개 사전 진단 단위 테스트 포함.
- `a7e047de...` 보존된 Windows 2022/2025 [회사 GUI·SQLite 종료/재실행 #39360004877](https://github.com/junggyeol4444/AIWACK/actions/runs/39360004877) SUCCESS 및 [Windows EXE 실행 #39360004935](https://github.com/junggyeol4444/AIWACK/actions/runs/39360004935) 2022/2025 SUCCESS. `a7e...` Windows 2022 **실제 GGUF #39360004947 FAIL**: 공식 `llama-completion.exe` 사전 진단 힙 손상(0xC0000374); 실제 EXE GGUF 업무 검사 전에 멈춤. 이 FAIL은 이후 검사 통과로 숨기지 말 것.
- `165b6255...` [Windows 2022/2025 GGUF 실제 EXE #39360520310](https://github.com/junggyeol4444/AIWACK/actions/runs/39360520310)는 마지막 조회 시 양쪽 **공식 GGUF 실제 추론 프리플라이트 통과 후 패키지 EXE GUI 클릭·2업무·31명 모델 검증 단계 in_progress**. 최종 PASS 아님. 실제 선택된 실행기/후속 업무 성공 여부는 job 종료 및 artifact로 확인해야 함.
- `165b6255...` [Windows 2022/2025 EXE·GUI·SQLite #39360520276](https://github.com/junggyeol4444/AIWACK/actions/runs/39360520276)는 마지막 조회 시 **in_progress**, 결과 확정 전 PASS 표기 금지.
- 과거 정상으로 검증된 `ffa8931b...` Windows 2022/2025 실제 EXE·GUI 및 GGUF [#39357846294](https://github.com/junggyeol4444/AIWACK/actions/runs/39357846294) 성공은 이번 변경의 증거가 아니므로 커밋 구분.
- 이 배치의 안전 변경 목적은 비상정지/취소 시 기존 실행·모델 호출 감사와 저장 결과를 일치시켜 정상 완료 오판을 없애는 것. 사용자 직접 물리 Windows 10/11 환경, T01~T20 전체 인수, 장기 자율 운영/다중 AI 실질 협업/외부 도구 및 실제 사업 거래는 미검증.

## 13. Windows 네이티브 2직원 동시 업무 실행과 총괄 검토 (다중 기능 통합 개발)

- 시작 main HEAD: 76fb2a8a3c8de8f270ea1550fbcd0141758f1d61. 직전 main 제품 코드 `165b6255...`는 Windows Server 2022/2025 EXE build, GUI SQLite, 실제 GGUF 직원·총괄 2업무 검증 모두 success; 개인 Windows10/11 실기기 테스트는 미완료.
- 기존 `desktop/company_operations.py`에 read-only `list_approved_parallel_candidates` 추가: 승인된 업무이며 모델이 연결된 서로 다른 직원 AI가 배정된 2건의 ID/제목/담당 직원 목록 제시.
- `execute_approved_parallel_cycle`는 관리자가 정확히 확인한 2개 업무 ID와 **2개 직원 ID**를 검증한 후 스레드 2개로 실제 `execute_task`를 병렬 실행. 기존 DB의 실행 동시 한도 2, 직원별 고유 실행, 업무 선행조건, 승인된 총괄 지시, 비상정지 및 취소 제어, 각 실행의 독립 SQL 감사 기록을 그대로 사용한다. 하나 실패하면 다른 프로세스에 취소 요청하고 다음 총괄 AI 검토를 하지 않는다. 성공 시 두 결과물을 저장하고 같은 총괄 AI는 순차 검토하며 관리자 최종 승인 대기로 유지한다. 자동 판매·결제·보고서 수락·업무 완료·무단 반복 없음.
- `desktop/company_office_gui.py` 업무 지휘실 상단에 **'승인 AI 2명 병렬'** 버튼을 추가하고, 실 실행 전 업무 ID·직원 ID·제목을 보여주는 실제 관리자 확인창 및 결과 상태 표시 구현. 기존 비상정지 버튼이 화면에서 밀려 사라지지 않도록 하단 제어행에 새로운 버튼을 추가하지 않고 기존 상단 줄에 배치.
- 기존 테스트를 삭제하지 않고 `tests/test_company_parallel_approved_cycle.py`에 병렬 worker 2명 실제 겹침 확인, 총괄 순차 검토/SQLite 재시작 pending 보존, 사전 확인 ID/직원 불일치·미승인 업무 차단, 한쪽 실패 시 다른 worker 취소·총괄 비실행, 비상정지 후 결과물 저장 거부의 4개 synthetic 병렬 회귀검사 추가. 이 fixture는 진짜 GGUF가 아니라 SQLite+모델 실행 파이프라인 검증임.
- 로컬 검증: 새 4 tests PASS, 기존 approved cycle+신규 합계 16 PASS, 병렬 하위 프로세스·모델 연결 포함 선별 25 PASS, Tkinter `COMPANY_OFFICE_LIVE_GUI_PASS`. Python compileall desktop PASS. 로컬의 전체 8개 테스트 파일 pytest는 느린 리소스로 제한시간 내 완료되지 않아 통과 주장 금지.
- `.github/workflows/ci.yml`와 `.github/workflows/windows-exe.yml` 모두 새 병렬 회귀 테스트를 기존 통합 테스트들과 함께 실행하도록 수정. Windows EXE 자체 및 실제 GGUF GUI 워크플로는 새 동일 SHA의 최종 Actions로 확인 후 성과 구분.
- 계속 남음: 한 화면에서 다수 직원의 장시간 협업과 실제 다중 업무 반복 자율 운영, 부서 간 의존 업무, 외부 서비스·거래, 원본 T01~T20의 전 항목 최종 인수; Windows 10/11 사용자 PC에서 EXE 물리 테스트.

### 13절 병렬 비상정지 경합 결함 발견·수정

- 병렬 기능 최초 통합 main 1588e48c... CI 39366115900 FAIL. 네이티브 회귀 114개 중 113 PASS, 1 FAIL. 관리자 비상정지에서 첫 직원은 failure, 동료는 취소를 받아 cancelled가 될 수 있는데 테스트가 둘 모두 failure를 잘못 강제했다.
- 반복 실행에서 동일 비상정지 상황이 예외 수집 순서에 따라 InterruptedError를 먼저 표시하는 실제 문제도 발견. 병렬 실행 예외를 비상정지 PermissionError 우선으로 결정하게 수정했다.
- 결과물 저장 금지 유지, 오류 감사 failure/cancelled만 허용, 실제 비상정지 UI 오류는 PermissionError로 전달. 로컬 신규 테스트 4개를 다섯 번 반복 실행해 매회 모두 PASS. 동일 SHA 전체 Windows EXE/GUI/GGUF 검사 통과 전에는 최종 성공 표기 금지.

### 13절 병렬 후보 선행 의존 업무 오류 수정

- 승인 병렬 2명 실행의 읽기 전용 후보 조회가 선행 업무 완료 여부를 확인하지 않아 미완료 의존 업무를 사용자 확인창에 올릴 수 있었음. 실제 SQL 실행 트랜잭션에서는 차단됐지만 혼동 및 배치 실패를 초래하는 후보 검증 버그로 확인.
- 기존 LocalStore._pending_prerequisites를 읽기 전용 트랜잭션으로 재사용해 미완료 선행 업무 제외. 최종 실행의 원래 트랜잭션 차단은 유지. 다른 독립 직원 업무로 정상 후보를 대체하는 회귀 테스트 추가.
- 수정 후 신규 병렬 테스트 5개 PASS. 동일 SHA Windows EXE/CI 검증 결과 확인 필요.

## 14. Windows 실 GGUF 직원 2명 병렬 실행·총괄 회수 통합 검증 추가

- 최초 병렬 구현 코드의 로컬 합성 모델 병렬 테스트만으로 실제 Windows GGUF 동시 실행 성공을 주장하지 않음. 새 검증 스크립트 validation/windows_real_parallel_company_e2e.py는 Windows 전용으로, 사전 SHA256 검증한 공식 llama.cpp CPU 실행기와 실제 GGUF를 이용해 기존 AIWACK native 저장소에서 소유자 계정·총괄 AI·직원 2명을 설정한다.
- 정확한 소유자 승인 업무 ID·직원 ID를 전달해 실제 GGUF 직원 2명 동시 실행, 진짜 총괄 AI 모델 순차 검토 2건, 총 4회 실제 모델 감사, 결과물/회수 보고서 모두 관리자 승인 대기, SQLite 무결성·재시작 후 상태를 확인한다. 자동 승인·외부 거래·더미 모델 통과 불허.
- 기존 Windows 2022/2025 workflow validation-windows-real-gguf-queue.yml에서 기존 packaged AIWACK.exe 실제 물리 GUI 마우스·키보드 E2E가 성공한 후 위 native 병렬 실 GGUF 검사를 추가. 두 검사는 분리되어 있으며 새로운 native 병렬 검사를 EXE 버튼의 물리 클릭 성공으로 과장하지 않는다.
- 실패 시 job FAILURE, 모델/시스템 오류 감춰서 성공하지 않음. 검증 메타데이터 JSON을 기존 증빙 artifact에 포함. 동일 SHA Windows 2022/2025 job 결과 검증 완료 전 해당 실제 병렬 GGUF 통과로 기록하지 말 것.

### 14절 Windows 실 GGUF 병렬 검증 오류 수정 및 실제 추론 시간 중첩 검사

- main 94c194425...의 Windows Server 2022/2025 GGUF 검증 run 39367357588에서 실제 병렬 직원 2명·총괄 검토·재로그인까지 통과 메시지가 출력됐으나, 검증 스크립트의 sqlite3.connect() context manager가 연결을 닫지 않아 TemporaryDirectory 정리 시 WinError 32로 전체 Actions FAIL. 다음 run 39367632430 Windows 2022 역시 동일 원인 FAIL.
- validation/windows_real_parallel_company_e2e.py의 SQLite 무결성 확인 함수를 명시적 try/finally + con.close로 분리. 테스트 완료 표시를 임시 DB가 실제 닫히고 정리된 다음에만 출력하도록 변경. PermissionError를 무시하거나 Windows 검증을 건너뛰지 않음.
- 실제 GGUF 병렬 증거를 강화: 모델 응답을 대체하지 않고 기존 task_runtime.run_local_model 호출 시간을 두 직원별로 기록, 실제 모델 추론 구간에 양의 중첩 시간이 있는지 확인. 없으면 FAIL. 모의 직원 모델은 사용하지 않는다.
- 루트 tests/test_windows_real_parallel_validation.py에 SQL 무결성 정상/오류 종료 후 DB 파일 삭제, 두 실제 실행구간 중첩 판정, 구간 측정 누락 거부 테스트 6개 추가. 새로운 Windows 2022/2025 실제 GGUF 결과는 동일 SHA Actions 종료 후 별도로 확정할 것.

## 15. 2026-10-20 반복 일정·대기열 동시 창 안정화 및 네이티브 테스트 경로 복구

- 기존 main `fda3bc24...` CI #39369215255 FAIL은 실제 모델이나 회사 앱 코드 실패가 아닌 신규 루트 검증 테스트 파일에서 두 `desktop` 패키지의 경로가 충돌해 발생했다. 루트 `tests/test_windows_real_parallel_validation.py`를 없애고 기존 Windows 네이티브 프로젝트의 `windows-integrated-src/tests/` 아래로 이동, 해당 테스트에서 루트 validation 경로만 직접 등록한다.
- 기존 여러 Windows EXE 창/다중 소유자 로그인 세션에서 `recurring_scheduler.dispatch` 및 `task_queue.claim`, resolve, recover 간 SQL SELECT→UPDATE 경합을 막기 위해 `LocalStore` 기존 wrapper에 `BEGIN IMMEDIATE` 사용. SQLite 트랜잭션 내에서 업무/일정·감사 기록을 일관되게 commit/rollback한다. 정지/승인·로그인 흐름 변경이나 새로운 자동 외부 실행 없음.
- 기존 task_queue.claim에서 상태가 이미 바뀌어 SQL UPDATE 변경 건수가 0건인 경우, 성공 로그를 추가하거나 해당 작업을 내 작업으로 반환하지 않도록 rowcount guard를 추가. 기존 반복 일정 validator의 `bool` 타입을 정수로 착각하는 입력도 차단.
- 새 네이티브 `tests/test_concurrent_scheduler_and_queue.py`: 같은 SQLite DB를 소유자 두 세션이 동시에 열어 같은 시각 반복 일정 생성 1회, 대기열 작업 claim 1회, 완료 결과 처리 1회만 기록되는지 검사; 비정상 bool 인자 거부. 로컬 기존 일정·대기열·복구 테스트와 합쳐 **12 passed**.
- 네이티브 CI와 Windows 2022/2025 EXE 빌드 테스트에 동시 창 검사·파일 잠금 검증 및 기존 회귀를 포함. 새 GitHub main SHA 동일 기준으로 CI/EXE/실제 GGUF 결과 확인 후에만 통과 판정.

### 15절 Windows 2025 공식 GGUF 실행기 힙 손상에 대한 추가 검증

- main 917bc65d... Windows 2025 실제 GGUF run 39369750285 FAIL은 AIWACK EXE 실행 전, 공식 llama.cpp b11433의 `llama-completion.exe`와 `llama-cli.exe` 두 프로세스가 모두 종료 코드 `3221226356 (0xC0000374)`를 반환한 원인으로 확인. 증빙 artifact 12240333540 내용: completion returncode=3221226356 has_output=True, cli returncode=3221226356 has_output=True. 출력이 있어도 실제 추론 성공으로 처리하지 않는다.
- 동일 GitHub 공식 저장소의 2026-10-20 발행 b11748 Windows CPU zip SHA-256 `59083a1df768be176d851ddbab6bbde2d8a67a1ea7f1d42f770753d13dc74f60`을 조회해 고정. Windows Actions는 기존 SHA 고정 b11433 실제 추론이 실패한 때에만 새 b11748 공식 배포 ZIP을 다운로드/검증하고, 두 실행기 중 하나가 실제 GGUF를 정상 반환·정상 종료하는지 다시 확인한다. 정상 추론이 아니면 FAIL이며 어떤 테스트도 생략하지 않는다.
- 기존 실패 진단과 신규 배포본 진단을 모두 같은 Windows artifact에 보관, 성공한 모델 실행기 경로를 앱의 실제 물리 GUI 및 병렬 업무 검사에 그대로 전달. 사용자 배포용 model setup 스크립트는 검증 결과 없이 임의로 변경하지 않음.
- 현재 이 새 검사 커밋은 Windows 2022/2025 실행 결과를 기다리는 상태. 성공 확정 전까지 GGUF 검증 성공으로 보고하지 않는다.

### 15절 반복 일정 24시간 가상 시계 및 비상정지 재개 회귀검증

- 기존 코드 변경에 추가로 5분 주기의 24시간 가상 시계 총 288회 반복 실행을 네이티브 통합 테스트에 고정 등록. 소유자 세션 두 개를 번갈아 사용하고 같은 마감 시각 재실행도 중복을 생성하지 않는지, 생성된 288개 업무가 모두 미배정 todo이고 AI·외부 도구가 실행되지 않는지 검증.
- 비상정지가 켜진 동안 자동 반복 일정 생성과 명시적 대기열 claim이 모두 차단되는지, 소유자가 비상정지를 해제한 후 정상적으로 업무가 단 한 번 생성·claim되는지 검증.
- 로컬 반복 일정·대기열·복구·보안 회귀 포함 **21 passed**. 이는 **실제 24시간 장시간 Windows 실사용 테스트가 아니라 가상 시간 기반 재현 검증**으로 명확히 구분. 본 커밋 새 GitHub CI/Windows 결과는 실행 종료 후 확인해야 함.

## 16. 2026-10-20 다중 미완료 기능 통합 구현 — 승인 31건 직원 공동운영

- 기존 사무직 31명 및 15개 부서/총괄 AI 구성 코드를 그대로 사용하면서, 모델이 연결된 **기존 소유자 승인 업무 최대 31건**을 영속 manifest로 고정하고 직원 AI 최대 2명을 동시 실행·총괄 AI 순차 검토하는 `desktop/company_campaign.py` 추가.
- 하나의 승인된 장기 운영 작업을 만들면 각 업무의 고정 ID·직원 ID·순번·상태·결과물 ID와 운영 작업 상태를 SQLite에 지속 기록. 실제 로컬 GGUF는 기존 `company_operations.execute_task`로 실행되고, 총괄 보고서 역시 기존 `collect_chief_review`을 호출한다. 자동 승인·최종 완료·재시도·결제·외부 게시 없음.
- 다중 창에서 같은 운영 작업의 중복 실행은 상태 변경을 `BEGIN IMMEDIATE`로 직렬화하여 차단. 한 작업에서 오류/중단 발생 시 관련 감사 기록을 보존하고 진행 중 항목은 `needs_review`로 잠금. EXE 재시작 후 중단 기록을 읽을 수 있지만 중단된 직원 모델을 자동으로 다시 돌리지 않는다.
- 운영센터 업무 지휘실에 `31명 승인 연속 운영`, `운영 기록 확인` 버튼 추가. 실행 전에 각 실제 업무·담당 직원 ID와 제목을 보여주고 소유자 명시 확인 필요. 기존 비상정지/회사 데이터 보존.
- `tests/test_company_campaign.py`에 실제 SQLite 다중 업무·총괄 감사/프로그램 재로그인·승인 ID 변경 거부/강제 중단 감사·비상정지·실패 후 자동 재시도 금지 5개 합성 회귀 테스트 추가. CI 및 Windows EXE 통합 회귀 목록에 포함.
- 남음: AI가 스스로 새로운 업무를 지속적으로 기획/승인해 외부 판매까지 수행하는 전체 24시간 자율 운영, 31명 실물 모델 전원 동시 실행, 실제 외부 도구/거래·T01~T20 전체 완성은 아직 아님. 테스트 통과와 실제 Windows EXE/실제 GGUF 결론을 섞지 않음.

### 16절 실제 로컬 업무 산출물·검수·안전 파일 출력 기능 통합 구현

- 기존 `company_task_artifacts`의 실제 직원 모델 출력과 소유자 검수 기록을 그대로 연결하는 `desktop/company_deliverables.py` 추가. 생성된 텍스트의 저장 SHA256 일치, 중복 본문, 짧은/임시 본문 경고를 **기계적 품질 보고서**로 제공하며 내용의 진위/완성도를 AI가 자동 승인하지 않는다.
- 승인 전 결과물은 파일로 내보내기 금지, 승인 후 운영센터 버튼을 관리자가 직접 눌러 `AIWACK_DATA_DIR/approved_deliverables` (기본 사용자 로컬 데이터 폴더)에 Markdown 파일 생성. 모델 제목을 파일 이름에 사용하지 않아 경로/파일명 오염 차단. 파일은 `O_EXCL` 신규 생성 및 `fsync`, 같은 승인 산출물을 재실행해도 내용 일치할 때만 idempotent, 외부 수정 파일 덮어쓰기 거부, 심볼릭 링크 대상 거부.
- SQLite `aiwack_deliverable_exports`에 SHA256·파일명 감사 기록 저장/재로그인 조회. 저장된 파일을 다시 검사해 누락/변조 확인할 수 있음. 외부 게시·판매·결제·코드 실행·자격증명 연동 없음.
- 회사 운영센터 결과 화면에 `결과물 품질 검사`, `승인 결과 파일 저장` 버튼 추가. 기존 승인/반려/최종 업무 완료 버튼 유지.
- 기존 실제 SQLite 산출물 생성 및 소유자 검수부터 저장/재로그인/파일 변경 방지/심볼릭 링크 거부까지 통합 검증하는 네이티브 테스트 5개 추가, GitHub CI/Windows EXE 회귀에 포함.

### 16절 장기 운영용 실제 SQLite 라이브 백업·무결성 점검·분리 복구

- 기존 회사 데이터가 수개월 쌓여도 장애 전 기록을 잃지 않도록 새 `desktop/company_backup.py` 구현. sqlite3의 일관성 있는 online backup API로 Windows EXE 실행 중 별도 SQLite 파일을 생성하고 종료 뒤 무결성·외래키 검증, SHA256 메타데이터 기록. 생성 도중 파일은 정식 백업으로 표시하지 않음.
- 소유자만 운영센터 상단의 `회사 DB 백업`, `백업 무결성 확인` 버튼을 사용. 기존 실행 중인 SQLite DB 파일을 덮어쓰지 않으며 복구 기능은 별도 `restore_into_new_copy`가 임시 후보 파일로만 만든다. 자동 복원·데이터 초기화·외부 업로드·네트워크 호출 없음.
- Windows 파일 핸들 정리 및 스냅샷 2회 독립 생성·실제 수정된 라이브 DB 보존·변조 검출·잘못된 경로 거부·비상정지 상태에서 백업 5개 테스트를 기존 Windows 네이티브 CI에 추가.

### 16절 실제 Windows GUI 승인 버튼 회귀 오류 및 플랫폼 테스트 수정

- 5aa136b6...의 실제 Windows 2022/2025 GGUF EXE 검사 run 39372215738 FAIL: 실물 EXE 마우스·키보드 검사에서 총괄 보고서 관리자가 수락한 뒤 원래 위치를 누른 결과물 승인이 실행되지 않아 SQLite `review_status`가 `pending` 유지. 모델은 실제 호출됐고 이것은 DB 자동 승인 오류가 아니라 결과 화면에 추가된 품질/내보내기 버튼 때문에 원래 승인 버튼이 밀린 GUI 배치 회귀로 확인.
- 품질 검사·파일 저장 버튼을 결과 화면 상단에서 하단의 기존 복구 버튼 줄로 이동해 원래 `결과 열기 / 승인 / 수정 요청 / 반려` 버튼 순서를 보존. 사용자 수동 승인 및 실제 Windows 물리 마우스 검증은 절대 생략하지 않음.
- Windows에서 로컬 경로 파일 이름을 시험할 때 OS별 문자열 구분 대신 Path.name을 사용, 심볼릭 링크 생성 권한이 없는 플랫폼만 해당 별도 테스트에서 명시적으로 SKIP (다른 기능/EXE 검사는 생략하지 않음). 새 SHA Windows 2022/2025 실제 승인·GGUF 결과 재확인 필요.

### 16절 중단된 사내 운영 작업의 실제 총괄 검토 연결·안전 재개

- 승인 31건 운영 기능의 중단된 항목 `needs_review`가 계속 남아 다음 미실행 업무를 재개하지 못하는 것을 보완. 새 `reconcile_manually_recovered_chief_reviews`는 기존 SQLite에 **이미 저장된 직원 결과물 1개 및 총괄 보고서 1개**가 정확히 대응하고 업무가 진행 중인 경우에만 운영 장부에서 `review_pending`으로 동기화. 모델을 호출하거나 결과물 승인·업무 완료·재실행하지 않는다.
- EXE GUI에서 잠시 중단한 운영 작업을 다시 선택할 때, 관리자에게 **기존 검토 기록 연결만** 수행할지 확인. 보고서가 없는 결과는 여전히 수동 확인 필요, 자동 재실행 금지 유지.
- 직원 모델이 이미 1회 실행되어 감사된 상태에서 프로그램이 중단된 예제를 검사: 미완료 보고서가 없을 때는 대기 유지, 기존 총괄 보고서 관리자 수동 생성 후 안전 동기화, 미실행 2건만 새로 실행, 첫 직원 중복 호출 없음.

### 16절 Windows EXE 신규 기능 패키징·실제 Tk 버튼 가시성 통합 검증

- 기존 `Windows` 실제 GGUF 검증에서 새로운 버튼 추가가 기존 소유자 `승인` 버튼을 밀어 정상 마우스 동작이 실패한 사건을 다시 예방하도록, 업무 실행 상단에 몰려 있던 `31명 승인 연속 운영`/기록 버튼을 기존 업무 버튼과 별도 줄에 배치. 기존 `비상 정지` 버튼은 원래 줄·좌표 유지.
- `company_office_gui_smoke.py`의 실제 Tk 윈도우에서 업무 화면·결과 검수 화면·회사 개요 화면의 새로 추가한 실제 버튼들을 탐색하고 `winfo_viewable`, 픽셀 기준 루트 창 안에 완전히 보이는지 검사. 윈도우 그림만 만들고 기능은 생략하는 mock가 아님.
- Windows EXE 빌드 Actions에 위 실제 Tk GUI 검사를 빌드 이전 추가. PyInstaller `--hidden-import`에 신규 campaign/deliverables/backup 세 모듈을 기본 로컬 `.bat`, Windows 2022/2025 EXE, 실제 GGUF E2E, 회사 SQLite GUI E2E 모든 빌드 설정에 동시 반영해, GUI에서 동적으로 import하는 신규 기능이 실제 EXE에 누락되지 않도록 함.
- 최신 동일 커밋 Windows EXE·마우스 클릭·실제 GGUF 검증 완료 전 전체 성공 판정 금지.

### 17절 장기 업무 운영 두 Windows EXE 창의 활성 작업 보호·기본 GUI 검사 경로 오류 수정

- Windows Server 2025 실행 빌드 run 39373643207의 신규 실 GUI 검사는 desktop 모듈 import 경로 오류로 FAIL. CLI를 python -m scripts.company_office_gui_smoke로 수정하고 스크립트 자체에도 프로젝트 루트 경로를 부여해 버튼 가시성 검사 본문을 유지.
- 장기 업무 운영 중 다른 EXE 창에서 아직 진행 중인 작업을 강제 종료된 것으로 오인하지 않도록 SQLite owner-token+heartbeat 임대 기록 테이블 추가. 동시 업무 진행 중 5초 간격 heartbeat, 마지막 기록 90초 이내이면 두 번째 창의 강제 중단 복구 거부; 임대 사라진 진짜 강제 종료만 소유자 확인 후 확인 필요로 변경. 정상 종료/실패 시 자신의 lease만 해제.
- 회귀 테스트 2개: 다른 로그인 창이 실제로 실행 중인 작업의 중단 감사·중복 실행 불가 확인, 오래된 heartbeat 복구 시 직원 자동 재호출 없는 중단 상태 유지. 새 결과의 CI/Windows EXE 통과는 종료 후 별도 확인.

### 17절 31업무 자동운영 실사용 감사 화면·온라인 백업 동시 쓰기 안정성

- 기존 31건 장기 운영 작업을 관리자 화면에서 조회할 때 합계만 표시하던 한계를 개선. 각 직원/업무 ID, 실행 상태, 저장된 산출물 ID를 모두 보여주고, 기존 `company_task_runs`, `company_task_artifacts`, `company_chief_task_reports`의 실제 감사 정보와 운영 장부가 맞는지 **read-only**로 확인하는 `audit_campaign` 추가. 누락/불일치에 경고를 표시할 뿐 DB 데이터 수정·모델 재실행·자동 승인 없음.
- 신규 회귀 검사에서 초기 승인 업무, 직원/총괄 실제 SQLite 감사 생성 후 상태 일치, 관리자가 고의로 결과물 연결을 누락시킨 경우 경고 탐지 및 원본 미변경 검증.
- 실제 SQLite 온라인 백업 중 같은 DB에 다른 스레드가 다중 UPDATE 커밋을 수행하는 상황을 시험해, 백업 생성/해시 검증/무결성 및 원본 데이터 지속 보존 검사 추가. CI와 Windows EXE 기존 회귀 파일에 포함.

### 17절 실제 Windows 운영센터에서 검증된 DB 복구 사본 생성 연결

- 이전 `company_backup.restore_into_new_copy`는 백엔드 코드는 있지만 사용자 EXE 화면에서 눌러 실행할 수 없었다. 회사 현황 화면의 우측 카드에 복구 후보 생성 버튼 추가: 가장 최근 백업의 SHA256·SQLite 무결성 확인 → 관리자 확인창 → 원본 회사 DB 변경 없이 새로운 SQLite 복사본 생성. 자동 교체·복원·데이터 삭제 불허.
- 기존 GUI 가시성 테스트에 신설 버튼 추가. 실제 `LocalStore`가 새로운 복구 후보 파일로 로그인하고 기존 저장된 회사 내용을 확인하는 테스트, 관리자 원본 DB 변경 유지 테스트 및 SHA256 위조된 메타데이터를 거부하고 사본을 생성하지 않는 테스트 추가. Windows EXE 워크플로 기존 통합 회귀에 포함.

## 18. 2026-10-20 관리자 승인 직원 AI 결과의 실제 연속 업무 공유/영구 지식화

- T05/T07 개발: 기존 SQLite 선행/후속 업무 연결과 결과물 감사를 실제 모델 입력에 통합. 선행 업무가 완료(done)됐고 해당 직원 실행 성공, 결과물에 대한 소유자 승인(approved), SHA256 일치가 모두 충족될 때에만 다른 직원의 후속 업무에 850자 이내의 **인용 참고 내용**을 추가. 미승인 자료·명령·변조 결과는 전달하지 않음. 기존 모델 입력 제한 3000자와 소유자 지시·모델 실행 감사는 보존.
- 기존 공동 지식 저장소를 활용하여 소유자가 승인한 실제 직원 결과물을 1번만 지식 문서로 등록하는 `company_handoffs.promote_approved` 추가. 직원 실행/원본 해시/승인 상태를 원자적으로 확인하고 출처·원본 결과물 ID 및 불변 공유 매핑 저장. 미승인·실패·변조 결과/기존 중복은 차단.
- 회사 운영센터 결과 화면에 수동 `승인 결과 회사 지식 등록` 버튼과 확인 팝업 추가. 자동 외부 발송/게시/결제 없음. 기존 결과물 승인 버튼은 보존.
- 기존 네이티브 테스트 파일과 함께 `test_company_handoffs.py`를 GitHub CI/Windows EXE 회귀에 포함. 새 커밋의 전체 CI·Windows GGUF 결과가 끝날 때까지 최종 완료 주장 금지.

### 18절 공유 장기 지식의 실제 직원 AI 재사용·감사 화면

- 앞서 소유자가 검수 승인하여 회사 지식 저장소에 직접 등록한 문서 중 현재 업무 제목과 유의미한 단어가 겹치는 문서만 후속 로컬 직원 모델의 업무 프롬프트에 450자 이내의 명시적으로 *신뢰할 수 없는 인용 참고 자료*로 포함. 미승인/미등록/보관처리 문서·원본 SHA256 변조는 제외하고 SQL 명령·거래·외부 프로그램 실행을 생성하지 않는다. 기존 직원 지시·감사 기록 및 모델 입력 최대 3000자 제한 유지.
- GUI 결과 화면에 소유자가 회사 지식 등록 기록을 조회하는 버튼 추가. 기억/원문 전체 복제 없이 결과물 ID와 지식 ID 연결 기록만 표시.
- 관련 회귀에 실제 직원 업무 컨텍스트로의 승인 지식 재사용, 관련 없는 지식 및 미등록 지식 미사용, 길이 제한·잘못된 자료 입력 차단 검증을 추가. Windows 2022/2025 GGUF E2E 최종 검증 전 완료 주장 금지.

### 18절 Windows EXE 공유 지식 모듈 포함 및 UI 실제 픽셀 가시성 검증

- 회사 운영센터에서 동적 import로 열리는 승인 지식 및 직원 간 공유 기능을 Windows 2022·2025 EXE, 실제 GGUF, GUI 검증 및 로컬 bat 빌드에 모두 명시적 PyInstaller hidden-import로 포함. 동일 기존 프로그램 재개발 아님.
- 실제 Tk GUI 스모크에서 신규 '승인 결과 회사 지식 등록'과 '회사 공유 지식 등록 기록' 버튼도 정상 그려졌고 창 픽셀 경계 안에 있는지 검사. 원래 소유자 '승인' 버튼 좌표/행은 그대로 유지. 검사 실패를 건너뛰지 않음.

### 18절 여러 기능 통합 검사 1건 실패·수정

- `3d49d618`의 CI #39379750687은 기존+신규 네이티브 테스트 **164 passed / 1 failed**. 실패는 `test_only_relevant_owner_promoted_knowledge_used_for_future_employee`에서 새 독립 업무의 담당 AI가 반드시 특정 직원 ID일 것이라고 고정한 테스트 가정으로 확인. 실제 자동 배정된 직원은 활성 직원이었고 모델 입력 지식 연결 전에 테스트가 실패함.
- 테스트가 특정 ID를 강요하지 않고 실제 자동 배정 정책이 선택한 활성 직원이 누구든 장기 지식 컨텍스트/감사/실행 3000자 제한이 성립하는지 확인하게 수정. 프로그램 배정 로직 변경 없음. 동일 수정본에서 기존 통합 CI/Windows EXE·실제 GGUF 회귀검사를 재실행해야 PASS 주장 가능.

## 19. 2026-10-20 사내 로컬 자율 업무 생성·반복 실행·오류 감사 묶음 개발

- 사내 자율 운영의 기존 수동 호출 한계를 해소하도록 `company_autopilot.py`와 실사용 Windows GUI 연결. 소유자가 명시적으로 켜면 해당 EXE 로그인 세션에서 30초 간격으로 DB에 영속 저장된 5분 주기를 확인, 원래 있는 규칙 기반 총괄 제안/반복 업무 일정/로컬 이벤트를 각각 최대 10건씩 실제 SQLite에 처리. **추론 자동 호출/유료 API/결제/외부 게시/소유자 승인 우회는 없음**.
- `aiwack_autopilot_settings`에 사용 여부·시간·다음 예정 시점 보관, `aiwack_autopilot_runs`에 각 주기마다 생성된 3종 결과 수·실행 상태·오류 종류 기록. 두 EXE 창의 동일 due 중복 실행은 BEGIN IMMEDIATE에서 1회만 선점. 프로그램 강제 종료로 중단된 건은 running 감사로 남기고 무단 재실행/성공 처리 안 함.
- 기존 `dispatch_local_events`를 BEGIN IMMEDIATE로 보호해 다중 창의 SELECT+업무 생성 중복 가능성을 수정. 비상정지/사용자 중지/로그아웃에서 새 처리 시작을 차단.
- Windows 기획 화면에 사내 자율 운영 켜기/끄기/실행 감사 버튼, 현재 상태 표기. 실제 Tk 버튼 가시성 검사에 새 버튼 추가. `test_company_autopilot.py`는 실제 SQLite 두 소유자 세션에서 미활성 기본, 목표 제안+일정+이벤트 생성, 경쟁 중복 차단, 비상정지, 로그아웃, 중단 감사, 잘못된 입력을 검사. 기존 전체 CI/Windows EXE 회귀에 포함.
- **이것은 Windows EXE가 실행 중인 동안의 사내 자동 계획/대기열 생성 기능**이며 PC/EXE 종료 중 독립 프로세스로 24시간 작동하거나 시장 판매·결제까지 수행한다는 주장 아님. 동일 SHA 전체 통합 검증 확인 전 최종 PASS 주장 금지.
