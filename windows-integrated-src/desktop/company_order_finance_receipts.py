"""관리자 주문별 로컬 재무 증빙 검토 스냅샷 — 매출/은행 독립 확인 아님.

실제 기존 주문·환불·상품 파일·고객지원 상태를 읽어 불변 감사 영수증으로
기록한다. 동일 증빙의 중복 검토 차단 및 이후 증빙 변경 탐지가 목적이다.
"""
from __future__ import annotations

import hashlib
import json

from desktop import company_local_order_fulfillment as orders
from desktop import company_local_delivery_packets as packets
from desktop import company_order_support as support
from desktop.stage87_90_management import stopped

KINDS = ("local_documents_reviewed", "needs_followup")


def _json(data):
    return json.dumps(data, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"))


def _sha(data):
    return hashlib.sha256(_json(data).encode("utf-8")).hexdigest()


def initialize(con):
    support.initialize(con)
    packets.initialize(con)
    con.execute("""CREATE TABLE IF NOT EXISTS aiwack_local_finance_evidence_reviews(
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      order_id INTEGER NOT NULL REFERENCES aiwack_local_order_intakes(id),
      kind TEXT NOT NULL CHECK(kind IN('local_documents_reviewed','needs_followup')),
      evidence_json TEXT NOT NULL,
      evidence_sha256 TEXT NOT NULL CHECK(length(evidence_sha256)=64),
      receipt_sha256 TEXT NOT NULL CHECK(length(receipt_sha256)=64),
      owner_note TEXT NOT NULL CHECK(length(owner_note) BETWEEN 5 AND 200),
      created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
      UNIQUE(order_id,kind,evidence_sha256)
    )""")
    for op in ("UPDATE", "DELETE"):
        con.execute(f"""CREATE TRIGGER IF NOT EXISTS aiwack_finance_evidence_no_{op.lower()}
          BEFORE {op} ON aiwack_local_finance_evidence_reviews BEGIN
          SELECT RAISE(ABORT,'로컬 재무 증빙 검토 원본 변경 금지'); END""")


def _evidence(store, order_id):
    order = orders.read(store, order_id)
    linked = support.read(store, order_id)["customer_cases"]
    with store._connect() as con:
        initialize(con)
        packet = con.execute(
            "SELECT id FROM aiwack_local_order_delivery_packets WHERE order_id=?",
            (order_id,)).fetchone()
    packet_id = int(packet[0]) if packet else None
    if packet_id is not None:
        packets.read(store, packet_id)
    return dict(order_id=order_id, business_id=order["business_id"],
                order_ref=order["order_ref"],
                settlement_evidence_event_id=order["payment_event_id"],
                bank_csv_match_id=order["bank_match_id"],
                evidence_amount_minor=order["amount_minor"],
                refund_evidence_minor=order["accepted_refund_minor"],
                unlinked_refund_ids=order["unlinked_refund_ids"],
                local_package_approved=order["local_package_approved"],
                local_cancel_requested=order["local_cancel_requested"],
                product_document_sha256=order["document_sha256"],
                local_packet_id=packet_id,
                customer_case_states=[
                    {"case_id": c["id"], "state": c["state"],
                     "reply_sha256": c["reply_sha256"]}
                    for c in sorted(linked, key=lambda c: c["id"])],
                actual_revenue_verified=False,
                independent_bank_or_pg_verified=False,
                actual_customer_delivery_sent=False)


def capture(store, order_id, kind, owner_note):
    store.require_permission("company:manage")
    orders._id(order_id, "주문")
    if kind not in KINDS:
        raise ValueError("로컬 문서 검토/후속 조사 중 선택하세요.")
    note = orders._text(owner_note, "관리자 재무 검토 사유", 200)
    if len(note) < 5:
        raise ValueError("관리자 사유 5자 이상")
    evidence = _evidence(store, order_id)
    digest = _sha(evidence)
    receipt = _sha({"order_id": order_id, "kind": kind,
                    "evidence_sha256": digest, "owner_note": note})
    with store._connect() as con:
        con.execute("BEGIN IMMEDIATE")
        initialize(con)
        if stopped(con):
            raise PermissionError("비상정지 중 재무 증빙 검토 금지")
        fresh = orders._verify(con, order_id)
        if (fresh["payment_event_id"] != evidence["settlement_evidence_event_id"]
                or fresh["accepted_refund_minor"] != evidence["refund_evidence_minor"]
                or fresh["unlinked_refund_ids"] != evidence["unlinked_refund_ids"]
                or fresh["document_sha256"] != evidence["product_document_sha256"]):
            raise ValueError("검토 도중 주문·환불 증빙이 변경되었습니다.")
        row = con.execute(
            "SELECT id FROM aiwack_local_order_delivery_packets WHERE order_id=?",
            (order_id,)).fetchone()
        if (int(row[0]) if row else None) != evidence["local_packet_id"]:
            raise ValueError("검토 도중 상품 준비 기록이 변경되었습니다.")
        case_rows = con.execute("""SELECT c.id,c.state,c.reply_sha256
          FROM aiwack_local_order_support_links l
          JOIN aiwack_customer_cases c ON c.id=l.case_id
          WHERE l.order_id=? ORDER BY c.id""", (order_id,)).fetchall()
        if ([dict(case_id=r[0], state=r[1], reply_sha256=r[2]) for r in case_rows]
                != evidence["customer_case_states"]):
            raise ValueError("검토 도중 고객지원 상태가 변경되었습니다.")
        if con.execute("""SELECT 1 FROM aiwack_local_finance_evidence_reviews
           WHERE order_id=? AND kind=? AND evidence_sha256=?""",
           (order_id, kind, digest)).fetchone():
            raise ValueError("동일 증빙·판단의 재무 검토 중복 기록 금지")
        review_id = int(con.execute("""INSERT INTO aiwack_local_finance_evidence_reviews
          (order_id,kind,evidence_json,evidence_sha256,receipt_sha256,owner_note)
          VALUES(?,?,?,?,?,?)""",
          (order_id, kind, _json(evidence), digest, receipt, note)).lastrowid)
    return read(store, review_id)


def read(store, review_id):
    store.require_permission("company:manage")
    orders._id(review_id, "재무 증빙 검토")
    with store._connect() as con:
        initialize(con)
        row = con.execute("""SELECT order_id,kind,evidence_json,evidence_sha256,
              receipt_sha256,owner_note FROM aiwack_local_finance_evidence_reviews
              WHERE id=?""", (review_id,)).fetchone()
    if row is None:
        raise ValueError("재무 증빙 검토 기록 없음")
    order_id, kind, raw, digest, receipt, note = row
    evidence = json.loads(raw)
    if (_sha(evidence) != digest or
            _sha({"order_id": order_id, "kind": kind,
                  "evidence_sha256": digest, "owner_note": note}) != receipt):
        raise ValueError("재무 증빙 검토 영수증 SHA 손상")
    current = _evidence(store, int(order_id))
    return dict(id=review_id, order_id=order_id, kind=kind,
                evidence_sha256=digest, receipt_sha256=receipt,
                evidence_changed=_sha(current) != digest,
                original_local_evidence=evidence,
                owner_note=note, actual_revenue_verified=False,
                independent_bank_or_pg_verified=False)


def history(store, limit=50):
    store.require_permission("company:manage")
    if type(limit) is not int or not 1 <= limit <= 200:
        raise ValueError("재무 검토 조회 1~200건")
    with store._connect() as con:
        initialize(con)
        ids = [int(r[0]) for r in con.execute(
            "SELECT id FROM aiwack_local_finance_evidence_reviews ORDER BY id DESC LIMIT ?",
            (limit,)).fetchall()]
    return [read(store, rid) for rid in ids]
