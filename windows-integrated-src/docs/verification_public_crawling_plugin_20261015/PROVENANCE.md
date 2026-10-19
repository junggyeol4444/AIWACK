# 실제 외부 크롤링·플러그인 결과 확인 (2026-10-15)

- **실제 호출 성공**: 연결된 TinyFish `fetch_content` 플러그인으로 Python 문서의 다음 공개 HTTPS 두 페이지를 읽어 제목과 본문을 확인함.
  - https://docs.python.org/3/library/urllib.request.html (플러그인 본문 길이 약 56,784자)
  - https://docs.python.org/3/library/urllib.robotparser.html (플러그인 본문 길이 약 2,717자)
- ZIP 안의 `tinyfish_live_excerpts.json`은 크롤링 플러그인 결과의 **출처·제목과 소량의 요약 데이터만** 담은 개인정보 없는 예제이며, 웹 페이지 전문이나 플러그인 인증 정보가 아니다. 현재 ChatGPT 플러그인 세션의 결과를 독립 Windows EXE가 직접 호출한 것처럼 주장하지 않는다.
- Firecrawl `scrape`: 해당 계정 잔여 크레딧 부족으로 미실행. Tavily `crawl`: 계정 사용 한도(HTTP 432)로 거부됨. 동일 요청 무한 재시도 금지.
- **프로그램 실행 컨테이너에서 직접 `socket.getaddrinfo('docs.python.org',443)` 호출은 DNS 실패**. Python 직접 HTTPS 전송 코드는 구현되었으나, 이 실행 환경에서 실제 HTTPS 원격 요청 성공 검증은 하지 못함. Windows 사용자 PC에서 검증 필요.
- `desktop/public_site_crawler.py`는 자체 직접 수집 경로이며 관리자 클릭 시만 최대 6페이지·2단계 깊이·512KiB·동일 공개 HTTPS 호스트로 제한. 기초 GUI 기본 버튼은 3페이지·1단계 깊이.
- `import_web_plugin_export`은 플러그인의 **로컬 JSON 내보내기**를 확인한 후 관리자 권한으로 수집 자료 목록에 등록한다. JSON의 제공자 표시만으로 플러그인 원본을 인증하는 것은 아니며, 저장된 자료는 미검증으로 표시한다.
- GitHub 접속/조회/업로드/커밋/Actions 작업을 수행하지 않았음.
- 실제 판매·결제·개인 계정·대외 게시·실제 고객 데이터 처리·Windows/GGUF/장시간 운영은 검증되지 않음.
