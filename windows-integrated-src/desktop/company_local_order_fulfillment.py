"""기존 승인 상품 문서와 HMAC 거래·관리자 은행 CSV 대사를 연결한 로컬 주문 기록.

이 모듈은 외부 주문 접수, PG 확인, 은행 입금 확인, 배송/환불 실행을 하지 않는다.
서명 증빙과 소유자 CSV는 독립 검증이 아니므로 실제 매출로 기록하지 않는다.
"""
from __future__ import annotations

import hashlib
import json
import re
import sqlite3

from desktop import company_bank_reconciliation as bank
from desktop import company_payment_reconciliation as payments
from desktop import company_product_documents as documents
from desktop.product_catalog import get as get_catalog
from desktop.stage87_90_management import stopped

REFERENCE = re.compile(r"[A-Za-z0-9._:-]{6,80}\Z")


def _id(value, name):
    if type(value) is not int or value <= 0:
        raise ValueError(name + " 번호는 양의 정수여야 합니다.")
    return value


def _text(value, name, length):
    if type(value) is not str or not 1 <= len(value.strip()) <= length:
        raise ValueError(name + " 길이 오류")
    value = value.strip()
    if any(ord(char) < 32 or ord(char) == 127 for char in value):
        raise ValueError(name + " 제어 문자 금지")
    return value


def _hash(payload):
    return hashlib.sha256(json.dumps(
        payload, sort_keys=True, ensure_ascii=False,
        separators=(",", ":")).encode("utf-8")).hexdigest()


def initialize(con: sqlite3.Connection) -> None:
    bank.initialize(con)
    documents.initialize(con)
    con.execute("""CREATE TABLE IF NOT EXISTS aiwack_local_order_intakes(
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      order_ref TEXT NOT NULL UNIQUE,
      customer_alias TEXT NOT NULL,
      business_id INTEGER NOT NULL REFERENCES managed_businesses(id),
      catalog_item_id INTEGER NOT NULL REFERENCES local_catalog_items(id),
      payment_event_id INTEGER NOT NULL UNIQUE REFERENCES aiwack_provider_payment_events(id),
      bank_match_id INTEGER NOT NULL UNIQUE REFERENCES aiwack_bank_reconciliation_matches(id),
      product_document_id INTEGER NOT NULL REFERENCES aiwack_approved_product_documents(id),
      document_sha256 TEXT NOT NULL CHECK(length(document_sha256)=64),
      amount_minor INTEGER NOT NULL CHECK(amount_minor>0),
      created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    )""")
    con.execute("""CREATE TABLE IF NOT EXISTS aiwack_local_order_actions(
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      order_id INTEGER NOT NULL REFERENCES aiwack_local_order_intakes(id),
      action TEXT NOT NULL CHECK(action IN
        ('package_approved','cancel_requested','refund_linked')),
      refund_event_id INTEGER UNIQUE REFERENCES aiwack_provider_payment_events(id),
      owner_note TEXT NOT NULL CHECK(length(owner_note) BETWEEN 5 AND 200),
      previous_sha256 TEXT NOT NULL,
      event_sha256 TEXT NOT NULL CHECK(length(event_sha256)=64),
      created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
      CHECK((action='refund_linked' AND refund_event_id IS NOT NULL) OR
            (action!='refund_linked' AND refund_event_id IS NULL))
    )""")
    con.execute("""CREATE UNIQUE INDEX IF NOT EXISTS aiwack_local_order_single_action
      ON aiwack_local_order_actions(order_id,action)
      WHERE action IN ('package_approved','cancel_requested')""")
    for table in ("aiwack_local_order_intakes", "aiwack_local_order_actions"):
        for op in ("UPDATE", "DELETE"):
            con.execute(f"""CREATE TRIGGER IF NOT EXISTS {table}_no_{op.lower()}
              BEFORE {op} ON {table} BEGIN
              SELECT RAISE(ABORT,'주문·환불 원본 감사 변경 금지'); END""")


