"""AIWACK 한국어 Windows Tk 관리자 실제 직원 간 모델 협업 탭."""
from __future__ import annotations
from tkinter import ttk


def attach(owner,tabs):
    tab=ttk.Frame(tabs)
    tabs.add(tab,text="실제 직원 AI 부서 간 협업")
    owner._field(tab,"peer_task_id","사전 검토 대상 todo 업무 번호")
    owner._field(tab,"peer_consultant_id","다른 부서 실제 GGUF 직원 번호")
    owner._field(tab,"peer_consultation_id","실제 협업 의견 번호")
    owner._field(tab,"peer_owner_note","관리자 실행·승인·반려 사유 (5~200자)")
    owner._buttons(tab,[
        ("다른 부서 직원 실제 GGUF 협업 검토 실행",lambda:owner._start_real_model_action(
            "서로 다른 부서 직원 실제 GGUF 협업 검토","peer_consultation",
            "선택 업무에 배정된 직원과 다른 부서에 있는 실제 로컬 GGUF 직원의 "
            "의견을 한 번 실행하여 SQLite에 보존합니다. "
            "모델 실행 기록/입력 변경/비상정지 여부를 확인하며 실패 후 "
            "같은 직원의 자동 재시도는 금지합니다. "
            "의견 승인·업무 실행·게시·거래는 이 버튼으로 진행되지 않습니다. 실행합니까?")),
        ("실제 GGUF 직원 협업 의견/호출 기록",lambda:owner._perform(
            "실제 타부서 직원 모델 호출/협업 감사",
            lambda:owner.store.peer_consultation_history(
                owner._id("peer_task_id"),50))),
    ])
    owner._buttons(tab,[
        ("검수한 동료 AI 의견 1건 승인·업무 인계",lambda:owner._perform(
            "동료 GGUF 의견의 업무 프롬프트 참고 승인",
            lambda:owner.store.decide_peer_consultation(
                owner._id("peer_consultation_id"),"approved",
                owner._get("peer_owner_note")),
            "실제 동료 GGUF 호출 성공/무결성/업무·직원 배정 변경이 없는 "
            "의견만 소유자 승인합니다. 해당 참고 의견을 기존 직원의 "
            "업무 실행 프롬프트에 비신뢰 근거로 포함하며 "
            "별도 업무 실행·돈 사용·게시·고객 연락은 하지 않습니다. 승인합니까?")),
        ("동료 AI 협업 의견 1건 반려",lambda:owner._perform(
            "실제 직원 협업 모델 의견 반려",
            lambda:owner.store.decide_peer_consultation(
                owner._id("peer_consultation_id"),"rejected",
                owner._get("peer_owner_note")),
            "의견 자체와 실제 호출·실패 기록을 삭제하지 않고 "
            "참고 자료 인계만 차단합니다. 반려합니까?")),
    ])
    ttk.Label(tab,text=(
        "실제 로컬 모델로 실행한 다른 부서 직원 의견만 원본 SHA256과 "
        "직원/모델 호출 감사로 추적합니다. 소유자가 개별 승인한 "
        "의견만 기존 직원 업무 입력에 450자 제한의 참고자료로 인계합니다. "
        "의견은 모델 지시·자동 승인·실제 매출 증빙이 아니며, "
        "기존 총괄 승인 지시/선행 협업 조건은 그대로 유지합니다."),
        wraplength=800).pack(anchor="w",padx=12,pady=10)
