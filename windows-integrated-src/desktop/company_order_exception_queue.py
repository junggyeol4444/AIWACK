"""주문 예외 → 고객지원부 실제 업무 연결과 관리자 후속 판단 (로컬 전용).

외부 환불/고객 연락/매출 확정은 수행하지 않는다. 기존 주문과 고객
원본을 삭제·수정하지 않고, 별도 감사 테이블에 사실을 추가한다.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3

from desktop import company_local_order_fulfillment as orders
from desktop import company_order_support as support
from desktop import company_customer_cases as cases
from desktop.stage87_90_management import stopped

KINDS = {
    "unlinked_refund": "승인 환불 증빙의 주문 연결 누락",
    "cancel_pending": "주문 내부 취소 요청 후 확인 필요",
    "approved_delivery_missing": "승인 주문의 로컬 상품 준비 미완료",
}


def _sha(value):
    return hashlib.sha256(json.dumps(
        value, ensure_ascii=False, sort_keys=True,
        separators=(",", ":")).encode("utf-8")).hexdigest()


def initialize(con):
    support.initialize(con)
    con.execute("""CREATE TABLE IF NOT EXISTS aiwack_order_exception_escalations(
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      order_id INTEGER NOT NULL REFERENCES aiwack_local_order_intakes(id),
      kind TEXT NOT NULL CHECK(kind IN
        ('unlinked_refund','cancel_pending','approved_delivery_missing')),
      case_id INTEGER NOT NULL UNIQUE REFERENCES aiwack_customer_cases(id),
      task_id INTEGER NOT NULL UNIQUE REFERENCES company_tasks(id),
      source_json TEXT NOT NULL,
      source_sha256 TEXT NOT NULL CHECK(length(source_sha256)=64),
      owner_note TEXT NOT NULL CHECK(length(owner_note) BETWEEN 5 AND 200),
      created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
      UNIQUE(order_id,kind)
    )""")
    con.execute("""CREATE TABLE IF NOT EXISTS aiwack_order_exception_reviews(
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      escalation_id INTEGER NOT NULL REFERENCES aiwack_order_exception_escalations(id),
      decision TEXT NOT NULL CHECK(decision IN
        ('followup_required','internal_case_closed')),
      case_state TEXT NOT NULL,
      current_order_sha256 TEXT NOT NULL CHECK(length(current_order_sha256)=64),
      previous_sha256 TEXT NOT NULL,
      event_sha256 TEXT NOT NULL CHECK(length(event_sha256)=64),
      owner_note TEXT NOT NULL CHECK(length(owner_note) BETWEEN 5 AND 200),
      created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    )""")
    for table in ("aiwack_order_exception_escalations", "aiwack_order_exception_reviews"):
        for op in ("UPDATE", "DELETE"):
            con.execute(f"""CREATE TRIGGER IF NOT EXISTS {table}_no_{op.lower()}
              BEFORE {op} ON {table} BEGIN
              SELECT RAISE(ABORT,'주문 예외 감사 원본 변경 금지'); END""")


def _source(con, order_id):
    row = orders._verify(con, order_id)
    packet = con.execute(
        "SELECT id FROM aiwack_local_order_delivery_packets WHERE order_id=?",
        (order_id,)).fetchone()
    payload = {
        "order_id": order_id,
        "order_ref": row["order_ref"],
        "payment_event_id": row["payment_event_id"],
        "document_sha256": row["document_sha256"],
        "refund_ids": row["unlinked_refund_ids"],
        "cancel_requested": bool(row["cancel_requested"]),
        "package_approved": bool(row["approved"]),
        "packet_id": int(packet[0]) if packet else None,
    }
    detected = []
    if payload["refund_ids"]:
        detected.append("unlinked_refund")
    if payload["cancel_requested"]:
        detected.append("cancel_pending")
    if (payload["package_approved"] and not payload["cancel_requested"]
            and not row["accepted_refund_minor"] and not payload["packet_id"]):
        detected.append("approved_delivery_missing")
    return row, payload, detected


def scan(store, limit=100):
    store.require_permission("company:manage")
    if type(limit) is not int or not 1 <= limit <= 200:
        raise ValueError("주문 예외 조회는 1~200건")
    with store._connect() as con:
        initialize(con)
        ids = [int(r[0]) for r in con.execute(
            "SELECT id FROM aiwack_local_order_intakes ORDER BY id DESC LIMIT ?",
            (limit,)).fetchall()]
    results = []
    for order_id in ids:
        orders.read(store, order_id)
        with store._connect() as con:
            initialize(con)
            _, source, detected = _source(con, order_id)
            recorded = {r[0]: int(r[1]) for r in con.execute(
                "SELECT kind,id FROM aiwack_order_exception_escalations WHERE order_id=?",
                (order_id,)).fetchall()}
        for kind in detected:
            results.append({"order_id": order_id, "order_ref": source["order_ref"],
                            "kind": kind, "reason": KINDS[kind],
                            "escalation_id": recorded.get(kind),
                            "actual_customer_contacted": False})
    return {"inspected_orders": len(ids), "exceptions": results,
            "read_only": True, "full_database_audit": False}


def escalate(store, order_id, kind, case_ref, owner_note):
    store.require_permission("company:manage")
    orders._id(order_id, "주문")
    if kind not in KINDS:
        raise ValueError("지원하지 않는 주문 예외 종류")
    if not isinstance(case_ref, str) or not cases.REF.fullmatch(case_ref):
        raise ValueError("고객지원 고유번호는 영문/숫자 5~80자")
    note = orders._text(owner_note, "관리자 조사 사유", 200)
    if len(note) < 5:
        raise ValueError("관리자 사유 5자 이상")
    orders.read(store, order_id)  # 승인된 실제 상품 문서 원본 SHA 검증
    with store._connect() as con:
        con.execute("BEGIN IMMEDIATE")
        initialize(con)
        if stopped(con):
            raise PermissionError("비상정지 중 고객지원 업무 생성 금지")
        row, source, detected = _source(con, order_id)
        if kind not in detected:
            raise ValueError("현재 원본에서 해당 주문 예외가 발견되지 않았습니다.")
        if con.execute(
                "SELECT 1 FROM aiwack_order_exception_escalations WHERE order_id=? AND kind=?",
                (order_id, kind)).fetchone():
            raise ValueError("이미 해당 주문 예외의 고객지원 업무가 있습니다.")
        if con.execute("SELECT 1 FROM aiwack_customer_cases WHERE case_ref=?",
                       (case_ref,)).fetchone():
            raise ValueError("중복된 고객지원 고유번호")
        department = con.execute(
            "SELECT id FROM company_departments WHERE name='고객지원부'").fetchone()
        if not department:
            raise ValueError("고객지원부가 없어 실제 업무를 연결할 수 없습니다.")
        question = "[주문 " + row["order_ref"] + "] " + KINDS[kind] + ": " + note
        title = ("고객지원 문의 " + case_ref)[:120]
        task_id = int(con.execute(
            "INSERT INTO company_tasks(title,description) VALUES(?,?)",
            (title, question)).lastrowid)
        con.execute("""INSERT INTO company_task_status_events(task_id,old_status,new_status)
                       VALUES(?,NULL,'todo')""", (task_id,))
        con.execute("""INSERT INTO company_task_routing(task_id,department_id)
                       VALUES(?,?)""", (task_id, int(department[0])))
        case_id = int(con.execute("""INSERT INTO aiwack_customer_cases
          (case_ref,customer_alias,question,task_id,catalog_item_id)
          VALUES(?,?,?,?,?)""", (case_ref, row["customer_alias"], question,
                                task_id, row["catalog_item_id"])).lastrowid)
        cases._event(con, case_id, "created", "", "open")
        con.execute("""INSERT INTO aiwack_local_order_support_links(order_id,case_id)
                       VALUES(?,?)""", (order_id, case_id))
        source_json = json.dumps(source, ensure_ascii=False, sort_keys=True,
                                 separators=(",", ":"))
        escalation_id = int(con.execute("""INSERT INTO aiwack_order_exception_escalations
          (order_id,kind,case_id,task_id,source_json,source_sha256,owner_note)
          VALUES(?,?,?,?,?,?,?)""",
          (order_id, kind, case_id, task_id, source_json, _sha(source), note)).lastrowid)
    return read(store, escalation_id)


def _reviews(con, escalation_id):
    rows = con.execute("""SELECT id,decision,case_state,current_order_sha256,
              previous_sha256,event_sha256,owner_note FROM aiwack_order_exception_reviews
              WHERE escalation_id=? ORDER BY id""", (escalation_id,)).fetchall()
    previous = ""
    result = []
    for rid, decision, case_state, current_sha, prior, digest, note in rows:
        payload = dict(escalation_id=escalation_id, decision=decision,
                       case_state=case_state, current_order_sha256=current_sha,
                       previous_sha256=prior, owner_note=note)
        if prior != previous or _sha(payload) != digest:
            raise ValueError("주문 예외 관리자 결정 감사 SHA 체인 불일치")
        result.append(dict(id=int(rid), **payload, event_sha256=digest))
        previous = digest
    return result


def read(store, escalation_id):
    store.require_permission("company:manage")
    orders._id(escalation_id, "주문 예외")
    with store._connect() as con:
        initialize(con)
        row = con.execute("""SELECT order_id,kind,case_id,task_id,source_json,
                 source_sha256,owner_note FROM aiwack_order_exception_escalations
                 WHERE id=?""", (escalation_id,)).fetchone()
        if row is None:
            raise ValueError("주문 예외 기록 없음")
        order_id, kind, case_id, task_id, source_json, digest, note = row
        source = json.loads(source_json)
        if _sha(source) != digest or source["order_id"] != order_id:
            raise ValueError("주문 예외 최초 원본 SHA 불일치")
        link = con.execute("""SELECT c.task_id,l.order_id FROM aiwack_customer_cases c
                 JOIN aiwack_local_order_support_links l ON l.case_id=c.id
                 WHERE c.id=?""", (case_id,)).fetchone()
        if not link or tuple(link) != (task_id, order_id):
            raise ValueError("고객지원 업무·주문 연결 불일치")
        reviews = _reviews(con, escalation_id)
    current = orders.read(store, int(order_id))
    case = cases.read(store, int(case_id))
    return {"id": escalation_id, "order_id": order_id, "kind": kind,
            "case_id": case_id, "task_id": task_id, "source_sha256": digest,
            "owner_note": note, "case_state": case["state"],
            "current_unlinked_refund_ids": current["unlinked_refund_ids"],
            "reviews": reviews, "external_message_sent": False,
            "actual_refund_executed": False}


def review(store, escalation_id, decision, owner_note):
    store.require_permission("company:manage")
    orders._id(escalation_id, "주문 예외")
    if decision not in ("followup_required", "internal_case_closed"):
        raise ValueError("후속 조사 또는 내부 고객지원 종료만 기록할 수 있습니다.")
    note = orders._text(owner_note, "관리자 검토 사유", 200)
    if len(note) < 5:
        raise ValueError("관리자 사유 5자 이상")
    existing = read(store, escalation_id)
    with store._connect() as con:
        con.execute("BEGIN IMMEDIATE")
        initialize(con)
        if stopped(con):
            raise PermissionError("비상정지 중 관리자 검토 금지")
        reviews = _reviews(con, escalation_id)
        if reviews and reviews[-1]["decision"] == "internal_case_closed":
            raise ValueError("이미 내부 고객지원 종료 결정이 기록되었습니다.")
        case_state = con.execute(
            "SELECT state FROM aiwack_customer_cases WHERE id=?",
            (existing["case_id"],)).fetchone()[0]
        if decision == "internal_case_closed" and case_state != "closed":
            raise ValueError("기존 고객지원의 실제 승인 답변 및 내부 종료가 필요합니다.")
        _, source, _ = _source(con, int(existing["order_id"]))
        if (decision == "internal_case_closed" and existing["kind"] == "unlinked_refund"
                and source["refund_ids"]):
            raise ValueError("환불 증빙의 주문 연결 누락이 남아 있습니다.")
        prior = reviews[-1]["event_sha256"] if reviews else ""
        payload = dict(escalation_id=escalation_id, decision=decision,
                       case_state=case_state, current_order_sha256=_sha(source),
                       previous_sha256=prior, owner_note=note)
        con.execute("""INSERT INTO aiwack_order_exception_reviews
           (escalation_id,decision,case_state,current_order_sha256,
            previous_sha256,event_sha256,owner_note)
           VALUES(?,?,?,?,?,?,?)""",
           (escalation_id, decision, case_state, payload["current_order_sha256"],
            prior, _sha(payload), note))
    return read(store, escalation_id)


def history(store, limit=50):
    store.require_permission("company:manage")
    if type(limit) is not int or not 1 <= limit <= 200:
        raise ValueError("주문 예외 이력 조회 1~200건")
    with store._connect() as con:
        initialize(con)
        ids = [int(r[0]) for r in con.execute(
            "SELECT id FROM aiwack_order_exception_escalations ORDER BY id DESC LIMIT ?",
            (limit,)).fetchall()]
    return [read(store, rid) for rid in ids]
