"""기존 고객지원 업무와 로컬 주문의 증빙형 연결. 고객 발송/환불 실행 없음."""
from __future__ import annotations

from desktop import company_customer_cases as cases
from desktop import company_local_order_fulfillment as orders
from desktop.stage87_90_management import stopped


def initialize(con):
    cases.initialize(con)
    orders.initialize(con)
    con.execute("""CREATE TABLE IF NOT EXISTS aiwack_local_order_support_links(
       id INTEGER PRIMARY KEY AUTOINCREMENT,
       order_id INTEGER NOT NULL REFERENCES aiwack_local_order_intakes(id),
       case_id INTEGER NOT NULL UNIQUE REFERENCES aiwack_customer_cases(id),
       created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
       UNIQUE(order_id,case_id))""")
    for op in ("UPDATE", "DELETE"):
        con.execute(f"""CREATE TRIGGER IF NOT EXISTS aiwack_order_support_no_{op.lower()}
           BEFORE {op} ON aiwack_local_order_support_links BEGIN
           SELECT RAISE(ABORT,'주문 고객지원 연결 원본 수정 금지'); END""")


def link_case(store, order_id: int, case_id: int) -> dict:
    store.require_permission("company:manage")
    order = orders.read(store, order_id)
    case = cases.read(store, case_id)
    if (case["customer_alias"] != order["customer_alias"]
            or case["catalog_item_id"] != order["catalog_item_id"]):
        raise ValueError("고객 별칭·상품 번호가 주문과 고객지원 업무에서 다릅니다.")
    with store._connect() as con:
        con.execute("BEGIN IMMEDIATE")
        initialize(con)
        if stopped(con):
            raise PermissionError("비상정지 중 고객지원 연결 금지")
        fresh = orders._verify(con, order_id)
        row = con.execute("""SELECT customer_alias,catalog_item_id FROM aiwack_customer_cases
                              WHERE id=?""", (case_id,)).fetchone()
        if not row or tuple(row) != (fresh["customer_alias"], fresh["catalog_item_id"]):
            raise ValueError("주문 또는 고객지원 원본이 변경됐습니다.")
        con.execute("""INSERT INTO aiwack_local_order_support_links(order_id,case_id)
                       VALUES(?,?)""", (order_id, case_id))
    return read(store, order_id)


def read(store, order_id: int) -> dict:
    store.require_permission("company:manage")
    order = orders.read(store, order_id)
    with store._connect() as con:
        initialize(con)
        ids = [int(row[0]) for row in con.execute(
            "SELECT case_id FROM aiwack_local_order_support_links WHERE order_id=? ORDER BY id",
            (order_id,)).fetchall()]
    linked = [cases.read(store, case_id) for case_id in ids]
    if any(case["customer_alias"] != order["customer_alias"]
           or case["catalog_item_id"] != order["catalog_item_id"] for case in linked):
        raise ValueError("주문과 고객지원 원본 연결 무결성 오류")
    return dict(order=order, customer_cases=linked,
                customer_message_sent=False, actual_refund_executed=False)
