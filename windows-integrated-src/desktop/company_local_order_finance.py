"""실제 주문/환불/상품 준비/고객지원 원본의 관리자 읽기 전용 대조.

서명된 PG 증빙과 사용자가 가져온 은행 CSV는 독립 은행 확인이 아니다.
여기서 합산한 금액은 실제 매출이나 이익으로 분류하지 않는다.
"""
from __future__ import annotations

from desktop import company_local_order_fulfillment as orders
from desktop import company_local_delivery_packets as packets
from desktop import company_order_support as support


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
            case_ids = [int(row[0]) for row in con.execute(
                'SELECT case_id FROM aiwack_local_order_support_links '
                'WHERE order_id=? ORDER BY case_id', (order_id,)).fetchall()]
        if packet:
            prepared = packets.read(store, int(packet[0]))
            if prepared['order_id'] != order_id:
                raise ValueError('로컬 상품 준비의 주문 번호 불일치')
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
            actual_customer_delivery_sent=False))
    gross = sum(int(x['evidence_amount_minor']) for x in entries)
    refunds = sum(int(x['accepted_refund_evidence_minor']) for x in entries)
    return dict(
        business_id=business_id, inspected_orders=len(entries), requested_limit=limit,
        local_signed_settlement_evidence_minor=gross,
        local_accepted_refund_evidence_minor=refunds,
        local_net_evidence_minor=gross-refunds,
        local_package_approved_count=sum(bool(x['local_package_approved']) for x in entries),
        local_packet_verified_count=sum(bool(x['local_packet_verified']) for x in entries),
        pending_cancel_request_count=sum(bool(x['local_cancel_requested']) for x in entries),
        unlinked_refund_event_count=sum(len(x['unlinked_refund_event_ids']) for x in entries),
        linked_customer_case_count=sum(len(x['linked_customer_case_ids']) for x in entries),
        orders=entries, actual_revenue_minor=None, actual_profit_minor=None,
        independent_pg_or_bank_verified=False, customer_delivery_executed=False,
        read_only=True, full_database_audit=False)
