"""Stage75: local synthetic event replay guard. Never processes provider webhooks."""
import hashlib
import json


def initialize(con):
    con.execute('''CREATE TABLE IF NOT EXISTS local_synthetic_payment_events (
      id INTEGER PRIMARY KEY, simulated_order_id INTEGER NOT NULL REFERENCES local_simulated_orders(id),
      event_key TEXT NOT NULL UNIQUE, fixture_audit_id INTEGER NOT NULL REFERENCES local_payment_fixture_audit(id),
      payload_digest TEXT NOT NULL, verdict TEXT NOT NULL,
      created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)''')
    for op in ('UPDATE', 'DELETE'):
        con.execute(f'''CREATE TRIGGER IF NOT EXISTS synthetic_event_no_{op.lower()}
          BEFORE {op} ON local_synthetic_payment_events BEGIN SELECT RAISE(ABORT,'append only'); END''')


def record(con, order_id, fixture_audit_id, event_key, payload):
    if type(order_id) is not int or order_id <= 0 or type(fixture_audit_id) is not int or fixture_audit_id <= 0:
        raise ValueError('invalid local reference')
    if not isinstance(event_key, str) or not 8 <= len(event_key) <= 64 or not all(c.isascii() and (c.isalnum() or c in '_-') for c in event_key):
        raise ValueError('invalid event key')
    if not isinstance(payload, dict) or set(payload) != {'kind', 'fixture_reference'} or payload['kind'] != 'LOCAL_SYNTHETIC_EVENT' or not isinstance(payload['fixture_reference'], str):
        raise ValueError('invalid synthetic event')
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    old = con.execute('SELECT id,simulated_order_id,fixture_audit_id,payload_digest,verdict FROM local_synthetic_payment_events WHERE event_key=?', (event_key,)).fetchone()
    if old:
        if (old[1], old[2], old[3]) != (order_id, fixture_audit_id, digest):
            raise ValueError('conflicting synthetic event replay')
        return {'id': old[0], 'verdict': old[4], 'duplicate': True, 'real_payment_verified': False}
    fixture = con.execute('SELECT simulated_order_id,reference FROM local_payment_fixture_audit WHERE id=?', (fixture_audit_id,)).fetchone()
    if fixture is None or fixture[0] != order_id or fixture[1] != payload['fixture_reference']:
        raise ValueError('fixture does not match order')
    cur = con.execute('INSERT INTO local_synthetic_payment_events(simulated_order_id,event_key,fixture_audit_id,payload_digest,verdict) VALUES(?,?,?,?,?)', (order_id,event_key,fixture_audit_id,digest,'IGNORED_SYNTHETIC_NO_PAYMENT'))
    return {'id': cur.lastrowid, 'verdict': 'IGNORED_SYNTHETIC_NO_PAYMENT', 'duplicate': False, 'real_payment_verified': False}
