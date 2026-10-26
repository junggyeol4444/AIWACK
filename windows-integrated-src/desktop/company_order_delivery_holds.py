"""Local owner-controlled fulfilment safety holds for real order handoffs.

A hold is an immutable SQLite record, not a provider refund or customer contact.
A single real Toss refund *attempt*, including claimed/not_sent/unknown, blocks
future local package handoffs and customer SMTP messages for that order. Nothing
here makes a network request or marks an actual customer refund as complete.
"""
from __future__ import annotations

import hashlib
import json

from desktop import company_local_order_fulfillment as orders
from desktop import company_toss_owner_refund as toss_refunds
from desktop.stage87_90_management import stopped


def initialize(con):
    orders.initialize(con)
    toss_refunds.initialize(con)
    con.execute("""CREATE TABLE IF NOT EXISTS aiwack_order_delivery_owner_holds(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        order_id INTEGER NOT NULL UNIQUE REFERENCES aiwack_local_order_intakes(id),
        payment_event_id INTEGER NOT NULL REFERENCES aiwack_provider_payment_events(id),
        owner_reason TEXT NOT NULL CHECK(length(owner_reason) BETWEEN 5 AND 200),
        evidence_sha256 TEXT NOT NULL CHECK(length(evidence_sha256)=64),
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    )""")
    for operation in ("UPDATE", "DELETE"):
        con.execute("""CREATE TRIGGER IF NOT EXISTS aiwack_order_delivery_holds_no_%s
            BEFORE %s ON aiwack_order_delivery_owner_holds
            BEGIN SELECT RAISE(ABORT,'고객 주문 배송 보류 감사 원본 변경 금지'); END"""
            % (operation.lower(), operation))


def _digest(order_id, payment_event_id, reason):
    payload = json.dumps({"order_id": order_id,
                          "payment_event_id": payment_event_id,
                          "owner_reason": reason}, sort_keys=True,
                         separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _evidence(con, order_id):
    orders._id(order_id, "주문")
    order = orders._verify(con, order_id)
    attempt = con.execute("""SELECT id, state, cancel_amount_minor, created_at
        FROM aiwack_toss_owner_refund_attempts
        WHERE payment_event_id=? ORDER BY id DESC LIMIT 1""",
        (order["payment_event_id"],)).fetchone()
    hold = con.execute("""SELECT id, payment_event_id, owner_reason,
        evidence_sha256, created_at FROM aiwack_order_delivery_owner_holds
        WHERE order_id=?""", (order_id,)).fetchone()
    if hold and (hold[1] != order["payment_event_id"] or
                 hold[3] != _digest(order_id, hold[1], hold[2])):
        raise ValueError("배송 보류 원장 SHA256/결제 이벤트 불일치")
    return {
        "order_id": order_id,
        "order_ref": order["order_ref"],
        "payment_event_id": order["payment_event_id"],
        "owner_hold_id": int(hold[0]) if hold else None,
        "owner_hold_reason": hold[2] if hold else None,
        "hold_created_at": hold[4] if hold else None,
        "toss_refund_attempt_id": int(attempt[0]) if attempt else None,
        "toss_refund_state": attempt[1] if attempt else None,
        "toss_refund_amount_krw": int(attempt[2]) if attempt else None,
        "toss_attempt_created_at": attempt[3] if attempt else None,
        "signed_refund_evidence_exists": bool(order["accepted_refund_minor"]),
        "unlinked_refund_event_ids": list(order["unlinked_refund_ids"]),
        "order_cancel_requested": bool(order["cancel_requested"]),
        "owner_package_approved": bool(order["approved"]),
        "blocked": bool(hold or attempt or order["cancel_requested"] or
                        order["accepted_refund_minor"] or
                        order["unlinked_refund_ids"]),
        "actual_customer_refund_verified": False,
        "external_api_invoked": False
    }


def assert_no_delivery_block(con, order_id):
    """Enforce before outbound send *and* inside its SQLite claim transaction."""
    initialize(con)
    record = _evidence(con, order_id)
    if record["blocked"]:
        raise PermissionError(
            "고객 배송 차단: 주문 취소·환불 원본 또는 관리자 영구 보류가 존재합니다"
        )
    return record


def preview(store, order_id):
    store.require_permission("company:manage")
    with store._connect() as con:
        initialize(con)
        return _evidence(con, order_id)


def hold(store, order_id, owner_reason):
    """One explicit owner click: immutable hold, without financial side effect."""
    store.require_permission("company:manage")
    store.require_permission("agents:manage")
    orders._id(order_id, "주문")
    if (type(owner_reason) is not str or
            not 5 <= len(owner_reason.strip()) <= 200 or
            any(ord(c) < 32 or ord(c) == 127 for c in owner_reason)):
        raise ValueError("관리자 보류 사유는 제어문자 없이 5~200자")
    reason = owner_reason.strip()
    with store._connect() as con:
        con.execute("BEGIN IMMEDIATE")
        initialize(con)
        if stopped(con):
            raise PermissionError("비상정지 중 새 주문 보류 조작 금지")
        current = _evidence(con, order_id)
        if current["owner_hold_id"]:
            raise ValueError("이 주문은 이미 관리자 보류 상태이며 원본을 변경하지 않습니다")
        digest = _digest(order_id, current["payment_event_id"], reason)
        con.execute("""INSERT INTO aiwack_order_delivery_owner_holds(
            order_id,payment_event_id,owner_reason,evidence_sha256)
            VALUES(?,?,?,?)""",
            (order_id, current["payment_event_id"], reason, digest))
    return preview(store, order_id)


def history(store, limit=50):
    store.require_permission("company:manage")
    if type(limit) is not int or not 1 <= limit <= 200:
        raise ValueError("보류 기록 조회 범위 1~200")
    with store._connect() as con:
        initialize(con)
        ids = [int(row[0]) for row in con.execute("""
            SELECT id FROM aiwack_local_order_intakes
            WHERE id IN (SELECT order_id FROM aiwack_order_delivery_owner_holds)
               OR payment_event_id IN (
                 SELECT payment_event_id FROM aiwack_toss_owner_refund_attempts)
            ORDER BY id DESC LIMIT ?""", (limit,)).fetchall()]
        return [_evidence(con, order_id) for order_id in ids]
