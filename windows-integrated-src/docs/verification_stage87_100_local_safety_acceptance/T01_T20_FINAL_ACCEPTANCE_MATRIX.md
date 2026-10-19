# 원본 기획안 T01~T20 최종 인수 상태 (실패/미검증 분리)

본 문서는 원본 `docs/original_project_spec.txt`의 시험 항목을 직접 읽어 작성함.
로컬 부분 기능을 T01~T20 전체 시험 통과로 간주하지 않음. **전 항목 최종 승인 보류**.

| 항목 | 원본 검증 내용 | 원본 성공 기준 | 현재 확인 범위 및 남은 미검증 | 최종 인수 |
|---|---|---|---|---|
| T01 | AGI 없이 실행 | AGI 관련 서비스 없이 서버 정상 실행 | Python/Tkinter/SQLite local test only; full server flow not verified | 미검증 |
| T02 | 총괄 AI 운영 | 회사 현황을 읽고 업무를 생성 | read-only local diagnostics and improvement drafts; no real AGI/AI decision | 미검증 |
| T03 | 직원 AI 생성 | 직무·권한을 가진 새 직원 등록 | local employee drafts stored; model/permissions runtime unverified | 미검증 |
| T04 | 자율 업무 | 추가 사용자 입력 없이 업무 시작 | scheduler and event queues exist; autonomous multi-cycle operation unverified | 미검증 |
| T05 | AI 협업 | 여러 AI가 같은 프로젝트 수행 | chat/meeting records exist; real multi-agent collaboration unverified | 미검증 |
| T06 | 도구 사용 | 실제 외부 도구 실행 및 결과 저장 | existing local tool adapters; no approved external real execution | 미검증 |
| T07 | 장기 기억 | 서버 재시작 후 기록 복원 | SQLite fresh-object restart and backup tests, not full persistent knowledge validation | 미검증 |
| T08 | 병렬 실행 | 독립 업무 동시 처리 | small 2-thread reads only; model execution concurrency and Stage63 timing unresolved | 미검증 |
| T09 | 사업 생성 | 신규 사업 후보부터 프로젝트 생성까지 수행 | local business proposals/catalog; no real business creation/effectiveness | 미검증 |
| T10 | 상품 제작 | 사용할 수 있는 실제 결과물 생성 | earlier local product prototype; usability and actual product quality unverified | 미검증 |
| T11 | 판매 연동 | 테스트 결제 및 주문 처리 | mock order/fixture only; no payment/test provider transactions | 미검증 |
| T12 | 실제 거래 | 검증된 거래를 매출 기록에 반영 | mock amounts only; no validated transaction in real revenue | 미검증 |
| T13 | 재무 관리 | 실제 거래와 비용을 구분하여 계산 | KRW-only hypothetical budget; verified finance/accounting unverified | 미검증 |
| T14 | 자동 평가 | 결과 분석 및 후속 업무 생성 | local descriptive diagnostic and no-execute improvement draft | 미검증 |
| T15 | 조직 개편 | 직원 추가·이동·작업 재배정 | local staff reassignment drafts; not applied to real agent workforce | 미검증 |
| T16 | 권한 통제 | 미승인 고위험 작업 실행 차단 | owner permission, local stop, review-only spend tests; all risks not verified | 미검증 |
| T17 | 장애 복구 | 중단된 작업의 상태 복원 | reopen and backup-copy tests; full crash/side effect recovery unverified | 미검증 |
| T18 | 반복 실행 | 자율 운영 사이클 지속 | long autonomous cycle not run | 미검증 |
| T19 | 회사 관리 | 관리 화면에서 전체 상태 확인 | local owner GUI / Linux Xvfb only; Windows GUI unverified | 미검증 |
| T20 | 비상 정지 | 관리자 명령으로 외부 작업 차단 | local queue/scheduler/event gate; no provider-wide external kill switch verified | 미검증 |

## 판단
- 개발 순번 100에 도달한 사실은 제품 100% 완성을 뜻하지 않음.
- 완전 완료로 기록된 단계: 54/100, 그 외 54,56~100은 부분 구현 또는 보류.
- 기술적으로 불가능과 아직 실행하지 않은 외부 연결/실기기 검증을 구분. 인터넷 계정 사용 금지 때문에 해당 검증은 이번 실행에서 수행하지 않았음.
- Windows 실기기/EXE, 진짜 GGUF 모델, 실서비스 계정/결제/판매/환불, 실제 AI 자율 운영, 장시간 안정화는 미검증.
- 기존 Stage63 subprocess 병렬 타이밍 임계 문제는 미해결.
- 정해지지 않은 Stage101 생성 금지. 이후에는 보류 중인 테스트/통합/실사용 승인 항목을 보완.
