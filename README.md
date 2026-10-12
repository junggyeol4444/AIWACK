# AIWACK — AI Autonomous Company

자율 운영형 AI 회사 시스템 개발 기획안에 따른 100단계 프로젝트입니다.

**구현·로컬 테스트 확인: 1~7 / 100단계. 다음은 8단계: 데이터베이스 변경 이력 관리.**
현재는 초기 FastAPI 서버, 연결 및 SQLite 개발용 DB 초기화까지만 구현됐습니다. 실제 자율 AI 회사 기능은 미구현입니다.

- [원본 기획서](docs/original_project_spec.txt)
- [100단계 로드맵](docs/roadmap_100.md)
- [개발 기록](docs/WORK_LOG.md)
- [GitHub 예약 개발 설명](docs/automation.md)

## GitHub Actions 예약 개발

`.github/workflows/hourly-development.yml`: 한국시간 기준 매시 30분 실행 (21:30, 22:30, 23:30, 00:30, 계속 반복). PC가 꺼져도 GitHub 쪽에서 테스트 및 다음 단계 확인 작업을 실행합니다.

새로운 코드를 AI가 자동 작성하려면 저장소 Secret `OPENAI_API_KEY` 등록이 필요합니다. **사용자 승인 없이 계정 생성/비용 발생/비밀키 입력을 하지 않습니다.** Secret이 없으면 테스트만 실행하며 개발한 것으로 기록하지 않습니다. AI 코드 생성은 일단 브랜치와 PR을 제출하고 main 자동 병합은 하지 않습니다.

## 로컬 개발 실행 (현재 사용자 PC에는 설치 안 함)

```bash
python -m pip install -e '.[dev]'
python -m pytest -q
python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
```
