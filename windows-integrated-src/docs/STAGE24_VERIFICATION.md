# 24단계 검증 — 로컬 업무 담당 AI 자동 지정

## 구현

- Windows 네이티브 Tkinter GUI의 `업무 자동 배정` 탭에서 업무 선택, 필요 부서/직무 지정, 조건 저장, 자동 배정, 해제 및 이력 조회
- 세 개의 로컬 SQLite 테이블로 기존 업무에 추가 정보 저장 (기존 데이터 보존)
- 활성 draft 프로필만 후보, CEO/부서장은 제외, 지정 조건 정확히 충족, 미완료 업무량 최저 우선, 직원 ID 동률 결정
- `todo` 상태 외 배정 금지, 미등록 직원·부서·직무/타 종류 ID 금지, 미배정 조건 실패는 명시적인 오류
- 세션 단위 소유자 권한 확인, 이벤트와 배정을 하나의 SQLite 트랜잭션에 저장
- 직원 비활성화/부서·직무 수정/관리자 계층 변경 시 자동 해제 이벤트
- 외부 서버/인터넷/AI 모델을 호출하지 않는 **업무 담당자 기록 기능**

## 실행할 수 있는 검사

```bash
python -m pytest -q
python -m desktop.entry --self-test
xvfb-run -a python -m scripts.desktop_gui_smoke
python -m scripts.verify_offline_runtime
python scripts/next_step.py
```

## 한계

- 화면 시험은 Linux Xvfb의 실제 Tk 창으로 수행. Windows EXE 빌드 및 사용자의 Windows PC에서 화면/보안 소프트웨어 검사는 수행하지 않음.
- 네트워크 소켓 차단 검사는 Python 경로의 회귀 검사이지 OS 수준 네트워크 격리가 아님.
- 업무를 실제 AI 직원이 실행하거나 결과를 평가하는 기능은 후속 단계. 로드맵 24/100과 실제 제품 완성도는 별개.
