"""기존 Windows 한국어 Tkinter 관리자 화면에 실제 총괄 부서 업무 발견 탭."""

from __future__ import annotations
from tkinter import ttk


def attach(owner,tabs):
    panel=ttk.Frame(tabs)
    tabs.add(panel,text="총괄 GGUF 부서별 신규 업무")
    owner._field(panel,"chief_dept_proposal_id","총괄 실제 GGUF 신규 업무 제안 번호")
    owner._field(panel,"chief_dept_note","관리자 승인/반려 사유 (5~200자)")
    owner._field(panel,"chief_dept_filter","부서 번호 (비워두면 전체)")
    owner._field(panel,"chief_autodiscovery_run_id","중단된 자동 총괄 모델 회차 번호")
    owner._field(panel,"chief_autodiscovery_note","중단 회차 확인 사유 (5~200자)")
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
    owner._buttons(panel,[
        ("총괄 GGUF 60분 주기 업무 발견 별도 허용",lambda: owner._perform(
            "총괄 GGUF 자율 신규업무 발견 활성화",
            lambda:owner.store.configure_chief_autodiscovery(True,60),
            "기존 회사 자동 운영·실제 모델 실행 두 동의가 켜져 있을 때만 "
            "현재 로그인 GUI의 5분 자동 운영 중 최대 60분마다 실제 총괄 "
            "GGUF를 호출해 미승인 신규 업무 초안만 생성합니다. "
            "기존 승인 직원 업무가 있으면 우선 실행합니다. 허용합니까?")),
        ("총괄 GGUF 정기 업무 발견 해제",lambda: owner._perform(
            "총괄 자동 신규업무 발견 비활성화",
            lambda:owner.store.configure_chief_autodiscovery(False,60),
            "추가 GGUF 자동 호출을 차단하며 현재 실행 중인 호출에도 "
            "취소 신호를 전달합니다. 이전 감사와 초안은 보존합니다.")),
    ])
    owner._buttons(panel,[
        ("총괄 GGUF 자동 발견 상태",lambda: owner._perform(
            "총괄 정기 모델 발견 설정·미완료 이력",
            lambda:owner.store.chief_autodiscovery_status())),
        ("총괄 GGUF 정기 발견 실제 호출 기록",lambda: owner._perform(
            "총괄 주기별 실제 모델 호출/실패 감사",
            lambda:owner.store.chief_autodiscovery_history(50))),
        ("중단 모델 회차 관리자 직접 확인 종료",lambda: owner._perform(
            "실제 모델 종료 확인 후 중단 회차 감사 종결",
            lambda:owner.store.close_interrupted_chief_autodiscovery(
                owner._id("chief_autodiscovery_run_id"),
                owner._get("chief_autodiscovery_note")),
            "중단 모델의 실제 프로세스 종료를 직접 확인했습니까? "
            "기존 모델 호출·실패·초안은 보존하고 같은 호출을 "
            "자동 재실행하지 않은 채 감사 회차만 종료합니다.")),
    ])
    ttk.Label(panel,text=(
        "이 기능은 기존 총괄/직원 모델 설정을 임의로 바꾸지 않습니다. "
        "실제 로컬 모델 출력과 원본 호출 감사가 있는 경우에만 업무 제안을 저장하고 "
        "관리자 승인 이후 부서별 직원에게 실제 todo를 생성/배정합니다. "
        "직원 실행·도구 사용·최종 보고·실제 거래는 별도 기존 절차이며 "
        "이번 개발만으로 15부서/31AI/30업무의 장기 자율 운영을 완료한 것은 아닙니다."),
        wraplength=800).pack(anchor="w",padx=12,pady=10)
