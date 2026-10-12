# AIWACK — AI Autonomous Company

**Windows EXE 데스크톱 프로그램을 최종 사용자 실행 형태로 사용합니다.** 기존 웹 진단 서버는 개발/호환용 코드이며 **EXE를 실행할 때 웹사이트, 브라우저, FastAPI 서버, 인터넷 연결이 필요하지 않습니다.** 원본 기획서의 개발 목표는 유지하고, 사용자가 PC에서 직접 실행하는 화면을 Windows 데스크톱 앱으로 구현합니다.

> **현재 12/100단계 + 데스크톱 실행 기반 구현.** 초기 관리자 계정·로그인·접근 제한 및 로컬 데이터 저장/복구가 실제 동작하는 프로토타입입니다. **AI 총괄/직원, 사업 자동화, 수익 기능은 아직 개발되지 않았습니다.** 원본 기획서의 10단계 관리 화면 항목도 최종 완성된 것은 아닙니다.

## 1. Windows 사용자: AIWACK.exe 받기 (Python 설치 불필요)

1. [GitHub Actions](https://github.com/junggyeol4444/AIWACK/actions/workflows/windows-exe.yml) 페이지를 엽니다.
2. `Windows EXE build and real startup check`에서 **성공한 최신 main 실행**을 클릭합니다.
3. 아래 `Artifacts`에서 **AIWACK-Windows-EXE**를 내려받고 압축을 풉니다.
4. 압축 안의 **AIWACK.exe**를 더블클릭합니다. Windows 보호 경고가 나올 수 있습니다. 서명되지 않은 개발판이므로 파일 출처를 확인한 뒤 본인 판단으로 실행하세요.
5. 첫 실행 시 관리자 ID와 12자 이상의 비밀번호를 **본인 PC에서만** 지정한 다음 로그인합니다. 비밀번호를 잊으면 현재 버전에서는 복구 기능이 없으니 안전하게 보관하세요. 프로그램 창의 `로컬 저장 실사` 탭에서 테스트 메모를 저장한 후 프로그램을 종료·다시 실행하여 메모가 남는지 확인하세요.

GitHub Actions 실행 결과가 **성공**이고 해당 실행의 Artifacts에 EXE 파일이 존재하는지 확인하기 전에는 빌드가 끝났다고 보고하지 않습니다. 저장된 메모는 `%LOCALAPPDATA%\\AIWACK\\aiwack.sqlite3`에 들어가며 외부로 전송되지 않습니다. EXE를 삭제해도 메모 파일은 남습니다.

## 2. 개발 중인 소스를 직접 실행하기 (개발자용)

Python 3.11 이상이 준비되어 있다면 프로젝트 폴더에서:

```bash
python -m desktop.entry
```

소스 실행은 `start_windows.bat`(Windows), `sh start_mac_linux.sh`(macOS/Linux)로도 가능합니다. GUI는 Python 표준 라이브러리 Tkinter만 필요합니다. EXE 사용자는 Python이나 Git을 설치할 필요가 없습니다.

## 3. 검증 방법 — 실제 프로그램 실행과 코드 테스트를 구분

```bash
python -m pytest -q                          # 코드/스토리지 검증
python -m desktop.entry --self-test          # 실제 SQLite 파일에 기록·재열기 검사
xvfb-run -a python -m scripts.desktop_gui_smoke # Linux에서 실제 GUI 창 생성/버튼/닫기/재열기 검사
```

Windows EXE 자체는 GitHub의 **Windows runner**에서 PyInstaller로 빌드하고 빌드된 `AIWACK.exe --self-test`를 실행·확인합니다. Windows 사용자 화면의 실제 클릭·글꼴·보안 소프트웨어 검사는 사용자 PC 실사 검증이 필요합니다.

- [데스크톱 검증 내용](docs/DESKTOP_VERIFICATION.md)
- [원본 기획서](docs/original_project_spec.txt) · [100단계 계획](docs/roadmap_100.md) · [진행 기록](docs/WORK_LOG.md)
- [Windows EXE 빌드](.github/workflows/windows-exe.yml) · [GitHub 예약 개발](.github/workflows/hourly-development.yml)

## 4. 예약 개발

GitHub Actions가 한국시간 기준 **매시 30분**에 GitHub 서버에서 검증·다음 작업을 확인하도록 설정되어 있습니다. PC 전원과 무관합니다. **AI 자동 코드 작성은 사용자 승인하에 `OPENAI_API_KEY` GitHub Secret을 구성한 뒤에만 가능**하고, 없으면 검증만 실행합니다. ChatGPT 구독과 API 과금은 별개이며, 별도의 API 사용 비용이 생길 수 있습니다. 자동 생성 코드가 바로 main에 병합되지는 않습니다.

**다음 로드맵 단계: 13단계 — 직급·직무·역할 관리.**

**9단계 주의:** 로그인 비밀번호는 PBKDF2 해시로 저장되지만 SQLite 내용 자체는 암호화되지 않습니다. 계정 정보·비밀번호를 이 채팅이나 GitHub에 올리지 마세요. 이전 버전에서 저장한 메모는 삭제되지 않으며 최초 계정 생성 후 열람할 수 있습니다.

### 10단계: 관리자 센터

로그인 후 `관리자 센터` 탭에서 7개 관리 영역으로 이동할 수 있습니다. 로컬 DB 상태와 관리자 역할만 실제로 조회하며 조직/업무/사업/재무 등 후속 기능은 **미구현**으로 표시됩니다. GitHub CI의 실 GUI 검사와 Windows EXE 실행 검사가 모두 통과해야 완료로 취급합니다.

## 11단계 사용법

EXE 로그인 후 `회사·목표 관리` 탭에서 회사명/소개/운영 방향을 저장하고, 목표를 추가·선택·수정·삭제할 수 있습니다. 목표 삭제 시 확인 창이 뜹니다. 다른 사용자에게 외부 전송하지 않습니다.

## 12단계: 부서 관리

관리자로 로그인한 뒤 `부서 관리`에서 부서명과 설명을 추가·수정·삭제할 수 있습니다. 기존 사용자 데이터는 지워지지 않습니다. 중복 부서명은 거부되고 부서 삭제에는 확인이 필요합니다. AI 직원 연결은 이후 단계입니다.
