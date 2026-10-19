"""Stages91-93 local safety: review-only expense approvals, non-executable input guard.
No real spending or remote service connections are available from this module.
"""
import re
import sqlite3
from desktop.local_commerce_common import ident, key, note, amount, digest, triggers

BAD_TOKENS=('ignore previous instructions','ignore all instructions','system prompt',
            'disable safety','reveal secret','send to http','curl ','wget ',
            'powershell ','subprocess','os.system','exec(','eval(','rm -rf',
            '지시 무시','보안 해제','관리자 암호','비밀번호 유출')

def guard_untrusted(value):
    """Defence in depth: untrusted external inputs are never dispatched as commands.
    Block known coercive text; human review still required for all other content.
    """
    note(value,maximum=240)
    if any(t in value.casefold() for t in BAD_TOKENS):
        raise ValueError('untrusted instruction text rejected')
    return value

def initialize(con):
    con.execute('''CREATE TABLE IF NOT EXISTS local_spend_review_requests (
      id INTEGER PRIMARY KEY AUTOINCREMENT, review_key TEXT NOT NULL UNIQUE,
      business_id INTEGER NOT NULL REFERENCES managed_businesses(id),
      amount_krw INTEGER NOT NULL CHECK(amount_krw BETWEEN 0 AND 1000000000000000),
      budget_snapshot_krw INTEGER NOT NULL,
      verdict TEXT NOT NULL CHECK(verdict IN ('REVIEW_ONLY_WITHIN_DECLARED_BUDGET','REJECTED_OVER_DECLARED_BUDGET')),
      rationale TEXT NOT NULL, previous_digest TEXT NOT NULL,digest TEXT NOT NULL,
      created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)''')
    triggers(con,('local_spend_review_requests',))

def spend_history(con):
    con.row_factory=sqlite3.Row
    prev='';out=[]
    for row in con.execute('SELECT * FROM local_spend_review_requests ORDER BY id'):
        r=dict(row)
        exp=digest([r['review_key'],r['business_id'],r['amount_krw'],r['budget_snapshot_krw'],r['verdict'],r['rationale'],prev])
        if r['digest']!=exp or r['previous_digest']!=prev:
            raise ValueError('spend review audit hash mismatch')
        out.append({**r,'real_spend_approved':False,'real_payment_executed':False})
        prev=r['digest']
    return out

def review_spending(con,review_key,business_id,amount_krw,rationale):
    key(review_key);ident(business_id);amount(amount_krw);guard_untrusted(rationale)
    row=con.execute('SELECT budget_krw FROM managed_businesses WHERE id=?',(business_id,)).fetchone()
    if not row:raise ValueError('unknown business')
    budget=row[0]
    verdict=('REVIEW_ONLY_WITHIN_DECLARED_BUDGET' if amount_krw<=budget
             else 'REJECTED_OVER_DECLARED_BUDGET')
    old=spend_history(con)
    for r in old:
        if r['review_key']==review_key:
            if (r['business_id'],r['amount_krw'],r['budget_snapshot_krw'],r['rationale'])!=(business_id,amount_krw,budget,rationale):
                raise ValueError('spend review key collision or changed budget')
            return {**r,'duplicate':True}
    prev=old[-1]['digest'] if old else ''
    h=digest([review_key,business_id,amount_krw,budget,verdict,rationale,prev])
    cur=con.execute('''INSERT INTO local_spend_review_requests
      (review_key,business_id,amount_krw,budget_snapshot_krw,verdict,rationale,previous_digest,digest)
      VALUES(?,?,?,?,?,?,?,?)''',(review_key,business_id,amount_krw,budget,verdict,rationale,prev,h))
    return {**next(r for r in spend_history(con) if r['id']==cur.lastrowid),'duplicate':False}
