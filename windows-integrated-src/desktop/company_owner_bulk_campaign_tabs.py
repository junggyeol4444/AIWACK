"""AIWACK Windows Tk 소유자: 총괄 승인 15부서/30업무 일괄 등록.

Plan approval has already created the genuine chief orders, worker/model
assignments and task dependencies. One further explicit owner action registers
all steps, but never runs or accepts unreviewed GGUF outputs automatically.
"""
from __future__ import annotations

from tkinter import ttk


def attach(owner,tabs):
    frame=ttk.Frame(tabs)
    tabs.add(frame,text="15부서·30업무 전체 실행 등록")
    owner._field(frame,"bulk_plan_scope","기존 승인 계획 종류 wide 또는 department")
    owner._field(frame,"bulk_plan_id","관리자 승인된 전체 협업 계획 번호")
    owner._field(frame,"bulk_plan_note","계획 전체 실 GGUF 대기열 등록 사유 (5~200자)")
    owner._buttons(frame,[
        ("실제 15부서·30업무 전원 승인 근거 미리보기",lambda:owner._perform(
            "실제 총괄 GGUF 계획·직원 모델·업무 원본 30건 조회",
            lambda:owner.store.preview_bulk_campaign_queue(
                owner._get("bulk_plan_scope"),
                owner._id("bulk_plan_id")))),
        ("관리자 승인 계획 전체 영속 GGUF 업무 대기열 등록",lambda:owner._perform(
            "15부서·31AI 실제 승인된 업무 전체 1회 등록",
            lambda:owner.store.enqueue_bulk_campaign_queue(
                owner._get("bulk_plan_scope"),
                owner._id("bulk_plan_id"),
                owner._get("bulk_plan_note")),
            "선택한 기존 총괄/관리자 승인 계획의 실제 부서·직원/부서장 모델, "
            "30업무 또는 2~5부서 업무 지시, 의존성, 이전 GGUF 실행·실패·"
            "과거 등록 여부를 원자적으로 재확인합니다. 모두 적합하면 "
            "모든 원본 업무를 한 번에 대기열에 등록합니다. "
            "기존 Windows 자동/장기 실GGUF 동의가 있어야 실제 실행되며, "
            "선행 결과 관리자 최종 수락·업무 완료 전 후속 단계는 실행되지 "
            "않습니다. 모델 즉시 호출·최종 승인·거래·고객 발송은 하지 않습니다. "
            "전체 1회 등록을 명시 승인합니까?")),
    ])
    owner._buttons(frame,[
        ("실제 총괄 승인 계획 전체 대기열·모델/결과 상태",lambda:owner._perform(
            "기존 15부서 GGUF 30업무/2~5부서 승인 등록 실행 이력",
            lambda:owner.store.bulk_campaign_queue_history(30))),
        ("현재 등록 업무 실행 준비 및 선행 검수 대기",lambda:owner._perform(
            "실제 GGUF 직원 업무 실행/선행 승인 차단 원본",
            lambda:owner.store.company_approval_inbox(150))),
    ])
    ttk.Label(frame,wraplength=800,text=(
        "한 번의 명시적 관리자 등록은 기존에 생성·승인된 15부서 30역할/"
        "31AI 계획 또는 2~5부서 협업 계획만 대상으로 합니다. "
        "업무 실행은 기존 로컬 GGUF 엔진과 선행 단계 승인 게이트가 결정하고 "
        "직원 결과·부서장 의견·총괄 보고서를 자동 승인하지 않습니다. "
        "오류/모델 실패가 생기면 동일 계획을 다시 대기열에 등록하지 않습니다. "
        "어떤 외부 거래도 수행하지 않습니다."
    )).pack(anchor="w",padx=12,pady=12)
