"""Native Tk owner-only real SMTP delivery of GGUF-approved customer order.

Never stores SMTP password in a Tk StringVar, SQLite row, audit log, or
packaged config. Secret is prompted only after an explicit owner confirmation.
No unattended sending and no receipt delivery claim.
"""
from __future__ import annotations

from tkinter import simpledialog,ttk


def attach(owner,tabs):
    panel=ttk.Frame(tabs)
    tabs.add(panel,text="실제 고객 SMTP 전달")
    owner._field(panel,"mail_handoff_id","실제 GGUF 승인 주문 연결 번호")
    owner._field(panel,"mail_server_host","소유자 지정 SMTP 서버 (TLS 전용)")
    owner._field(panel,"mail_sender","실제 발신자 이메일")
    owner._field(panel,"mail_recipient","고객 수신 이메일 (소유자 지정)")
    owner._field(panel,"mail_username","SMTP 인증 계정")
    owner._field(panel,"mail_note","실제 발송 관리자 사유 (5~200자)")
    owner._buttons(panel,[
        ("관리자 직접 승인 실제 SMTP 상품 ZIP 전달",lambda:owner._perform(
            "실제 고객 SMTP 서버 접수 시도",
            lambda:owner.store.send_approved_model_customer_email(
                owner._id("mail_handoff_id"),
                owner._get("mail_server_host"),465,
                owner._get("mail_sender"),owner._get("mail_recipient"),
                owner._get("mail_username"),
                simpledialog.askstring("AIWACK 실제 SMTP 인증",
                    "일회성 SMTP 비밀번호/앱 비밀번호를 입력하세요.\n"
                    "비밀번호는 프로그램 DB에 저장하지 않습니다.",
                    parent=owner.window,show="*"),
                owner._get("mail_note")),
            "실제 고객 이메일 발송입니다. 기존 주문 승인·환불 여부·"
            "직원/총괄 실제 GGUF 승인 ZIP SHA256을 재확인한 뒤 "
            "이 화면에 입력한 고객 이메일 주소로 현재 SMTP 서버를 "
            "이용하여 압축 파일을 한 번 전송합니다. "
            "네트워크 불명확/실패 후 자동 재전송은 금지합니다. "
            "서버의 메시지 접수는 고객 실제 수령·결제/은행 정산을 "
            "증명하지 않습니다. 실제 발송을 명시 승인합니까?")),
    ])
    owner._buttons(panel,[
        ("고객 SMTP 실제 접수/실패/미확인 감사 내역",lambda:owner._perform(
            "실제 고객 이메일 서버 접수 감사·재시도 차단 내역",
            lambda:owner.store.approved_model_customer_email_history(50))),
        ("전달 전 실제 주문·환불·취소 이력",lambda:owner._perform(
            "원본 실제 AI GGUF 제품 준비와 현재 주문 상태 조회",
            lambda:owner.store.real_release_order_handoff_history(50))),
    ])
    ttk.Label(panel,wraplength=820,text=(
        "SMTP는 선택적 외부 서비스로 이 기능을 쓰지 않으면 AIWACK은 "
        "인터넷 연결 없이 기존 Windows EXE 기능을 수행합니다. "
        "이 화면은 사용자 직접 요청 시에만 인증서 검증 TLS(포트 465) "
        "연결을 시도합니다. 서버 수신 완료는 최종 고객 받은편지함 "
        "수령과 다릅니다. 발송은 주문당 1번만 시도하며 장애/종료 후 "
        "재시도하지 않습니다. 고객 연락처는 관리자 직접 입력입니다. "
        "비밀번호는 현재 발송 함수 메모리 안에서만 사용합니다."
    )).pack(anchor="w",padx=12,pady=12)
