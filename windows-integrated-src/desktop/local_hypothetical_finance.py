"""Stage79. Hypothetical financial assumptions only, NEVER sales or settlement."""
from desktop.local_commerce_common import digest, ident, key, note, amount, CURRENCIES, triggers
from desktop.offline_order_simulations import _base as order_base

KINDS = ('ASSUMED_REVENUE','ASSUMED_EXPENSE','ASSUMED_REFUND','ASSUMED_SETTLEMENT_REFERENCE')

def initialize(con):
    con.execute("""CREATE TABLE IF NOT EXISTS local_hypothetical_finance (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      entry_key TEXT NOT NULL UNIQUE,
      business_id INTEGER NOT NULL REFERENCES managed_businesses(id),
      simulated_order_id INTEGER REFERENCES local_simulated_orders(id),
      kind TEXT NOT NULL CHECK(kind IN ('ASSUMED_REVENUE','ASSUMED_EXPENSE','ASSUMED_REFUND','ASSUMED_SETTLEMENT_REFERENCE')),
      currency TEXT NOT NULL CHECK(currency IN ('KRW','JPY','USD','EUR')),
      amount_minor INTEGER NOT NULL CHECK(amount_minor BETWEEN 0 AND 1000000000000000),
      note TEXT NOT NULL,
      previous_digest TEXT NOT NULL,
      digest TEXT NOT NULL,
      created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)""")
    triggers(con, ('local_hypothetical_finance',))

def _row_payload(row,prev):
    return [row['entry_key'],row['business_id'],row['simulated_order_id'],row['kind'],row['currency'],row['amount_minor'],row['note'],prev]

def history(con):
    con.row_factory=__import__('sqlite3').Row
    prev='';out=[]
    for r in con.execute('SELECT * FROM local_hypothetical_finance ORDER BY id'):
        row=dict(r)
        if row['previous_digest']!=prev or row['digest']!=digest(_row_payload(row,prev)):
            raise ValueError('hypothetical ledger hash chain mismatch')
        key(row['entry_key']);note(row['note']);amount(row['amount_minor'])
        if row['kind'] not in KINDS or row['currency'] not in CURRENCIES: raise ValueError('ledger enum mismatch')
        prev=row['digest'];out.append({**row,'verified_revenue':False,'verified_settlement':False,'real_spend':False,'simulation_only':True})
    return out

def _business_for_order(con,order_id):
    row=con.execute("""SELECT cat.business_id FROM local_simulated_orders o
      JOIN local_unpublished_listings l ON o.listing_id=l.id
      JOIN local_catalog_items cat ON l.catalog_item_id=cat.id WHERE o.id=?""",(order_id,)).fetchone()
    if row is None: raise ValueError('order has no business lineage')
    return row[0]

def record(con,business_id,entry_key,kind,currency,amount_minor,note_text,order_id=None):
    ident(business_id);key(entry_key);note(note_text);amount(amount_minor)
    if kind not in KINDS or currency not in CURRENCIES: raise ValueError('invalid hypothetical ledger category')
    if not con.execute('SELECT 1 FROM managed_businesses WHERE id=?',(business_id,)).fetchone(): raise ValueError('unknown business')
    if order_id is not None:
        ident(order_id);order=order_base(con,order_id)
        if _business_for_order(con,order_id)!=business_id or currency!=order['currency']:
            raise ValueError('order business or currency mismatch')
        if kind in ('ASSUMED_REVENUE','ASSUMED_REFUND','ASSUMED_SETTLEMENT_REFERENCE') and amount_minor>order['total_minor']:
            raise ValueError('amount exceeds simulated order assumption')
    elif kind in ('ASSUMED_REVENUE','ASSUMED_REFUND','ASSUMED_SETTLEMENT_REFERENCE'):
        raise ValueError('synthetic order required for assumed revenue/refund/settlement')
    existing=history(con)
    for row in existing:
        if row['entry_key']==entry_key:
            if (row['business_id'],row['simulated_order_id'],row['kind'],row['currency'],row['amount_minor'],row['note']) != (business_id,order_id,kind,currency,amount_minor,note_text):
                raise ValueError('ledger key conflict')
            return {**row,'duplicate':True}
    # A synthetic order may not be overcounted by issuing multiple hypothetical
    # revenue/refund/settlement entries with different local keys.
    if order_id is not None and kind != 'ASSUMED_EXPENSE':
        prior_total = sum(x['amount_minor'] for x in existing
                          if x['simulated_order_id'] == order_id and x['kind'] == kind)
        if prior_total + amount_minor > order['total_minor']:
            raise ValueError('hypothetical order category total exceeds original assumption')
    prev=existing[-1]['digest'] if existing else ''
    payload=[entry_key,business_id,order_id,kind,currency,amount_minor,note_text,prev]
    hash_value=digest(payload)
    cur=con.execute("""INSERT INTO local_hypothetical_finance(entry_key,business_id,simulated_order_id,kind,currency,amount_minor,note,previous_digest,digest)
        VALUES(?,?,?,?,?,?,?,?,?)""",(entry_key,business_id,order_id,kind,currency,amount_minor,note_text,prev,hash_value))
    return {**[x for x in history(con) if x['id']==cur.lastrowid][0],'duplicate':False}
