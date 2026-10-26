"""AIWACK Windows 관리자: 부서간 선행 실제 GGUF 승인 인계 서명 원장."""
from __future__ import annotations
from tkinter import ttk


def attach(owner,tabs):
    frame=ttk.Frame(tabs)
    tabs.add(frame,text="부서간 GGUF 승인 인계")
    owner._field(frame,"handoff_target_task","선행 업무를 인계받을 후속 직원 업무 번호")
    owner._field(frame,"handoff_owner_note","부서간 AI 근거 관리자 인계 사유 (5~200자)")
    owner._buttons(frame,[
        ("부서간 직원·총괄 GGUF 실제 승인 근거 고정",lambda:owner._perform(
            "서로 다른 업무의 실GGUF·관리자 검수 원본 불변 인계",
            lambda:owner.store.seal_dependency_handoff(
                owner._id("handoff_target_task"),
                owner._get("handoff_owner_note")),
            "선행 업무 각각의 실제 직원 GGUF 성공, 총괄 GGUF 회수 성공, "
            "관리자 양쪽 결과 승인과 업무 완료, 내용 SHA256을 검사합니다. "
            "그 근거와 후속 직원 배정·모델·총괄 지시를 한 번만 불변 서명합니다. "
            "서명된 후 업무 실행 전 원본 변경이 발견되면 차단됩니다. "
            "모델을 호출·업무를 승인·완료하지 않습니다. 서명합니까?")),
        ("선행 GGUF 모델·후속 직원 인계 무결성 조회",lambda:owner._perform(
            "선행 부서 실제 모델 호출/관리자 승인/결과 SHA256 변경 검사",
            lambda:owner.store.inspect_dependency_handoff(
                owner._id("handoff_target_task"))),
    ])
    owner._buttons(frame,[
        ("부서간 실제 GGUF 인계 원본·승인 기록 전체",lambda:owner._perform(
            "실제 15부서 협업 근거 승인/실패 상태·업무별 인계 원장",
            lambda:owner.store.dependency_handoff_history(50))),
    ])
    ttk.Label(frame,wraplength=800,text=(
        "부서 간 선행 결과물이 done으로 표시된 것만으로는 충분하지 않습니다. "
        "실제 직원 모델 실행/결과 SHA·총괄 모델 검토/승인 및 후속 업무 배정을 "
        "다시 확인해 SQLite에 관리자 별도 인계 근거를 보존합니다. "
        "서명된 후속 업무만 새로운 모델 실행 시 이 인계 원장도 강제 확인합니다. "
        "기존 업무/승인 원본/모델을 변경하거나 외부 거래를 수행하지 않습니다."
    )).pack(anchor="w",padx=12,pady=12)
