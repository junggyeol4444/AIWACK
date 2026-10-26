"""실제 주문/환불/상품 준비/고객지원 원본의 관리자 읽기 전용 대조.

서명된 PG 증빙과 사용자가 가져온 은행 CSV는 독립 은행 확인이 아니다.
여기서 합산한 금액은 실제 매출이나 이익으로 분류하지 않는다.
"""
from __future__ import annotations

from desktop import company_local_order_fulfillment as orders
from desktop import company_local_delivery_packets as packets
from desktop import company_order_support as support
from desktop import company_real_release_order_handoff as real_handoff


def snapshot(store, business_id: int | None = None, limit: int = 100) -> dict:
    store.require_permission('company:manage')
    if business_id is not None:
        orders._id(business_id, '사업')
    if type(limit) is not int or not 1 <= limit <= 200:
        raise ValueError('주문 대조 범위 1~200건')
    with store._connect() as con:
        support.initialize(con)
        packets.initialize(con)
        if business_id is None:
            rows = con.execute(
                'SELECT id FROM aiwack_local_order_intakes ORDER BY id DESC LIMIT ?',
                (limit,)).fetchall()
        else:
            rows = con.execute(
                'SELECT id FROM aiwack_local_order_intakes WHERE business_id=? '
                'ORDER BY id DESC LIMIT ?', (business_id, limit)).fetchall()
        ids = [int(row[0]) for row in rows]
    entries = []
    for order_id in ids:
        order = orders.read(store, order_id)
        with store._connect() as con:
            support.initialize(con)
            packets.initialize(con)
            packet = con.execute(
                'SELECT id FROM aiwack_local_order_delivery_packets WHERE order_id=?',
                (order_id,)).fetchone()
            has_handoff=bool(con.execute("""SELECT 1 FROM sqlite_master
                WHERE type='table' AND name='aiwack_real_release_order_handoffs'""").fetchone())
            handoff_id=(con.execute("""SELECT id FROM aiwack_real_release_order_handoffs
                WHERE order_id=?""",(order_id,)).fetchone()
                if has_handoff else None)
            smtp_available=bool(con.execute("""SELECT 1 FROM sqlite_master
                WHERE type='table' AND name='aiwack_smtp_customer_deliveries'""").fetchone())
            smtp_event=(con.execute("""SELECT id,status,recipient,message_id,
                claimed_at,finished_at FROM aiwack_smtp_customer_deliveries
                WHERE order_id=?""",(order_id,)).fetchone()
                if smtp_available else None)
            case_ids = [int(row[0]) for row in con.execute(
                'SELECT case_id FROM aiwack_local_order_support_links '
                'WHERE order_id=? ORDER BY case_id', (order_id,)).fetchall()]
        if packet:
            prepared = packets.read(store, int(packet[0]))
            if prepared['order_id'] != order_id:
                raise ValueError('로컬 상품 준비의 주문 번호 불일치')
        real_ready=(real_handoff.read(store,int(handoff_id[0]))
                    if handoff_id else None)
        cases = support.read(store, order_id)['customer_cases']
        if {int(case['id']) for case in cases} != set(case_ids):
            raise ValueError('주문·고객지원 원본 연결 감사 불일치')
        entries.append(dict(
            order_id=order_id, business_id=order['business_id'],
            order_ref=order['order_ref'], evidence_amount_minor=order['amount_minor'],
            accepted_refund_evidence_minor=order['accepted_refund_minor'],
            unlinked_refund_event_ids=order['unlinked_refund_ids'],
            local_package_approved=order['local_package_approved'],
            local_cancel_requested=order['local_cancel_requested'],
            local_packet_id=int(packet[0]) if packet else None,
            local_packet_verified=bool(packet), linked_customer_case_ids=case_ids,
            # SMTP server acceptance != customer inbox receipt.
            actual_customer_delivery_sent=False,
            actual_smtp_send_attempt_id=int(smtp_event[0]) if smtp_event else None,
            actual_smtp_state=smtp_event[1] if smtp_event else "not_attempted",
            actual_smtp_recipient=smtp_event[2] if smtp_event else None,
            actual_smtp_message_id=smtp_event[3] if smtp_event else None,
            actual_smtp_claimed_at=smtp_event[4] if smtp_event else None,
            actual_smtp_finished_at=smtp_event[5] if smtp_event else None,
            smtp_server_accepted=bool(smtp_event and smtp_event[1]=="accepted_by_smtp"),
            smtp_delivery_outcome_unknown=bool(
                smtp_event and smtp_event[1] in ("claimed","outcome_unknown")),
            independent_customer_receipt_verified=False,
            actual_gguf_order_release_handoff_id=(
                int(handoff_id[0]) if handoff_id else None),
            actual_gguf_release_id=(
                real_ready["release_id"] if real_ready else None),
            local_model_release_prepared=bool(real_ready),
            currently_eligible_for_local_handoff=(
                real_ready["current_owner_delivery_ready"] if real_ready else False)))
    gross = sum(int(x['evidence_amount_minor']) for x in entries)
    refunds = sum(int(x['accepted_refund_evidence_minor']) for x in entries)
    return dict(
        business_id=business_id, inspected_orders=len(entries), requested_limit=limit,
        local_signed_settlement_evidence_minor=gross,
        local_accepted_refund_evidence_minor=refunds,
        local_net_evidence_minor=gross-refunds,
        local_package_approved_count=sum(bool(x['local_package_approved']) for x in entries),
        local_packet_verified_count=sum(bool(x['local_packet_verified']) for x in entries),
        smtp_send_attempt_count=sum(bool(x['actual_smtp_send_attempt_id']) for x in entries),
        smtp_server_accepted_count=sum(bool(x['smtp_server_accepted']) for x in entries),
        smtp_outcome_unknown_count=sum(bool(x['smtp_delivery_outcome_unknown']) for x in entries),
        independent_customer_receipt_verified_count=0,
        local_real_gguf_release_handoff_count=sum(
            bool(x['local_model_release_prepared']) for x in entries),
        pending_cancel_request_count=sum(bool(x['local_cancel_requested']) for x in entries),
        unlinked_refund_event_count=sum(len(x['unlinked_refund_event_ids']) for x in entries),
        linked_customer_case_count=sum(len(x['linked_customer_case_ids']) for x in entries),
        orders=entries, actual_revenue_minor=None, actual_profit_minor=None,
        independent_pg_or_bank_verified=False, customer_delivery_executed=False,
        read_only=True, full_database_audit=False)
