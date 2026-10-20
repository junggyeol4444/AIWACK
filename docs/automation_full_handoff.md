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
