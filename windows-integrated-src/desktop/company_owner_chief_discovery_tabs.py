"""기존 Windows 한국어 Tkinter 관리자 화면에 실제 총괄 부서 업무 발견 탭."""

from __future__ import annotations
from tkinter import ttk


def attach(owner,tabs):
    panel=ttk.Frame(tabs)
    tabs.add(panel,text="총괄 GGUF 부서별 신규 업무")
    owner._field(panel,"chief_dept_proposal_id","총괄 실제 GGUF 신규 업무 제안 번호")
    owner._field(panel,"chief_dept_note","관리자 승인/반려 사유 (5~200자)")
    owner._field(panel,"chief_dept_filter","부서 번호 (비워두면 전체)")
    owner._buttons(panel,[
        ("실제 회사 원본 기반 신규 업무 GGUF 생성",lambda: owner._start_real_model_action(
            "총괄 GGUF 부서별 실제 신규 업무 제안","department_discovery",
            "15부서/31AI의 기존 SQLite 회사 상태를 실제 로컬 총괄 GGUF에 "
            "전달해 부서별 내부 업무 초안 1~5개를 작성합니다. "
            "모델 호출은 실제 실행되며 동일 원본으로 자동 재호출하지 않습니다. "
            "각 업무·직원 배정은 관리자 개별 승인 전까지 생성되지 않습니다. 실행합니까?")),
        ("실제 모델 호출 근거/실패 이력",lambda: owner._perform(
            "총괄 실제 모델 신규 업무 호출/무결성 기록",
            lambda:owner.store.chief_department_discovery_attempts(30))),
    ])
    owner._buttons(panel,[
        ("실제 GGUF가 작성한 신규 업무 조회",lambda: owner._perform(
            "총괄 GGUF 신규 부서별 업무 초안",
            lambda:owner.store.chief_department_discovery_proposals(100))),
        ("부서별 신규 업무·배정 현황",lambda: owner._perform(
            "실제 총괄 제안/직원 배정 원장",
            lambda:owner.store.chief_department_handoffs(
                int(owner._get("chief_dept_filter"))
                if owner._get("chief_dept_filter").strip() else None,100))),
    ])
    owner._buttons(panel,[
        ("제안 1건 승인 후 직원 배정",lambda: owner._perform(
            "실제 총괄 신규 업무 관리자 개별 승인/부서 직원 지정",
            lambda:owner.store.decide_chief_department_proposal(
                owner._id("chief_dept_proposal_id"),"approved",
                owner._get("chief_dept_note")),
            "모델이 제시한 한 업무만 현재 부서·모델 연결 직원에게 실제 todo로 "
            "등록하고 SQLite에서 담당자를 배정합니다. 실제 직원 모델 실행, "
            "고객 전송, 거래, 원본 인사 변경은 하지 않습니다. 승인합니까?")),
        ("제안 1건 반려",lambda: owner._perform(
            "총괄 신규 부서 업무 개별 반려",
            lambda:owner.store.decide_chief_department_proposal(
                owner._id("chief_dept_proposal_id"),"rejected",
                owner._get("chief_dept_note")),
            "실제 모델 제안의 반려 원본 감사만 추가하며 이미 생성한 업무를 삭제하지 않습니다. 반려합니까?")),
    ])
    ttk.Label(panel,text=(
        "이 기능은 기존 총괄/직원 모델 설정을 임의로 바꾸지 않습니다. "
        "실제 로컬 모델 출력과 원본 호출 감사가 있는 경우에만 업무 제안을 저장하고 "
        "관리자 승인 이후 부서별 직원에게 실제 todo를 생성/배정합니다. "
        "직원 실행·도구 사용·최종 보고·실제 거래는 별도 기존 절차이며 "
        "이번 개발만으로 15부서/31AI/30업무의 장기 자율 운영을 완료한 것은 아닙니다."),
        wraplength=800).pack(anchor="w",padx=12,pady=10)
