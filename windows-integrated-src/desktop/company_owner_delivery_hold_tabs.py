"""Korean Tk order delivery hold administration; no network effects."""
from __future__ import annotations
from tkinter import ttk


def attach(owner, tabs):
    panel = ttk.Frame(tabs)
    tabs.add(panel, text="고객발송 보류·PG환불 연계")
    owner._field(panel, "delivery_hold_order_id", "기존 로컬 주문 ID")
    owner._field(panel, "delivery_hold_reason", "영구 보류 관리자 사유")
    owner._buttons(panel, [
        ("주문 환불·배송 차단 상태", lambda: owner._perform(
            "기존 주문·Toss 취소시도와 로컬 배송 가능 여부",
            lambda: owner.store.preview_order_delivery_hold(
                owner._id("delivery_hold_order_id")))),
        ("관리자 영구 배송 보류", lambda: owner._perform(
            "주문 배송 보류 저장",
            lambda: owner.store.hold_order_delivery(
                owner._id("delivery_hold_order_id"),
                owner._get("delivery_hold_reason")),
            "이 주문의 새로운 상품 인계·고객 SMTP 발송을 영구 차단하고 "
            "원본 감사 기록을 보존합니다. 취소/해제 기능은 없습니다. "
            "외부 환불, 발송, 결제는 실행하지 않습니다. 계속하시겠습니까?")),
        ("보류 및 실제 PG 취소 시도 이력", lambda: owner._perform(
            "외부 작업 없는 보류·PG 환불 감사 조회",
            lambda: owner.store.order_delivery_hold_history(50)))
    ])
    ttk.Label(panel, text=(
        "기존 실PG 취소 시도가 1건이라도 있으면 결과가 not_sent라도 "
        "해당 주문의 신규 SMTP 발송·상품 인계를 차단합니다. "
        "PG 취소 수락은 은행/고객 실제 입금 확인이 아닙니다. "
        "조회는 외부 API를 호출하지 않습니다."
    ), wraplength=800).pack(padx=12, pady=14, anchor="w")
