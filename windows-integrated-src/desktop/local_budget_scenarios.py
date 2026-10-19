"""Stage80. Local business KRW-only hypothetical P&L and saved snapshots.
This is NOT accounting; non-KRW currencies are never silently converted.
"""
from desktop.local_commerce_common import digest, ident, key, triggers
from desktop.local_hypothetical_finance import history as ledger_history

KIND_SIGN = {'ASSUMED_REVENUE':1,'ASSUMED_EXPENSE':-1,'ASSUMED_REFUND':-1,'ASSUMED_SETTLEMENT_REFERENCE':0}

def initialize(con):
    con.execute("""CREATE TABLE IF NOT EXISTS local_budget_snapshots (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      snapshot_key TEXT NOT NULL UNIQUE,
      source_ledger_digest TEXT NOT NULL,
      snapshot_json TEXT NOT NULL,
      previous_digest TEXT NOT NULL,
      digest TEXT NOT NULL,
      created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)""")
    triggers(con, ('local_budget_snapshots',))

def calculate(con):
    import json
    rows=ledger_history(con)
    businesses=con.execute('SELECT id,name,budget_krw FROM managed_businesses ORDER BY id').fetchall()
    result=[]
    for business_id,name,budget in businesses:
        totals={'ASSUMED_REVENUE':0,'ASSUMED_EXPENSE':0,'ASSUMED_REFUND':0,'ASSUMED_SETTLEMENT_REFERENCE':0}
        foreign={}
        for r in rows:
            if r['business_id']!=business_id:continue
            if r['currency']=='KRW':totals[r['kind']]+=r['amount_minor']
            else:
                foreign.setdefault(r['currency'],{'entry_count':0,'sum_minor_not_converted':0})
                foreign[r['currency']]['entry_count']+=1
                foreign[r['currency']]['sum_minor_not_converted']+=r['amount_minor']
        net=totals['ASSUMED_REVENUE']-totals['ASSUMED_EXPENSE']-totals['ASSUMED_REFUND']
        result.append({'business_id':business_id,'business_name':name,'budget_krw':budget,
                       'assumed_revenue_krw':totals['ASSUMED_REVENUE'],
                       'assumed_expenses_krw':totals['ASSUMED_EXPENSE'],
                       'assumed_refunds_krw':totals['ASSUMED_REFUND'],
                       'assumed_settlement_reference_krw_not_extra_revenue':totals['ASSUMED_SETTLEMENT_REFERENCE'],
                       'assumed_net_krw':net,'hypothetical_budget_remaining_krw':budget-totals['ASSUMED_EXPENSE'],
                       'non_krw_excluded':foreign})
    return {'businesses':result,'total_assumed_net_krw':sum(x['assumed_net_krw'] for x in result),
            'total_budget_krw':sum(x['budget_krw'] for x in result),
            'total_assumed_expenses_krw':sum(x['assumed_expenses_krw'] for x in result),
            'includes_real_transactions':False,'includes_verified_revenue':False,
            'currency':'KRW','foreign_currency_conversion':'FORBIDDEN_UNVERIFIED',
            'accounting_compliant':False,'simulated_only':True}

def snapshots(con):
    import json
    prev='';out=[]
    for row in con.execute('SELECT * FROM local_budget_snapshots ORDER BY id'):
        row=dict(zip(('id','snapshot_key','source_ledger_digest','snapshot_json','previous_digest','digest','created_at'),row))
        if row['previous_digest']!=prev or row['digest']!=digest([row['snapshot_key'],row['source_ledger_digest'],row['snapshot_json'],prev]):
            raise ValueError('budget snapshot hash chain mismatch')
        obj=json.loads(row['snapshot_json'])
        if obj.get('includes_real_transactions') is not False or obj.get('currency')!='KRW':
            raise ValueError('budget is not safe synthetic snapshot')
        out.append({**row,'report':obj})
        prev=row['digest']
    return out

def save(con,snapshot_key):
    import json
    key(snapshot_key)
    report=calculate(con)
    rows=ledger_history(con)
    source=rows[-1]['digest'] if rows else ''
    old=snapshots(con)
    payload=json.dumps(report,ensure_ascii=False,sort_keys=True,separators=(',',':'))
    for s in old:
        if s['snapshot_key']==snapshot_key:
            if s['source_ledger_digest']!=source or s['snapshot_json']!=payload:raise ValueError('snapshot key conflict')
            return {**s,'duplicate':True}
    prev=old[-1]['digest'] if old else ''
    h=digest([snapshot_key,source,payload,prev])
    cur=con.execute('INSERT INTO local_budget_snapshots(snapshot_key,source_ledger_digest,snapshot_json,previous_digest,digest) VALUES(?,?,?,?,?)',(snapshot_key,source,payload,prev,h))
    return {**[x for x in snapshots(con) if x['id']==cur.lastrowid][0],'duplicate':False}
