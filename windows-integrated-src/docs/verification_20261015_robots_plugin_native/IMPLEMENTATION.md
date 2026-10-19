# AIWACK 100단계 후속 보완 — robots.txt 크롤링 + 플러그인 결과 연동

## 실제 코드 변경
- `desktop/public_site_crawler.py`: 일반 단일 호스트 크롤러 보존 및 `crawl_site_with_robots` 새 경로 추가.
- 새 경로는 공개 HTTPS /robots.txt 읽기를 먼저 진행한다. 응답 없거나 해석 불가, 금지 경로면 자동 수집을 거부한다.
- 동일 호스트·공개 IP DNS 제한·SNI TLS 검증·비인증/비로그인 GET 제한·페이지/크기/깊이 제한 유지.
- robots.txt Crawl-delay를 따르고(최소 0.5초, 15초 초과 정책은 수집 거부) URL별 수집 직전에 확인한다.
- `public_site_crawl_runs`에 robots.txt 원문 바이트 SHA-256 및 정책으로 제외한 URL 건수 보존. 기존 DB 컬럼은 데이터 삭제 없이 추가된다.
- `desktop/storage.py`: 관리자용 `crawl_public_site_robots_checked` 기능 추가. 실제 GUI 버튼은 이 경로로 변경.
- TinyFish/Tavily/Firecrawl의 통상적인 JSON 도구 결과를 `{"provider":"...","tool_result":{...}}` 형식으로 전달하면 별도 원문 필드 재가공 없이 파싱 가능. 외부 서비스 계정이나 플러그인의 진위에 대한 확인이 아님.
- 로컬 자료 → Stage62 사업 후보 → Stage63 시장 근거 연결·관리자 검토의 실제 SQLite 데이터 경로 통합 테스트.

## 재현과 미검증 범위
- 단위 pytest는 DNS/TLS 전송을 모의한다. 이는 직접 Windows HTTPS 연결 시험이 아니다.
- 실제 ChatGPT TinyFish 연결 도구를 통해 공개 Python 문서 2쪽을 읽은 점은 본 대화에서 실제로 확인했다.
- Firecrawl은 잔여 크레딧 부족, Tavily는 요금제 한도로 이번 대화 요청이 거부되었다.
- 현재 실행 컨테이너의 docs.python.org 직접 DNS 조회는 실패하였다. 사용자 Windows PC에서 프로그램 직접 연결을 검증해야 한다.
- 외부 사이트 robots.txt 준수는 접근허가·재배포 허락·정보 정확성 보증을 의미하지 않는다.
- GitHub 및 실제 계정 거래·게시·결제·사용자 PC 접근은 시도하지 않았다.
- 제품 T01~T20 전체 인수, 전체 프로젝트 단일 pytest, 장시간 운영, GGUF 실추론, Windows GUI는 아직 검증하지 않았다.
