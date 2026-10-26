"""기존 AIWACK Windows Tk 고객지원 승인 답변 실제 SMTP 발송 탭.

원문과 SHA 미리보기 후 관리자 별도 승인, 일회성 비밀번호 입력.
조회는 네트워크를 호출하지 않으며 자동 고객 발송은 없다.
"""
from __future__ import annotations

from tkinter import simpledialog, ttk


def attach(owner, tabs):
    panel = ttk.Frame(tabs)
    tabs.add(panel, text="고객지원 승인 답변 SMTP")
    owner._field(panel, "support_mail_case_id", "승인된 고객지원 문의 번호")
    owner._field(panel, "support_mail_hash", "미리보기 SHA256 앞 12자리")
    owner._field(panel, "support_mail_host", "SMTP 서버 호스트 (TLS 465)")
    owner._field(panel, "support_mail_sender", "발신 이메일")
    owner._field(panel, "support_mail_recipient", "고객 수신 이메일")
    owner._field(panel, "support_mail_user", "SMTP 인증 계정")
    owner._field(panel, "support_mail_note", "실제 발송 관리자 사유 (5~200자)")
    owner._buttons(panel, [
        ("승인 답변 원문·SHA256 전체 미리보기", lambda: owner._perform(
            "직원/총괄 승인 고객지원 원문 (읽기 전용)",
            lambda: owner.store.preview_customer_reply_smtp(
                owner._id("support_mail_case_id")))),
        ("고객지원 실제 SMTP 1회 발송", lambda: owner._perform(
            "관리자 승인 고객지원 SMTP 접수 결과",
            lambda: owner.store.send_customer_reply_smtp(
                owner._id("support_mail_case_id"),
                owner._get("support_mail_host"), 465,
                owner._get("support_mail_sender"),
                owner._get("support_mail_recipient"),
                owner._get("support_mail_user"),
                simpledialog.askstring(
                    "AIWACK 실제 고객지원 SMTP 인증",
                    "일회성 SMTP 비밀번호를 입력하세요. DB/로그에는 저장하지 않습니다.",
                    parent=owner.window, show="*"),
                owner._get("support_mail_note"),
                owner._get("support_mail_hash")),
            "실제 외부 고객지원 이메일 전송입니다. 먼저 승인된 답변 전체를 "
            "미리보고 SHA256 앞 12자리를 입력했습니까? 지정 수신자에게 "
            "실제 이메일을 한 번 보냅니다. 결과 불명/실패 후 자동 재시도는 "
            "없습니다. SMTP 접수는 고객 받은편지함 수령이 아닙니다. "
            "해당 단일 발송을 명시적으로 승인합니까?")),
        ("고객지원 SMTP 시도 불변 이력", lambda: owner._perform(
            "고객지원 실제 SMTP 접수·실패·미확인 감사",
            lambda: owner.store.customer_reply_smtp_history(50)))
    ])
    ttk.Label(panel, wraplength=830, text=(
        "이 탭은 기존 승인 고객지원 직원 결과와 총괄 모델 감사 원본을 사용합니다. "
        "미리보기는 실제 외부 통신을 하지 않습니다. 발송 전에 원문 전체와 "
        "고객 주소를 직접 검토하세요. 한 문의당 단 한 번의 SMTP 시도만 "
        "기록하며 실패/중단 후에도 자동 재발송하지 않습니다. "
        "모델 바이너리의 독립 검증·실제 고객 수령·실제 매출·환불 성공을 "
        "주장하지 않습니다. 외부 계정 없이 로컬 EXE의 다른 기능은 동작합니다."
    )).pack(anchor="w", padx=12, pady=12)
