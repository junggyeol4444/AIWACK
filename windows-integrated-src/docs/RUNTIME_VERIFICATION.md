# 로컬 실구동 검증 기록

이 문서는 자동 단위 테스트 통과를 **실제 실행 성공**과 구분하기 위해 기록합니다.

## 확인 범위

- 실제 Uvicorn 서버 프로세스 실행 (`127.0.0.1`, 임의 포트)
- HTTP `GET /api/v1/health` 정상 응답
- HTTP `GET /docs`의 OpenAPI UI 제공
- HTTP `GET /diagnostics` 로컬 진단 HTML 제공
- Alembic 마이그레이션 `0001_initial` 적용
- 실제 HTTP POST로 진단 메시지 DB 저장
- 서버 종료 후 새로운 프로세스로 재시작
- 같은 물리 SQLite DB 파일에서 이전 메시지 HTTP GET 재확인
- 서버 프로세스 종료와 임시 테스트 DB 삭제

## 실행한 명령

```bash
python -m pytest -q
python scripts/real_smoke_test.py
```

**추가 브라우저 클릭 검증:** Chromium/Playwright로 로컬 화면을 열려 했으나 실행 환경 정책에서 `net::ERR_BLOCKED_BY_ADMINISTRATOR`가 반환되어 **미검증**입니다. HTML/JS 정적 구문 검사(`node --check`)는 통과했습니다. 사용자 PC에서 직접 화면과 저장 버튼을 확인해야 합니다.

## 제한 사항

- 사용자 개인 PC에서는 실행하지 않았습니다. 사용자가 직접 Windows/macOS/Linux에서 확인해야 합니다.
- PostgreSQL DB와 외부 모델 API는 구동 검증 대상이 아닙니다.
- 총괄 AI/직원 AI/실제 회사 운영의 기능은 미구현이므로 통합 작동 성공을 주장할 수 없습니다.
- 원격 공개, 금전 결제, 계정 인증 등은 구현하지 않았습니다.
