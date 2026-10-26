"""Korean Windows Tk owner-only Toss Payments full/partial cancellation tab.

No automatic POST, refunds, API key persistence, or UI background polling.
A typed amount+paymentKey challenge and a separate yes/no dialog are mandatory.
"""
from __future__ import annotations

from tkinter import simpledialog,ttk


def attach(owner,tabs):
    panel=ttk.Frame(tabs)
    tabs.add(panel,text="토스 실제 환불 직접 승인")
    owner._field(panel,"refund_event_id","기존 HMAC 승인 정산 이벤트 번호")
    owner._field(panel,"refund_payment_key","실제 토스 paymentKey (기존 거래번호)")
    owner._field(panel,"refund_order_id","실제 토스 orderId (PG 조회와 일치)")
    owner._field(panel,"refund_amount","이번 실제 취소 금액 (KRW 정수)")
    owner._field(panel,"refund_cancel_reason","PG 실제 취소 사유 (5~200자)")
    owner._field(panel,"refund_owner_note","관리자 직접 환불 승인 근거 (5~200자)")
    owner._field(panel,"refund_challenge","확인 문구: 환불확인:금액:paymentKey끝6자")
    owner._buttons(panel,[
        ("로컬 HMAC·PG 조회 성공 원본/취소 금액 사전 확인",
         lambda:owner._perform(
            "토스 실환불 원본 검토 (외부 접속·금전 이동 없음)",
            lambda:owner.store.preview_toss_owner_refund(
                owner._id("refund_event_id"),
                owner._get("refund_payment_key"),
                owner._get("refund_order_id"),
                owner._id("refund_amount")))),
    ])
    owner._buttons(panel,[
        ("관리자 1회 명시 승인 실제 PG 환불 요청",lambda:owner._perform(
            "토스페이먼츠 실제 금전 취소 POST 실행 결과",
            lambda:owner.store.cancel_toss_payment_once(
                owner._id("refund_event_id"),
                owner._get("refund_payment_key"),
                owner._get("refund_order_id"),
                owner._id("refund_amount"),
                simpledialog.askstring("AIWACK | 실제 환불 API 인증",
                    "실제 PG 결제 취소 POST가 실행됩니다.\n"
                    "테스트/운영 시크릿 키를 한 번만 입력하세요.\n"
                    "이 키는 SQLite·로그·설정에 저장하지 않습니다.",
                    show="*",parent=owner.window),
                owner._get("refund_cancel_reason"),
                owner._get("refund_owner_note"),
                owner._get("refund_challenge")),
            "주의: 이 버튼은 실제 결제 취소·부분 환불 요청입니다.\n"
            "사전 로컬 조회와 PG 현재 상태 조회가 성공하면 "
            "토스페이먼츠 외부 POST 취소 API를 호출합니다.\n"
            "가상계좌·에스크로·면세·기존 부분취소 결제는 거부합니다.\n"
            "한 번 시도한 거래는 통신 장애·프로그램 중단·PG 거절 후에도 "
            "자동 또는 이 화면에서 재시도하지 않습니다.\n"
            "확인 문구에 정확한 원화 금액과 paymentKey 끝 6자리를 입력했습니까?\n"
            "현재 건의 실제 금전 취소를 명시 승인합니까?")),
    ])
    owner._buttons(panel,[
        ("실제 PG 환불 시도·서버 응답·미확정 감사 조회",lambda:owner._perform(
            "실제 PG 취소/부분취소 불변 원본 이력",
            lambda:owner.store.toss_owner_refund_history(50))),
        ("기존 실제 PG 결제 상태 조회 감사",lambda:owner._perform(
            "실제 결제 GET 조회 성공 원본",
            lambda:owner.store.toss_payment_lookup_history(50))),
    ])
    ttk.Label(panel,wraplength=830,text=(
        "환불 기능은 사용자가 매번 직접 클릭하고 금액 확인 문구·별도 "
        "예/아니오 승인·일회성 비밀키 입력을 해야만 실행됩니다. "
        "자동 환불·자동 재시도·백그라운드 PG 접속은 없습니다. "
        "먼저 '토스 실제 결제 조회' 탭에서 같은 HMAC 이벤트/주문/키의 "
        "실제 결제 상태 조회 성공이 필요합니다. "
        "API 서버가 취소를 접수했더라도 고객 계좌 실제 입금이나 "
        "은행 정산·매출은 별도 독립 확인이 필요합니다. "
        "Windows EXE/실계정/T01~T20 통합검증은 아직 수행하지 않았습니다."
    )).pack(anchor="w",padx=12,pady=12)
