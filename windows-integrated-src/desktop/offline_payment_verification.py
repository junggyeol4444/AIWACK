"""Offline synthetic payment fixture boundary; never real verification."""
import hashlib, json

def initialize(con):
    con.execute("""CREATE TABLE IF NOT EXISTS local_payment_fixture_audit(id INTEGER PRIMARY KEY, simulated_order_id INTEGER NOT NULL REFERENCES local_simulated_orders(id), reference TEXT NOT NULL, digest TEXT NOT NULL, verdict TEXT NOT NULL, created_at TEXT DEFAULT CURRENT_TIMESTAMP, UNIQUE(simulated_order_id,reference))""")
    for op in ('UPDATE','DELETE'):
        con.execute(f"CREATE TRIGGER IF NOT EXISTS payment_fixture_no_{op.lower()} BEFORE {op} ON local_payment_fixture_audit BEGIN SELECT RAISE(ABORT,'append only'); END")

def check(con, order_id, reference, fixture):
    if type(order_id) is not int or order_id < 1: raise ValueError('invalid order id')
    if not isinstance(reference,str) or not 8 <= len(reference) <= 48 or not all(c.isascii() and (c.isalnum() or c in '_-') for c in reference): raise ValueError('invalid fixture reference')
    if not isinstance(fixture,dict) or set(fixture) != {'kind','currency','amount_minor'} or fixture['kind'] != 'LOCAL_TEST_ONLY' or type(fixture['amount_minor']) is not int or fixture['amount_minor'] < 0 or fixture['currency'] not in ('KRW','JPY','USD','EUR'): raise ValueError('invalid fixture')
    row=con.execute('SELECT currency,total_minor FROM local_simulated_orders WHERE id=?',(order_id,)).fetchone()
    if row is None: raise ValueError('unknown simulated order')
    digest=hashlib.sha256(json.dumps(fixture,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    verdict='UNVERIFIED_NO_PROVIDER' if (row[0],row[1]) == (fixture['currency'],fixture['amount_minor']) else 'REJECTED_SYNTHETIC_MISMATCH'
    old=con.execute('SELECT id,digest,verdict FROM local_payment_fixture_audit WHERE simulated_order_id=? AND reference=?',(order_id,reference)).fetchone()
    if old:
        if old[1] != digest: raise ValueError('conflicting reference')
        return {'id':old[0],'verdict':old[2],'real_payment_verified':False}
    cur=con.execute('INSERT INTO local_payment_fixture_audit(simulated_order_id,reference,digest,verdict) VALUES(?,?,?,?)',(order_id,reference,digest,verdict))
    return {'id':cur.lastrowid,'verdict':verdict,'real_payment_verified':False}
