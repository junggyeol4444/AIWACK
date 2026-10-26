"""AIWACK 네이티브 관리자: 실제 승인 제품 제작·총괄 조직 분석·전사 모델 회차."""
from __future__ import annotations

from tkinter import ttk


def attach(owner,tabs):
    panel=ttk.Frame(tabs)
    tabs.add(panel,text="실제 제품 제작·전사 운영")
    owner._field(panel,"real_product_artifact","승인된 직원 실모델 결과물 번호")
    owner._field(panel,"real_product_format","제품 파일 유형 python / markdown / text")
    owner._field(panel,"real_product_note","제품 제작 관리자 사유 (5~200자)")
    owner._buttons(panel,[
        ("실제 AI 결과 원문 로컬 제품 파일 제작",lambda:owner._perform(
            "최종 승인 직원 GGUF 코드/문서 실제 로컬 제작",
            lambda:owner.store.export_approved_real_product(
                owner._id("real_product_artifact"),
                owner._get("real_product_format"),
                owner._get("real_product_note")),
            "직원 실제 모델 성공·총괄 실제 모델 성공·직원 결과물 관리자 승인·"
            "총괄 보고서 관리자 수락을 다시 확인한 뒤 승인 원본 텍스트의 "
            "바이트 그대로 별도 로컬 .py/.md/.txt 파일을 제작합니다. "
            "코드 실행·배포·고객 발송·결제는 하지 않습니다. 제작합니까?")),
        ("로컬 AI 제품 제작·SHA256 검증 조회",lambda:owner._perform(
            "원본 직원/총괄 승인 실제품 제작 이력",
            lambda:owner.store.approved_real_product_history(40))),
    ])
    owner._field(panel,"real_release_title","실제 다중 파일 AI 배포 묶음 제목")
    owner._field(panel,"real_release_items","실제 승인 직원 결과물 목록: 101:python,102:markdown")
    owner._field(panel,"real_release_note","다중 파일 제작 관리자 사유 (5~200자)")
    owner._buttons(panel,[
        ("실제 직원 GGUF 원문 여러 개를 로컬 배포 패키지 제작",lambda:owner._perform(
            "실제 직원·총괄 이중 승인 소스 다중 파일 로컬 ZIP 제작",
            lambda:owner.store.create_actual_model_release(
                owner._get("real_release_title"),
                owner._get("real_release_items"),
                owner._get("real_release_note")),
            "실제 직원 GGUF·총괄 GGUF 성공 호출, 직원 결과물 관리자 승인, "
            "총괄 보고서 관리자 수락을 각 결과물마다 검사해 원문 텍스트를 "
            "로컬 ZIP의 .py/.md/.txt 여러 파일로 제작합니다. "
            "Python 코드는 AST 문법만 확인하며 실제 실행·고객 발송·"
            "프로그램 설치·판매·배포는 하지 않습니다. 제작합니까?")),
        ("로컬 실제 GGUF 다중 코드·문서 배포 목록 재조회",lambda:owner._perform(
            "실제 승인 GGUF 다중 파일 ZIP·SHA256 원본 감사",
            lambda:owner.store.actual_model_release_history(30))),
    ])
    owner._field(panel,"real_order_id","로컬 주문 번호")
    owner._field(panel,"real_order_release_id","실제 GGUF 다중 제품 번호")
    owner._field(panel,"real_order_packet_id","해당 주문의 승인 로컬 상품 준비 파일 번호")
    owner._field(panel,"real_order_note","주문별 AI 제품 전달 준비 사유 (5~200자)")
    owner._buttons(panel,[
        ("실제 GGUF 승인 다중 파일을 로컬 주문에 연결",lambda:owner._perform(
            "실제 로컬 주문·승인 상품·직원 GGUF 다중 ZIP 연결",
            lambda:owner.store.create_real_release_order_handoff(
                owner._id("real_order_id"),
                owner._id("real_order_release_id"),
                owner._id("real_order_packet_id"),
                owner._get("real_order_note")),
            "실제 승인된 주문의 상품 문서가 직원·총괄 GGUF 승인 다중 ZIP의 "
            "원본 직원 결과물에 포함되는지 확인합니다. 주문의 미취소·미환불 상태, "
            "준비 파일 SHA256, 직원·총괄 성공 및 최종 승인 증빙을 확인한 뒤 "
            "고객 개인정보가 없는 로컬 전달 준비 JSON을 기록합니다. "
            "고객 발송·결제/환불 실행·은행 확인은 하지 않습니다. 진행합니까?")),
        ("실제 GGUF 제품 주문별 연결·환불 변경 조회",lambda:owner._perform(
            "로컬 주문별 GGUF 상품 준비 SHA256 및 최신 취소/환불 상태",
            lambda:owner.store.real_release_order_handoff_history(50))),
    ])
    owner._field(panel,"real_staff_strategy_id","총괄 실제 GGUF 조직 판단 번호")
    owner._field(panel,"real_staff_note","총괄 조직 판단 관리자 검토 사유 (5~200자)")
    owner._buttons(panel,[
        ("실제 실패 근거 총괄 GGUF 조직 평가",lambda:owner._start_real_model_action(
            "총괄 실제 GGUF 직원 성과·조직 판단","chief_staff_strategy",
            "기존 SQLite에서 실제 실패·중단된 직원 업무 및 부서를 확인해 "
            "로컬 실제 총괄 GGUF를 한 번 호출합니다. 모델 변경·직원 이동 "
            "자동 실행 없음. 동일 원본의 재호출도 차단합니다. 진행합니까?")),
        ("총괄 GGUF 직원·조직 제안 기록",lambda:owner._perform(
            "실제 총괄 GGUF 인력 판단 이력",
            lambda:owner.store.chief_staff_strategy_history(30))),
    ])
    owner._buttons(panel,[
        ("실제 총괄 재배치 판단을 관리자 제안 전달",lambda:owner._perform(
            "실제 총괄 인사 제안을 기존 직원 이동 검토로 등록",
            lambda:owner.store.decide_chief_staff_strategy(
                owner._id("real_staff_strategy_id"),"propose",
                owner._get("real_staff_note")),
            "실제 총괄 모델 원본 호출·실제 실패 업무·부서를 확인하고 "
            "기존 인력 재배치 제안에만 등록합니다. **직원을 실제 이동시키지 "
            "않습니다.** 기존 직원 이동 승인은 별도 검토가 필요합니다. 진행합니까?")),
        ("총괄 인력 재배치 판단 관리자 반려",lambda:owner._perform(
            "총괄 GGUF 조직 전략 반려",
            lambda:owner.store.decide_chief_staff_strategy(
                owner._id("real_staff_strategy_id"),"reject",
                owner._get("real_staff_note")),
            "실제 모델 호출/원본 증거를 유지하며 제안만 반려합니다.")),
    ])
    owner._field(panel,"operating_round_staff","이번 회차 승인 GGUF 직원 업무 수 (1~30)")
    owner._field(panel,"operating_round_chief","이번 회차 부서장 승인 총괄 회수 수 (1~10)")
    owner._field(panel,"operating_round_note","전사 승인 GGUF 운영 사유 (5~200자)")
    owner._field(panel,"operating_round_id","중단된 전사 GGUF 운영 회차 번호")
    owner._buttons(panel,[
        ("승인된 전사 GGUF 직원·총괄 실제 연속 실행",lambda:owner._start_real_model_action(
            "전사 실제 GGUF 승인 업무 연속 운영","operating_round",
            "관리자 개별 승인된 기존 GGUF 직원 업무와 부서장 개별 전달 승인 "
            "완료된 총괄 회수 업무를 순서대로 모델에서 실제 실행합니다. "
            "미승인 업무와 결과물 최종 승인·모델 실패 자동 재시도·"
            "외부 거래는 실행하지 않습니다. 진행합니까?")),
        ("전사 실행 가능 원본·승인 대기 조회",lambda:owner._perform(
            "전사 실제 GGUF 승인 운영 준비 현황",
            lambda:owner.store.preview_operating_round())),
    ])
    owner._buttons(panel,[
        ("전사 실제 GGUF 운영 회차 이력",lambda:owner._perform(
            "SQLite 실제 GGUF 전사 실행 이력",
            lambda:owner.store.operating_round_history(30))),
        ("주문·환불·상품·고객지원 연계 조회",lambda:owner._perform(
            "실제 승인 주문·상품 준비·환불·고객 원본 증빙",
            lambda:owner.store.local_order_finance_snapshot())),
    ])
    owner._buttons(panel,[
        ("중단 전사 운영 관리자 확인 종료",lambda:owner._perform(
            "중단 GGUF 회차 모델 종료 확인 감사",
            lambda:owner.store.close_operating_round_after_inspection(
                owner._id("operating_round_id"),
                owner._get("operating_round_note")),
            "실제 GGUF 프로세스 및 미종료 잠금이 없음을 직접 확인했습니까? "
            "기존 업무·결제·고객 전송·모델 호출 재실행 없이 "
            "중단 회차 기록만 종료합니다.")),
    ])
    owner._field(panel,"native_round_kind","원본 회차 종류 operating 또는 chief")
    owner._field(panel,"native_round_run_id","중단된 원본 GGUF 회차 번호")
    owner._field(panel,"native_round_interruption_id","Windows 커널 종료 관측 감사 번호")
    owner._field(panel,"native_round_note","관리자 중단 확인 사유 (5~200자)")
    owner._buttons(panel,[
        ("Windows PID·생성시각 기반 미종료 모델 회차",lambda:owner._perform(
            "실제 Windows 커널과 영속 SQLite 운영 회차 비교",
            lambda:owner.store.inspect_native_round_owners())),
        ("실제 Windows 원 GUI 프로세스 종료 증빙 기록",lambda:owner._perform(
            "원본 Windows PID/생성시각 종료 확인 감사",
            lambda:owner.store.record_dead_native_round(
                owner._get("native_round_kind"),
                owner._id("native_round_run_id")),
            "실제 Windows 원 GUI 프로세스 PID와 생성시각을 재확인합니다. "
            "원래 프로세스가 종료된 경우에만 불변 감사에 남기며 "
            "원본 GGUF 자식 프로세스는 자동 종료·재호출하지 않습니다. 기록합니까?")),
    ])
    owner._buttons(panel,[
        ("Windows 중단 GGUF 회차 최종 관리자 확인 종료",lambda:owner._perform(
            "실제 Windows 종료 관측 및 모델 잔여 잠금 확인",
            lambda:owner.store.close_native_round_after_inspection(
                owner._id("native_round_interruption_id"),
                owner._get("native_round_note")),
            "원래 GUI 프로세스가 실제 종료됐고 모델 자식 프로세스·외부 거래와 "
            "기존 미종료 회차 잠금까지 직접 확인했습니까? 기존 모델 재실행·"
            "원본 삭제 없이 최상위 회차 상태만 종료합니다.")),
        ("Windows 원 GUI 중단·관리자 확인 기록",lambda:owner._perform(
            "Windows 커널 기반 종료 프로세스와 원본 회차 감사",
            lambda:owner.store.inspect_native_round_owners())),
    ])
    ttk.Label(panel,wraplength=800,text=(
        "로컬 실제품은 실제 승인된 AI 출력에서만 생성하며 품질/실행 합격을 "
        "의미하지 않습니다. 조직 전략은 실제 실패·모델 감사만 사용하고 "
        "승인 전 직원/모델은 변경되지 않습니다. 전사 모델 연속 실행은 "
        "관리자 승인 원본만 대상으로 하며, 직원 결과물·부서장 의견·"
        "총괄 보고서 최종 검수는 별개입니다. 주문·결제·환불·"
        "은행 CSV 대사도 외부 공급자 독립 확인으로 주장하지 않습니다."
    )).pack(anchor="w",padx=12,pady=12)
