"""Existing Korean Tk owner window extensions for real SQLite recovery/staff audits.

Attaches tabs to the original notebook. Every state change is a separate
confirmed owner action. No GGUF, payment, network or external tool execution.
"""
from __future__ import annotations

from tkinter import ttk


def attach(owner, tabs):
    queue = ttk.Frame(tabs)
    tabs.add(queue, text="관리자 승인 GGUF 영속 대기열")
    owner._field(queue, "owner_queue_task", "기존 승인된 업무 번호")
    owner._field(queue, "owner_campaign_queue_id", "기존 승인된 15부서·30업무 계획 번호")
    owner._field(queue, "owner_queue_id", "대기열 항목 번호")
    owner._field(queue, "owner_queue_note", "관리자 사유 (5~200자)")
    owner._field(queue, "owner_model_run_id", "Windows 종료 모델 실행 번호")
    owner._buttons(queue, [
        ("승인 업무를 영속 대기열에 등록", lambda: owner._perform(
            "기존 총괄 지시 승인 업무 등록",
            lambda: owner.store.enqueue_owner_model_task(
                owner._id("owner_queue_task"), owner._get("owner_queue_note")),
            "기존 총괄 지시 승인·직원 모델 연결을 다시 확인합니다. "
            "별도 자동 운영/모델 정책이 켜진 경우에만 실제 GGUF를 한 번 실행하며 "
            "실패 자동 재시도·결과 자동 승인·외부 전송은 없습니다. 등록합니까?")),
        ("대기 중인 항목 취소", lambda: owner._perform(
            "실행 전 대기열 취소",
            lambda: owner.store.cancel_owner_model_queue(
                owner._id("owner_queue_id"),owner._get("owner_queue_note")),
            "실행 중인 모델은 이 버튼으로 취소하지 않습니다. 대기 항목만 취소합니까?")),
    ])
    owner._buttons(queue, [
        ("실제 대기열·실행 상태 조회", lambda: owner._perform(
            "GGUF 영속 대기열",lambda: owner.store.list_owner_model_queue(50))),
        ("대기열 선행 업무·인계 준비 상태", lambda: owner._perform(
            "실제 GGUF 대기열 준비 상태",lambda: owner.store.inspect_owner_model_queue(100))),
        ("Windows 종료 확인 모델 감사", lambda: owner._perform(
            "GUI 소유 프로세스 종료 기록",lambda: owner.store.native_model_exit_history(50))),
        ("하위 모델 확인 후 실패 잠금 해제", lambda: owner._perform(
            "모델 종료 감사의 잠금 관리자 해제",
            lambda: owner.store.release_owner_confirmed_model_lease(
                owner._id("owner_model_run_id"),owner._get("owner_queue_note")),
            "기존 Windows GUI 소유 프로세스가 종료됐음을 확인한 기록만 대상입니다. "
            "하위 GGUF 실행 프로세스도 관리자가 직접 확인했고 종료됐습니까? "
            "이 버튼은 잠금만 해제하며 해당 업무의 자동 재실행은 영구 차단됩니다. 진행합니까?")),
    ])
    owner._buttons(queue, [
        ("30업무 다음 단계·실원본 확인", lambda: owner._perform(
            "15부서 30업무 다음 승인 단계", lambda: owner.store.preview_campaign_model_queue(
                owner._id("owner_campaign_queue_id")))),
        ("30업무 다음 1건 영속 대기열 등록", lambda: owner._perform(
            "15부서 30업무 개별 승인 등록", lambda: owner.store.enqueue_campaign_model_step(
                owner._id("owner_campaign_queue_id"), owner._get("owner_queue_note")),
            "기존 실제 총괄 GGUF 원본과 앞 단계 관리자 검수 완료가 확인된 "
            "다음 한 업무만 등록합니다. 실제 모델 실행은 별도 정책/대기열 "
            "주기에 따르며 결과 자동 승인·실패 재시도는 없습니다. 등록합니까?")),
    ])
    ttk.Label(queue, text=(
        "기존 자율운영 + 실제 모델 실행 별도 동의가 모두 있어야 실행됩니다. "
        "소유자 Windows GUI가 살아있는 동안 기존 5분 tick당 최대 1건 실행합니다. "
        "Windows GUI 종료가 확인돼도 모델 하위 프로세스 생존은 미확정이므로 "
        "잠금은 유지하고 자동 재호출하지 않습니다. 24시간 검증 결과가 아닙니다."),
        wraplength=800).pack(anchor="w",padx=12,pady=10)
    recovery = ttk.Frame(tabs)
    tabs.add(recovery, text="중단 복구 후속 업무")
    owner._field(recovery, "recovery_audit_id", "기존 중단 확인 감사 번호")
    owner._field(recovery, "recovery_work_id", "복구 후속 제안 번호")
    owner._field(recovery, "recovery_work_note", "관리자 사유 (5~200자)")
    owner._buttons(recovery, [
        ("기존 소유자 확인 감사 조회", lambda: owner._perform(
            "중단 실행 직접 확인 후속 후보",
            lambda: owner.store.eligible_recovery_work_orders(50))),
        ("기존 중단 감사로 후속 제안", lambda: owner._perform(
            "중단 복구 후속 업무 제안",
            lambda: owner.store.capture_recovery_work_order(
                owner._id("recovery_audit_id"),
                owner._get("recovery_work_note")),
            "소유자가 직접 중단 판정한 감사만 연결합니다. "
            "실제 프로세스 종료를 독립 확인하거나 자동 재실행하지 않습니다. 진행합니까?")),
    ])
    owner._buttons(recovery, [
        ("복구 전 확인 업무 승인", lambda: _decide_recovery(owner, "followup_task")),
        ("복구 후속 제안 반려", lambda: _decide_recovery(owner, "rejected")),
        ("중단 후속 감사 이력", lambda: owner._perform(
            "중단 복구 후속 감사",
            lambda: owner.store.recovery_work_order_history(50))),
    ])
    ttk.Label(recovery, text=(
        "기존 실행/결제/고객 전송을 재생하지 않습니다. 승인 시 기존 회사 업무 "
        "목록에 중단 후 확인 업무만 추가하며 재실행은 별도 검토 대상입니다. "
        "24시간 연속 실행이나 자동 장애 복구 합격을 뜻하지 않습니다."),
        wraplength=800).pack(anchor="w", padx=12, pady=10)

    employee = ttk.Frame(tabs)
    tabs.add(employee, text="직원 실적 근거·관리자 평가")
    owner._field(employee, "evidence_employee_id", "기존 직원 AI 번호")
    owner._field(employee, "evidence_review_id", "직원 근거 평가 번호")
    owner._field(employee, "evidence_review_note", "관리자 사유 (5~200자)")
    owner._buttons(employee, [
        ("직원 실제 실행 근거 조회", lambda: owner._perform(
            "실제 직원 실행/모델 감사",
            lambda: owner.store.employee_evidence_snapshot(
                owner._id("evidence_employee_id")))),
        ("직원 실행 근거 평가 제안", lambda: owner._perform(
            "직원 실행 근거 보존",
            lambda: owner.store.capture_employee_evidence_review(
                owner._id("evidence_employee_id"),
                owner._get("evidence_review_note")),
            "실제 SQLite 호출·실행 기록을 SHA256으로 보존합니다. "
            "직원 이동/모델 변경/외부 실행은 없습니다. 진행합니까?")),
    ])
    owner._buttons(employee, [
        ("개선 업무 생성 승인", lambda: _decide_employee(owner, "improvement_task")),
        ("관찰 결과만 기록", lambda: _decide_employee(owner, "observed")),
        ("평가 반려", lambda: _decide_employee(owner, "rejected")),
        ("직원 평가 감사 이력", lambda: owner._perform(
            "직원 실행 근거/관리자 결정",
            lambda: owner.store.employee_evidence_review_history(50))),
    ])
    ttk.Label(employee, text=(
        "직원별 실제 업무·모델 호출 및 승인된 결과물 건수만 사용합니다. "
        "성공률/호출 수가 실제 품질·매출을 증명하지 않으며, "
        "개선 업무 승인도 직원 자동 이동·모델 재설정을 하지 않습니다."),
        wraplength=800).pack(anchor="w", padx=12, pady=10)


def _decide_recovery(owner, decision):
    label = "복구 전 확인 업무 생성" if decision == "followup_task" else "복구 후속 반려"
    owner._perform(label, lambda: owner.store.decide_recovery_work_order(
        owner._id("recovery_work_id"), decision,
        owner._get("recovery_work_note")),
        "기존 중단 감사/실제 프로세스 상태를 확인했습니까? "
        "승인해도 모델/도구/결제는 자동 재실행되지 않습니다. 진행합니까?")


def _decide_employee(owner, decision):
    label = {
        "improvement_task": "직원 개선 업무 생성",
        "observed": "직원 관찰 결과 기록",
        "rejected": "직원 평가 반려",
    }[decision]
    owner._perform(label, lambda: owner.store.decide_employee_evidence_review(
        owner._id("evidence_review_id"), decision,
        owner._get("evidence_review_note")),
        "실제 SQLite 직원 실행 근거를 확인했습니까? "
        "모델 교체/조직 변경/외부 실행은 하지 않습니다. 진행합니까?")
