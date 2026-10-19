# AIWACK 공개 자료 크롤러·플러그인 결과 가져오기 사용 안내

1. Windows에서 AIWACK GUI를 열고 소유자 계정으로 로그인합니다. 54단계 연구 자료 화면의 `출처 URL`과 `허용 호스트`에 예를 들어 `https://docs.python.org/3/library/urllib.request.html` 및 `docs.python.org`를 입력합니다.
2. 해당 사이트의 robots.txt, 이용약관, 접근 권한을 확인합니다. `이번 공개 HTTPS GET 허용` 체크를 선택하고 `같은 호스트 크롤링`을 누릅니다. 버튼 기본값은 최대 3쪽·링크 깊이 1이며 공개 HTTPS GET만 수행합니다. 로그인·게시·결제 및 GitHub 접속은 하지 않습니다.
3. 소유자가 이미 TinyFish/Firecrawl/Tavily 등의 외부 크롤링 플러그인으로 가져온 **결과를 JSON으로 내보낸 파일**이 있다면 `크롤링 플러그인 JSON 가져오기`를 사용합니다. 입력 JSON은 `{"provider":"tinyfish","results":[{"url":"https://...","title":"...","text":"..."}]}` 형식이며 Firecrawl `markdown`, Tavily `raw_content`도 받아들입니다.
4. 해당 JSON 파일의 `provider`는 **표시 문자열만** 의미합니다. 독립적인 제공자 서명 확인이나 실제 API 인증이 아닙니다. 플러그인은 ChatGPT 연결 세션에서 호출 가능하며 Windows EXE에 자동 내장되는 것이 아닙니다.
5. 수집 자료는 출처 URL·원문 바이트 SHA-256·관리자 기록과 함께 SQLite에 저장하고, 중복 수집 시 동일 원문은 재사용합니다. 본문 색인 최대 59,000자이며 큰 HTML은 일부만 색인합니다. 수집 사실은 출처 내용의 사실 검증이 아닙니다.
6. 스크립트 실행: `python -m pytest -q -p no:cacheprovider tests/test_public_site_crawler.py tests/test_public_web_research.py`, GUI 검사(Linux): `xvfb-run -a python scripts/public_crawling_plugin_gui_smoke.py`.

**확인해야 할 항목**: Windows 10/11 실제 HTTPS 크롤링 네트워크·TLS·방화벽, 웹사이트 이용 조건 및 robots 규칙, 플러그인 계정 권한과 요금, 원본 T01~T20 및 모든 DB/업무 통합 회귀, 실거래·고객·GGUF·장시간 운영. 제품 완성도 100%를 주장하지 않습니다.