def _source(con, event_id: int, document_id: int):
    row = con.execute("""SELECT p.provider,p.transaction_id,p.business_id,p.amount_minor,
       p.event_sha256,m.id,m.event_sha256,m.amount_minor,
       d.catalog_item_id,d.file_sha256,c.business_id,c.assumed_price_krw
       FROM aiwack_provider_payment_events p
       JOIN aiwack_bank_reconciliation_matches m ON m.payment_event_id=p.id
       JOIN aiwack_approved_product_documents d ON d.id=?
       JOIN local_catalog_items c ON c.id=d.catalog_item_id
       WHERE p.id=? AND p.event_type='settlement'
         AND p.owner_decision='accepted' AND p.authenticated=1
         AND p.currency='KRW'""", (document_id, event_id)).fetchone()
    if not row:
        raise ValueError("관리자 승인된 정산 서명 증빙·은행 CSV 대사·상품 문서 연결 누락")
    provider, transaction, business, amount, event_sha, match_id, match_sha, matched_amount, catalog_id, doc_sha, catalog_business, assumed_price = row
    catalog = get_catalog(con, int(catalog_id))
    if (event_sha != match_sha or amount != matched_amount
            or business != catalog_business or catalog["state"] == "archived"
            or amount <= 0 or amount != assumed_price):
        raise ValueError("서명 거래·은행 대사·사업·상품 가정 가격 불일치")
    return dict(provider=provider, transaction_id=transaction, business_id=int(business),
                amount_minor=int(amount), event_sha256=event_sha,
                bank_match_id=int(match_id), catalog_item_id=int(catalog_id),
                document_sha256=doc_sha)


def _accepted_refunds(con, source):
    rows = con.execute("""SELECT p.id,p.amount_minor,p.event_sha256,
          m.event_sha256,m.amount_minor
       FROM aiwack_provider_payment_events p
       JOIN aiwack_bank_reconciliation_matches m ON m.payment_event_id=p.id
       WHERE p.provider=? AND p.related_transaction=? AND p.business_id=?
         AND p.event_type='refund' AND p.owner_decision='accepted'
       ORDER BY p.id""", (source["provider"], source["transaction_id"],
                         source["business_id"])).fetchall()
    if any(row[2] != row[3] or row[1] != row[4] for row in rows):
        raise ValueError("환불 서명·은행 CSV 대사 원본 무결성 불일치")
    if sum(int(row[1]) for row in rows) > source["amount_minor"]:
        raise ValueError("원 정산액 초과 환불 증빙")
    return [(int(row[0]), int(row[1])) for row in rows]


def _actions(con, order_id):
    rows = con.execute("""SELECT action,refund_event_id,owner_note,previous_sha256,
            event_sha256 FROM aiwack_local_order_actions
            WHERE order_id=? ORDER BY id""", (order_id,)).fetchall()
    previous = ""
    approved = cancelled = False
    refunds = set()
    for action, refund_id, note, prev, digest in rows:
        if prev != previous or digest != _hash(dict(
                order_id=order_id, action=action, refund_event_id=refund_id,
                owner_note=note, previous_sha256=prev)):
            raise ValueError("주문 승인·환불 이력 SHA256 감사 손상")
        if action == "package_approved":
            if approved or cancelled or refunds or refund_id is not None:
                raise ValueError("주문 승인 순서 감사 손상")
            approved = True
        elif action == "cancel_requested":
            if cancelled or refund_id is not None:
                raise ValueError("주문 취소 요청 감사 손상")
            cancelled = True
        elif action == "refund_linked":
            if type(refund_id) is not int or refund_id in refunds:
                raise ValueError("주문 환불 이력 중복·형식 오류")
            refunds.add(refund_id)
        else:
            raise ValueError("주문 감사 유형 오류")
        previous = digest
    return dict(approved=approved, cancel_requested=cancelled,
                linked_refund_ids=refunds, previous_sha256=previous)


