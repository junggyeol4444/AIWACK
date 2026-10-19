# AIWACK Stage54 부분 개발 — 등록 자료 묶음 원본 파일 일괄 재검사

- 근거: 최신 누적본 `AIWACK_Stage54_Offline_Bundle_Context_Guard_Continuation_Source.zip`의 다섯 핵심 문서 실제 검토.
- 원본 단계 54 **인터넷 조사 및 자료 수집**은 외부 접속 금지로 **완료하지 않음**. 1~53 완료 / 54 진행 중, 전체 100단계 중 **53%** 유지.
- 기존 묶음 가져오기와 JSON 목록 생성/승인·SQLite 데이터·원본 기획안은 유지. 별도 독립 원본 기획안 텍스트 첨부는 이 실행에서 접근하지 못했고 최신 ZIP 내부의 원본 문서를 기준으로 진행함.

## 기능과 실제 변경

- `desktop/research_captures.py`: 로컬 JSON 목록 안전 읽기를 메타데이터와 파일 내용 검증으로 분리. 이전에 저장된 JSON 목록의 바이트 SHA-256으로 SQLite 묶음 이력을 찾고 현재 사용자가 선택한 폴더의 최대 20개 파일을 원본 해시·크기와 비교. 일치/변경/파일 부재·읽기 불가/등록 이력 불일치를 구분. 보관된 자료 포함.
- `desktop/storage.py`: 소유자 권한 필수 및 일관된 읽기 트랜잭션으로 검사 API 추가.
- `desktop/app.py`: Tkinter `등록 묶음 원본 파일 일괄 재검사` 버튼 및 결과·오류 표시.
- `tests/test_offline_research_bundle_custody.py`: 단위/통합/권한/오프라인 테스트.
- `scripts/stage54_bundle_custody_gui_smoke.py`: Linux Xvfb 실제 Tkinter UI에서 정상/변경/누락 확인.
- `scripts/verify_offline_runtime.py`: 기존 네트워크 차단 오프라인 실행 검사에 GUI 추가.
- 기존 DB 테이블 마이그레이션·신규 네트워크/클라우드 API·사용자 PC 접속 없음. 선택 경로 외의 파일 자동 탐색 없음.

## 검증

- 전체 pytest 단일 실행 **1,144개 통과 / 실패 0개, 140.60초** — `full_pytest.log`, `full_pytest.exit`. `sitecustomize.py`를 통한 Python 소켓·DNS 호출 차단 후 실행.
- 관련 테스트 **44개 통과** (신규 13개 포함) — `related_pytest.log`.
- Linux Xvfb 실제 Tkinter 화면에서 묶음 JSON 선택·원본 일치·내용 변경·파일 누락 확인 — `gui_smoke.log`.
- 소켓·DNS 호출 차단 상태에서 오프라인 실행 스크립트 **44개 명령 통과** — `offline_runtime.log`, `offline_runtime.exit`.
- Python 컴파일 검사 통과 — `compileall.log`.
- 기존 **615개 파일 경로 모두 보존**, 608개 바이트 단위 일치, 기존 코드/문서 7개 수정. 원본 기획안·추적표·CSV 로드맵·기존 SQLite SHA-256 일치 — `source_preservation.json`.
- 전체 ZIP 별도 폴더 재압축 해제 후 관련 pytest **44개 통과** 및 Linux Xvfb 실제 GUI 검사 통과 — `reextracted_related_pytest.log`, `reextracted_gui.log`.
- 누적 ZIP CRC 검사 통과, 기존 모든 파일 보존, 상세 SHA-256은 별도 검증 문서 참조.

## 제한

- 파일 해시 일치는 선택한 파일 바이트의 동일성만 증명. 웹 자료의 출처, 실제 저작자, 원래 파일 경로, 인터넷 사이트 존재, 원본 복제 방지, 인증/서명을 증명하지 않음.
- 선택 JSON 목록이 등록 당시와 한 바이트라도 달라지면 기존 묶음과 연결할 수 없어 검사 오류로 보고. 최초 가져오기 이후 원본 파일이 사라지면 검증 불가로 보고.
- Python 소켓·DNS 차단 검사는 운영체제 수준의 모든 네트워크 차단을 입증하지 않음.
- Windows 10/11 실제 기기·Windows EXE 빌드·실제 GGUF 모델·장시간 자율 운영은 검증하지 않음.
- 실질 제품 완성도 약 **20~25%**는 주관적 추정이며 53% 로드맵 단계 완료율 및 pytest 통과율과 별개임.
