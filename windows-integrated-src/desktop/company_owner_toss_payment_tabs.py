"""Korean native Tk owner controls for Toss Payments read-only GET verification.

This optional tab is not a web UI. It never automatically queries, approves,
charges, cancels or refunds a transaction. Secret is entered per owner action.
"""
from __future__ import annotations

from tkinter import simpledialog,ttk


def attach(owner,tabs):
    panel=ttk.Frame(tabs)
    tabs.add(panel,text="토스 실제 결제 조회")
    owner._field(panel,"toss_event_id","기존 HMAC 인증·관리자 승인 결제 이벤트 번호")
    owner._field(panel,"toss_payment_key","토스페이먼츠 실제 paymentKey (기존 거래번호와 동일)")
    owner._field(panel,"toss_order_id","실제 PG 원본 주문번호 orderId")
    owner._field(panel,"toss_reason","외부 실제 조회 관리자 사유 (5~200자)")
    owner._buttons(panel,[
        ("로컬 원본·서명 승인·은행 대사 상태 사전 조회",
         lambda:owner._perform("토스 결제 원본 조회 사전 확인 (외부 접속 없음)",
            lambda:owner.store.preview_toss_payment_lookup(
                owner._id("toss_event_id"),owner._get("toss_payment_key"),
                owner._get("toss_order_id")))),
        ("관리자 직접 승인 토스 실제 결제 상태 조회",
         lambda:owner._perform("토스페이먼츠 실제 읽기 전용 GET API 확인",
            lambda:owner.store.verify_toss_payment_lookup(
                owner._id("toss_event_id"),owner._get("toss_payment_key"),
                owner._get("toss_order_id"),
                simpledialog.askstring("AIWACK | 토스 실제 조회 인증",
                    "토스페이먼츠 개발자센터 테스트/운영 시크릿 키를 "
                    "이번 한 번의 조회에만 입력하세요.\n"
                    "키는 DB·로그·설정에 저장하지 않습니다.",
                    show="*",parent=owner.window),
                owner._get("toss_reason")),
            "현재 소유자가 승인한 토스페이먼츠 결제 원본을 외부 "
            "토스페이먼츠 공식 API 서버에 HTTPS GET으로 한 번 조회합니다. "
            "원본 HMAC 승인 이벤트의 paymentKey·원화 금액, 실제 응답 "
            "orderId·결제 완료 상태·취소 여부를 비교하고 응답 SHA256만 "
            "로컬 감사에 기록합니다. POST/결제 승인/취소/환불/송금은 "
            "절대로 호출하지 않습니다. 이 조회는 은행 입금 또는 향후 "
            "환불 부재를 보장하지 않습니다. 실제 외부 조회를 승인합니까?")),
    ])
    owner._buttons(panel,[
        ("토스 실제 조회 성공/불일치/통신 실패 원본",lambda:owner._perform(
            "토스 실제 PG 상태 읽기 전용 감사 이력",
            lambda:owner.store.toss_payment_lookup_history(50))),
        ("기존 HMAC 인증 공급자 거래 이력",lambda:owner._perform(
            "기존 관리자 서명 거래 원본 목록",
            lambda:owner.store.list_signed_payment_events(50))),
    ])
    ttk.Label(panel,wraplength=840,text=(
        "이 기능은 사용자 직접 클릭과 관리자 명시 승인 뒤에만 "
        "api.tosspayments.com 공식 HTTPS GET 결제 조회 API를 사용합니다. "
        "기존 거래 공급자 식별자는 tosspayments이고, 거래번호는 실제 "
        "paymentKey와 같아야 합니다. 토스 시크릿 키는 실행 때만 "
        "입력하며 저장하지 않습니다. PG 응답의 DONE·KRW·금액·"
        "orderId·취소 없음이 일치해도 은행 정산이나 고객 수령·"
        "최종 매출을 증명하지 않습니다. 실계정 연결/Windows EXE "
        "최종 검증은 아직 별도로 필요합니다."
    )).pack(anchor="w",padx=12,pady=12)