def _append(con, order_id, action, refund_id, note):
    state = _actions(con, order_id)
    if action == "package_approved" and (state["approved"] or state["cancel_requested"] or state["linked_refund_ids"]):
        raise ValueError("취소·환불·기존 승인 주문은 중복 승인할 수 없습니다.")
    if action == "cancel_requested" and state["cancel_requested"]:
        raise ValueError("취소 요청 중복")
    if action == "refund_linked" and refund_id in state["linked_refund_ids"]:
        raise ValueError("동일 환불 증빙 중복")
    previous = state["previous_sha256"]
    digest = _hash(dict(order_id=order_id, action=action, refund_event_id=refund_id,
                        owner_note=note, previous_sha256=previous))
    con.execute("""INSERT INTO aiwack_local_order_actions
      (order_id,action,refund_event_id,owner_note,previous_sha256,event_sha256)
      VALUES(?,?,?,?,?,?)""", (order_id, action, refund_id, note, previous, digest))


def create(store, order_ref: str, customer_alias: str,
           payment_event_id: int, document_id: int) -> dict:
    store.require_permission("company:manage")
    if type(order_ref) is not str or not REFERENCE.fullmatch(order_ref):
        raise ValueError("주문 고유 번호 형식 오류")
    alias = _text(customer_alias, "고객 별칭", 100)
    _id(payment_event_id, "서명 거래"); _id(document_id, "상품 문서")
    document = documents.read(store, document_id)
    with store._connect() as con:
        con.execute("BEGIN IMMEDIATE"); initialize(con)
        if stopped(con):
            raise PermissionError("비상정지 중 주문 등록 금지")
        source = _source(con, payment_event_id, document_id)
        if (document["sha256"] != source["document_sha256"]
                or document["catalog_item_id"] != source["catalog_item_id"]):
            raise ValueError("로컬 승인 상품 파일 원본 변경")
        if _accepted_refunds(con, source):
            raise ValueError("환불 증빙이 존재하는 정산은 신규 주문으로 등록 불가")
        order_id = int(con.execute("""INSERT INTO aiwack_local_order_intakes
          (order_ref,customer_alias,business_id,catalog_item_id,payment_event_id,
           bank_match_id,product_document_id,document_sha256,amount_minor)
          VALUES(?,?,?,?,?,?,?,?,?)""",
          (order_ref, alias, source["business_id"], source["catalog_item_id"],
           payment_event_id, source["bank_match_id"], document_id,
           source["document_sha256"], source["amount_minor"])).lastrowid)
    return read(store, order_id)


def _row(con, order_id):
    row = con.execute("""SELECT order_ref,customer_alias,business_id,catalog_item_id,
       payment_event_id,bank_match_id,product_document_id,document_sha256,amount_minor
       FROM aiwack_local_order_intakes WHERE id=?""", (order_id,)).fetchone()
    if row is None:
        raise ValueError("로컬 주문 번호 없음")
    labels = ("order_ref","customer_alias","business_id","catalog_item_id",
              "payment_event_id","bank_match_id","product_document_id",
              "document_sha256","amount_minor")
    return dict(zip(labels, row))


def _verify(con, order_id):
    row = _row(con, order_id)
    source = _source(con, row["payment_event_id"], row["product_document_id"])
    for key in ("business_id","catalog_item_id","bank_match_id",
                "document_sha256","amount_minor"):
        if row[key] != source[key]:
            raise ValueError("주문 원본과 정산·상품 승인 기록 불일치")
    state = _actions(con, order_id)
    refunds = _accepted_refunds(con, source)
    known = {event_id for event_id, _ in refunds}
    if not state["linked_refund_ids"].issubset(known):
        raise ValueError("연결된 환불 원본이 승인 상태와 일치하지 않습니다.")
    row.update(source)
    row.update(state)
    row["accepted_refund_minor"] = sum(amount for _, amount in refunds)
    row["unlinked_refund_ids"] = sorted(known - state["linked_refund_ids"])
    return row


