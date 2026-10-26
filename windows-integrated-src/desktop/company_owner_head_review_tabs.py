"""Windows 한국어 관리 GUI: 실제 부서장 GGUF 직원 결과 검토/관리자 인계."""

from __future__ import annotations
from tkinter import ttk


def attach(owner,tabs):
    frame=ttk.Frame(tabs)
    tabs.add(frame,text="실제 부서장 AI 개별 검토")
    owner._field(frame,"manager_review_artifact","실제 직원 결과물 번호")
    owner._field(frame,"manager_review_id","부서장 GGUF 검토 번호")
    owner._field(frame,"manager_owner_note","관리자 부서장 검토 판단 사유 (5~200자)")
    owner._field(frame,"head_to_chief_limit","실제 총괄 회수 최대 업무 수 (1~10)")
    owner._field(frame,"head_to_chief_note","총괄 실제 GGUF 회수 관리자 사유 (5~200자)")
    owner._field(frame,"head_to_chief_batch_id","중단된 총괄 회수 회차 번호")
    owner._buttons(frame,[
        ("직원 결과물 부서장 실제 GGUF 검토",lambda:owner._start_real_model_action(
            "실제 부서장 GGUF 직원 결과물 검토","manager_review",
            "실제 총괄 GGUF가 자발적으로 발견하고 관리자가 승인한 부서 업무의 "
            "성공한 직원 결과물에 대해 지정된 부서장 GGUF를 실제로 호출합니다. "
            "결과물과 부서장 모델 및 실행 기록 원본은 그대로 보존합니다. "
            "검토 의견은 관리자 개별 전달 승인 전까지 총괄에게 넘기지 않습니다. "
            "같은 결과물의 모델 호출 실패를 자동 재시도하지 않습니다. 실행합니까?")),
        ("실제 부서장 모델 호출/실패/승인 조회",lambda:owner._perform(
            "실제 부서장 AI 모델 검토 원장",
            lambda:owner.store.department_head_review_history(50))),
    ])
    owner._buttons(frame,[
        ("부서장 적합 의견 관리자 개별 전달 승인",lambda:owner._perform(
            "실제 부서장 GGUF 수락 의견을 총괄 검토로 전달 승인",
            lambda:owner.store.decide_department_head_review(
                owner._id("manager_review_id"),"forward",
                owner._get("manager_owner_note")),
            "실제 부서장 모델이 accept로 판단했고 저장 결과물 및 모델 호출 기록이 "
            "그대로인 경우에만 총괄 회수 단계로 진행할 수 있습니다. "
            "이 버튼은 총괄 호출·직원 결과물 승인·업무 완료를 수행하지 않습니다. "
            "전달을 개별 승인합니까?")),
        ("부서장 의견 검토 뒤 재작업 요청",lambda:owner._perform(
            "실제 부서장 GGUF 검토 재작업 회신",
            lambda:owner.store.decide_department_head_review(
                owner._id("manager_review_id"),"return",
                owner._get("manager_owner_note")),
            "부서장 검토 의견을 재작업 요청으로 기록합니다. "
            "원본 직원 모델 실행·업무 결과물은 보존하고 자동 재호출하지 않습니다. "
            "진행합니까?")),
    ])
    owner._buttons(frame,[
        ("승인 부서장 업무 실제 총괄 GGUF 연속 회수",lambda:owner._start_real_model_action(
            "실제 총괄 GGUF 부서장 승인 결과 회수","head_to_chief_batch",
            "다른 부서에서 이미 실제 직원·부서장 모델 검토가 완료되고 "
            "관리자가 개별 전달 승인한 결과물만 최대 10건까지 실제 총괄 "
            "GGUF로 회수합니다. 자동 최종 승인·모델 실패 재호출·거래·게시·"
            "환불은 하지 않습니다. 실제로 진행합니까?")),
        ("총괄 모델 회수 준비 업무 원본 조회",lambda:owner._perform(
            "부서장 승인 완료된 총괄 GGUF 회수 후보",
            lambda:owner.store.preview_head_chief_handoffs(30))),
    ])
    owner._buttons(frame,[
        ("실제 총괄 모델 회수 이력",lambda:owner._perform(
            "부서장 → 총괄 GGUF 실제 호출 원장",
            lambda:owner.store.head_chief_handoff_history(30))),
        ("전사 실제 직원·부서장·총괄 원본 현황",lambda:owner._perform(
            "실제 부서별 직원·부서장·총괄 증빙 현황",
            lambda:owner.store.head_chief_department_coverage(100))),
    ])
    owner._buttons(frame,[
        ("중단 회차 실제 프로세스 관리자 확인",lambda:owner._perform(
            "중단된 총괄 회수 원장 안전 종결",
            lambda:owner.store.close_head_chief_handoff_after_inspection(
                owner._id("head_to_chief_batch_id"),
                owner._get("head_to_chief_note")),
            "기존 GGUF 모델 프로세스가 종료됐음을 직접 확인했습니까? "
            "이 버튼은 이전 모델 호출이나 결과물을 재실행·삭제하지 않습니다.")),
    ])
    ttk.Label(frame,wraplength=800,text=(
        "총괄이 제안한 실제 신규 부서 업무에 대해 직원 AI → 부서장 AI "
        "(실제 GGUF 호출 기록) → 관리자 개별 인계 승인 → 총괄 AI 검토 → "
        "관리자 최종 검수를 분리합니다. 원본 30업무 프로그램/기존 보고 경로를 "
        "삭제하거나 외부 계정·실거래를 자동 실행하지 않습니다."
    )).pack(anchor="w",padx=12,pady=12)
