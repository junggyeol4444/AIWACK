"""Stage76: internal mock delivery planning only. No external dispatch or fulfillment."""
import hashlib
import json

STATES = ('PLANNED_SIMULATED', 'CANCELLED_SIMULATED')

def initialize(con):
    con.execute("""CREATE TABLE IF NOT EXISTS local_mock_delivery_events (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      simulated_order_id INTEGER NOT NULL REFERENCES local_simulated_orders(id),
      delivery_key TEXT NOT NULL UNIQUE,
      payload_digest TEXT NOT NULL,
      state TEXT NOT NULL CHECK(state IN ('PLANNED_SIMULATED','CANCELLED_SIMULATED')),
      created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)""")
    for operation in ('UPDATE','DELETE'):
        con.execute(f"""CREATE TRIGGER IF NOT EXISTS mock_delivery_no_{operation.lower()}
          BEFORE {operation} ON local_mock_delivery_events BEGIN
          SELECT RAISE(ABORT, 'append-only simulated delivery'); END""")

def record(con, order_id, delivery_key, state, note):
    if type(order_id) is not int or order_id < 1:
        raise ValueError('invalid simulated order id')
    if not isinstance(delivery_key,str) or not (8 <= len(delivery_key) <= 64) or not all(c.isascii() and (c.isalnum() or c in '_-') for c in delivery_key):
        raise ValueError('invalid local idempotency key')
    if state not in STATES:
        raise ValueError('only simulated delivery states allowed')
    if not isinstance(note,str) or len(note) > 300 or any(ord(c) < 32 and c not in '\n\t' for c in note):
        raise ValueError('invalid local note')
    digest=hashlib.sha256(json.dumps([order_id,state,note],ensure_ascii=False,separators=(',',':')).encode()).hexdigest()
    old=con.execute('SELECT id,simulated_order_id,payload_digest,state FROM local_mock_delivery_events WHERE delivery_key=?',(delivery_key,)).fetchone()
    if old:
        if old[1] != order_id or old[2] != digest:
            raise ValueError('conflicting simulated delivery key')
        return {'id':old[0],'state':old[3],'duplicate':True,'real_delivery':False}
    if not con.execute('SELECT 1 FROM local_simulated_orders WHERE id=?',(order_id,)).fetchone():
        raise ValueError('unknown simulated order')
    cur=con.execute('INSERT INTO local_mock_delivery_events(simulated_order_id,delivery_key,payload_digest,state) VALUES(?,?,?,?)',(order_id,delivery_key,digest,state))
    return {'id':cur.lastrowid,'state':state,'duplicate':False,'real_delivery':False}

def history(con, order_id):
    return [dict(zip(('id','delivery_key','state','created_at'),r)) for r in con.execute('SELECT id,delivery_key,state,created_at FROM local_mock_delivery_events WHERE simulated_order_id=? ORDER BY id',(order_id,))]
