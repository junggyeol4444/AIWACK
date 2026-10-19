"""Stage78. Entirely synthetic, local support tickets; no customers or messages."""
import sqlite3
from desktop.local_commerce_common import digest, ident, key, note, ALIAS, triggers
from desktop.offline_order_simulations import _base as order_base

ACTIONS = {'opened':'OPEN_SIMULATED','reviewed':'REVIEW_SIMULATED','resolved':'RESOLVED_SIMULATED','closed':'CLOSED_SIMULATED'}
NEXT = {None: ('opened',),'OPEN_SIMULATED':('reviewed','closed'),'REVIEW_SIMULATED':('resolved','closed'),'RESOLVED_SIMULATED':('closed',),'CLOSED_SIMULATED':()}
CATEGORIES = ('QUESTION_SIMULATED','DELIVERY_SIMULATED','REFUND_SIMULATED')

def initialize(con):
    con.execute("""CREATE TABLE IF NOT EXISTS local_support_tickets (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      ticket_key TEXT NOT NULL UNIQUE,
      synthetic_alias TEXT NOT NULL,
      simulated_order_id INTEGER NOT NULL REFERENCES local_simulated_orders(id),
      category TEXT NOT NULL CHECK(category IN ('QUESTION_SIMULATED','DELIVERY_SIMULATED','REFUND_SIMULATED')),
      summary TEXT NOT NULL,
      origin_digest TEXT NOT NULL,
      base_digest TEXT NOT NULL,
      created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)""")
    con.execute("""CREATE TABLE IF NOT EXISTS local_support_ticket_events (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      ticket_id INTEGER NOT NULL REFERENCES local_support_tickets(id),
      event_key TEXT NOT NULL UNIQUE,
      revision INTEGER NOT NULL,
      action TEXT NOT NULL CHECK(action IN ('opened','reviewed','resolved','closed')),
      comment TEXT NOT NULL,
      previous_digest TEXT NOT NULL,
      digest TEXT NOT NULL,
      created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
      UNIQUE(ticket_id,revision))""")
    triggers(con, ('local_support_tickets','local_support_ticket_events'))

def _ticket(con, ticket_id):
    ident(ticket_id)
    con.row_factory=sqlite3.Row
    row=con.execute('SELECT * FROM local_support_tickets WHERE id=?',(ticket_id,)).fetchone()
    if row is None: raise ValueError('unknown synthetic ticket')
    base=dict(row)
    order=order_base(con,base['simulated_order_id'])
    if base['origin_digest']!=digest(order) or not ALIAS.fullmatch(base['synthetic_alias']) or base['category'] not in CATEGORIES:
        raise ValueError('synthetic support source mismatch')
    note(base['summary'])
    expected=digest([base['ticket_key'],base['synthetic_alias'],base['simulated_order_id'],base['category'],base['summary'],base['origin_digest']])
    if base['base_digest']!=expected: raise ValueError('support immutable base checksum mismatch')
    return base

def history(con,ticket_id):
    base=_ticket(con,ticket_id)
    events=con.execute('SELECT * FROM local_support_ticket_events WHERE ticket_id=? ORDER BY revision',(ticket_id,)).fetchall()
    if not events: raise ValueError('missing support audit')
    prev='';state=None;results=[]
    for revision,row in enumerate(events,1):
        e=dict(row)
        if e['revision']!=revision or e['previous_digest']!=prev or e['action'] not in NEXT[state]:
            raise ValueError('support history discontinuity')
        key(e['event_key']); note(e['comment'])
        data=[base['base_digest'],base['ticket_key'],revision,e['event_key'],e['action'],e['comment'],prev]
        if digest(data)!=e['digest']: raise ValueError('support audit checksum mismatch')
        state=ACTIONS[e['action']];prev=e['digest']
        results.append({'revision':revision,'state':state,'action':e['action'],'digest':prev,'comment':e['comment']})
    return results

def get(con,ticket_id):
    base=_ticket(con,ticket_id)
    chain=history(con,ticket_id)
    return {**base,'state':chain[-1]['state'],'latest_digest':chain[-1]['digest'],'simulation_only':True,'real_customer':False,'message_sent':False}

def _append(con,base,event_key,action,comment):
    existing=history(con,base['id']) if action!='opened' else []
    prev=existing[-1]['digest'] if existing else ''
    revision=len(existing)+1
    hashed=digest([base['base_digest'],base['ticket_key'],revision,event_key,action,comment,prev])
    con.execute('INSERT INTO local_support_ticket_events(ticket_id,event_key,revision,action,comment,previous_digest,digest) VALUES(?,?,?,?,?,?,?)',(base['id'],event_key,revision,action,comment,prev,hashed))

def create(con,order_id,ticket_key,synthetic_alias,category,summary):
    ident(order_id);key(ticket_key)
    if type(synthetic_alias) is not str or not ALIAS.fullmatch(synthetic_alias): raise ValueError('synthetic alias only; no real identity')
    if category not in CATEGORIES: raise ValueError('synthetic categories only')
    note(summary)
    order=order_base(con,order_id)
    exists=con.execute('SELECT id FROM local_support_tickets WHERE ticket_key=?',(ticket_key,)).fetchone()
    if exists:
        old=get(con,exists[0])
        if (old['simulated_order_id'],old['synthetic_alias'],old['category'],old['summary']) != (order_id,synthetic_alias,category,summary):
            raise ValueError('ticket key conflict')
        return {**old,'duplicate':True}
    cur=con.execute('INSERT INTO local_support_tickets(ticket_key,synthetic_alias,simulated_order_id,category,summary,origin_digest,base_digest) VALUES(?,?,?,?,?,?,?)',(ticket_key,synthetic_alias,order_id,category,summary,digest(order),digest([ticket_key,synthetic_alias,order_id,category,summary,digest(order)])))
    base=_ticket(con,cur.lastrowid)
    _append(con,base,ticket_key,'opened','Synthetic ticket opened')
    return {**get(con,cur.lastrowid),'duplicate':False}

def transition(con,ticket_id,event_key,action,comment):
    ident(ticket_id);key(event_key);note(comment)
    if action not in ('reviewed','resolved','closed'): raise ValueError('not an allowed simulated action')
    base=_ticket(con,ticket_id)
    exists=con.execute('SELECT ticket_id,action,comment FROM local_support_ticket_events WHERE event_key=?',(event_key,)).fetchone()
    if exists:
        if tuple(exists)!=(ticket_id,action,comment): raise ValueError('support event key conflict')
        return {**get(con,ticket_id),'duplicate':True}
    old=get(con,ticket_id)
    if action not in NEXT[old['state']]: raise ValueError('invalid support state transition')
    _append(con,base,event_key,action,comment)
    return {**get(con,ticket_id),'duplicate':False}