def approve_local_package(store, order_id: int, owner_note: str) -> dict:
    store.require_permission("company:manage")
    _id(order_id, "주문")
    note = _text(owner_note, "관리자 포장 승인 사유", 200)
    if len(note) < 5: raise ValueError("관리자 사유 5자 이상")
    # Read actual approved product file before approving; no auto-delivery.
    current = read(store, order_id)
    if current["unlinked_refund_ids"] or current["accepted_refund_minor"]:
        raise ValueError("환불이 확인된 주문은 포장 승인 금지")
    with store._connect() as con:
        con.execute("BEGIN IMMEDIATE"); initialize(con)
        if stopped(con): raise PermissionError("비상정지 중 주문 승인 금지")
        fresh = _verify(con, order_id)
        if fresh["accepted_refund_minor"] or fresh["unlinked_refund_ids"]:
            raise ValueError("환불 발생 후 주문 승인 금지")
        if fresh["document_sha256"] != current["document_sha256"]:
            raise ValueError("승인 상품 문서 지문 변경")
        _append(con, order_id, "package_approved", None, note)
    return read(store, order_id)


def request_cancel(store, order_id: int, owner_note: str) -> dict:
    store.require_permission("company:manage")
    _id(order_id, "주문")
    note = _text(owner_note, "취소 요청 사유", 200)
    if len(note) < 5: raise ValueError("관리자 사유 5자 이상")
    with store._connect() as con:
        con.execute("BEGIN IMMEDIATE"); initialize(con)
        if stopped(con): raise PermissionError("비상정지 중 취소 요청 금지")
        _verify(con, order_id)
        _append(con, order_id, "cancel_requested", None, note)
    return read(store, order_id)


def link_refund(store, order_id: int, refund_event_id: int, owner_note: str) -> dict:
    store.require_permission("company:manage")
    _id(order_id, "주문"); _id(refund_event_id, "환불 이벤트")
    note = _text(owner_note, "환불 증빙 연결 사유", 200)
    if len(note) < 5: raise ValueError("관리자 사유 5자 이상")
    with store._connect() as con:
        con.execute("BEGIN IMMEDIATE"); initialize(con)
        if stopped(con): raise PermissionError("비상정지 중 환불 연결 금지")
        row = _verify(con, order_id)
        if refund_event_id not in row["unlinked_refund_ids"]:
            raise ValueError("해당 주문에 연결할 수 있는 승인·대사 환불 증빙이 아닙니다.")
        _append(con, order_id, "refund_linked", refund_event_id, note)
    return read(store, order_id)


def read(store, order_id: int) -> dict:
    store.require_permission("company:manage")
    _id(order_id, "주문")
    with store._connect() as con:
        initialize(con)
        row = _verify(con, order_id)
    document = documents.read(store, int(row["product_document_id"]))
    if document["sha256"] != row["document_sha256"]:
        raise ValueError("로컬 승인 상품 문서의 실제 파일 SHA256 불일치")
    return dict(id=order_id, **row,
                local_package_approved=row["approved"],
                local_cancel_requested=row["cancel_requested"],
                actual_order_provider_verified=False,
                independent_bank_verified=False,
                actual_revenue_confirmed=False,
                actual_customer_delivery_sent=False,
                actual_refund_executed=False)


def list_orders(store, limit: int = 50) -> list[dict]:
    store.require_permission("company:manage")
    if type(limit) is not int or not 1 <= limit <= 200:
        raise ValueError("로컬 주문 조회 범위 1~200건")
    with store._connect() as con:
        initialize(con)
        ids = [int(row[0]) for row in con.execute(
            "SELECT id FROM aiwack_local_order_intakes ORDER BY id DESC LIMIT ?",
            (limit,)).fetchall()]
    return [read(store, order_id) for order_id in ids]
