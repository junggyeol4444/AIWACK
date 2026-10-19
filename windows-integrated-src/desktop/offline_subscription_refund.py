"""Stage77 offline-only mock subscription/cancel/refund requests.

No payment/renewal/refund provider, customer, account, or network access.
All amounts are unverified order price assumptions, NEVER transferred money.
"""
from __future__ import annotations

import hashlib
import json
import re
import sqlite3

from desktop.offline_order_simulations import _base as order_base

KEY_RE = re.compile(r'[A-Za-z0-9_-]{8,48}\Z', re.ASCII)
MODES = ('MONTHLY_PLAN_SIMULATED', 'ONE_TIME_PLAN_SIMULATED')
STATES = {
    'plan_created': 'PLANNED_SIMULATED',
    'cancel_requested': 'CANCEL_REQUESTED_SIMULATED',
    'cancel_acknowledged': 'CANCELLED_SIMULATED',
    'refund_requested': 'REFUND_REQUESTED_SIMULATED',
    'refund_declined': 'REFUND_DECLINED_SIMULATED',
}
TRANSITIONS = {
    'PLANNED_SIMULATED': ('cancel_requested', 'refund_requested'),
    'CANCEL_REQUESTED_SIMULATED': ('cancel_acknowledged', 'refund_requested'),
    'CANCELLED_SIMULATED': ('refund_requested',),
    'REFUND_REQUESTED_SIMULATED': ('refund_declined',),
    'REFUND_DECLINED_SIMULATED': (),
}
MAX_NOTE = 240


def _hash(payload) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False,
                                    separators=(',', ':')).encode('utf-8')).hexdigest()


def _key(value):
    if type(value) is not str or not KEY_RE.fullmatch(value) or any(
        x in value.lower() for x in ('token', 'secret', 'password', 'bearer', 'api_key')
    ):
        raise ValueError('로컬 키는 비밀정보가 아닌 영문·숫자·_- 8~48자여야 합니다.')
    return value


def _note(value):
    if (type(value) is not str or len(value) > MAX_NOTE or '\x00' in value or
            any(ord(c) < 32 and c not in ('\n', '\t') for c in value) or
            '://' in value or '@' in value):
        raise ValueError('개인정보·URL·제어문자가 없는 240자 이하 메모만 허용합니다.')
    return value


def _ident(value):
    if type(value) is not int or value < 1:
        raise ValueError('유효한 모의 레코드 ID가 필요합니다.')
    return value


def initialize(con: sqlite3.Connection) -> None:
    con.execute('''CREATE TABLE IF NOT EXISTS local_mock_subscriptions (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      simulated_order_id INTEGER NOT NULL UNIQUE REFERENCES local_simulated_orders(id) ON DELETE RESTRICT,
      plan_key TEXT NOT NULL UNIQUE CHECK(length(plan_key) BETWEEN 8 AND 48),
      mode TEXT NOT NULL CHECK(mode IN ('MONTHLY_PLAN_SIMULATED','ONE_TIME_PLAN_SIMULATED')),
      periods INTEGER NOT NULL CHECK(periods BETWEEN 1 AND 12),
      currency TEXT NOT NULL CHECK(currency IN ('KRW','JPY','USD','EUR')),
      assumed_amount_minor INTEGER NOT NULL CHECK(assumed_amount_minor BETWEEN 0 AND 1000000000000000),
      order_digest TEXT NOT NULL CHECK(length(order_digest)=64),
      created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    )''')
    con.execute('''CREATE TABLE IF NOT EXISTS local_mock_subscription_events (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      subscription_id INTEGER NOT NULL REFERENCES local_mock_subscriptions(id) ON DELETE RESTRICT,
      revision INTEGER NOT NULL CHECK(revision>0),
      event_key TEXT NOT NULL UNIQUE CHECK(length(event_key) BETWEEN 8 AND 48),
      action TEXT NOT NULL CHECK(action IN ('plan_created','cancel_requested','cancel_acknowledged','refund_requested','refund_declined')),
      amount_minor INTEGER NOT NULL CHECK(amount_minor>=0),
      note TEXT NOT NULL CHECK(length(note)<=240),
      previous_digest TEXT NOT NULL,
      digest TEXT NOT NULL CHECK(length(digest)=64),
      created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
      UNIQUE(subscription_id,revision)
    )''')
    con.execute('CREATE INDEX IF NOT EXISTS mock_subscription_events_idx ON local_mock_subscription_events(subscription_id,revision)')
    for table in ('local_mock_subscriptions', 'local_mock_subscription_events'):
        for op in ('UPDATE', 'DELETE'):
            con.execute(f'''CREATE TRIGGER IF NOT EXISTS {table}_no_{op.lower()}
                BEFORE {op} ON {table} BEGIN SELECT RAISE(ABORT,'append-only simulated subscription audit'); END''')


def _base(con, subscription_id):
    _ident(subscription_id)
    con.row_factory = sqlite3.Row
    row = con.execute('SELECT * FROM local_mock_subscriptions WHERE id=?',
                      (subscription_id,)).fetchone()
    if row is None:
        raise ValueError('모의 구독 계획을 찾을 수 없습니다.')
    base = dict(row)
    order = order_base(con, base['simulated_order_id'])
    if (base['order_digest'] != _hash(order) or
            base['currency'] != order['currency'] or
            base['assumed_amount_minor'] != order['total_minor'] or
            base['mode'] not in MODES or
            type(base['periods']) is not int or not 1 <= base['periods'] <= 12 or
            (base['mode'] == 'ONE_TIME_PLAN_SIMULATED' and base['periods'] != 1) or
            not KEY_RE.fullmatch(base['plan_key'])):
        raise ValueError('모의 구독 원본 스냅샷 불일치')
    return base


def history(con, subscription_id):
    base = _base(con, subscription_id)
    rows = con.execute('''SELECT * FROM local_mock_subscription_events
        WHERE subscription_id=? ORDER BY revision''', (subscription_id,)).fetchall()
    if not rows:
        raise ValueError('모의 구독 최초 감사 이력이 없습니다.')
    previous = ''
    current_state = None
    result = []
    for rev, event in enumerate(rows, 1):
        action = event['action']
        if event['revision'] != rev or event['previous_digest'] != previous:
            raise ValueError('모의 구독 감사 체인 불일치')
        if rev == 1:
            if action != 'plan_created' or event['amount_minor'] != 0 or event['note']:
                raise ValueError('모의 구독 최초 감사 이벤트 불일치')
        elif action not in TRANSITIONS.get(current_state, ()):
            raise ValueError('모의 구독 감사 상태 전환 불일치')
        _key(event['event_key'])
        _note(event['note'])
        if (type(event['amount_minor']) is not int or event['amount_minor'] < 0 or
                event['amount_minor'] > base['assumed_amount_minor'] or
                (action != 'refund_requested' and event['amount_minor'] != 0) or
                (action == 'refund_requested' and event['amount_minor'] == 0)):
            raise ValueError('모의 구독 감사 금액 불일치')
        payload = [base['order_digest'], base['plan_key'], rev, event['event_key'], action,
                   event['amount_minor'], event['note'], previous]
        digest = _hash(payload)
        if event['digest'] != digest:
            raise ValueError('모의 구독 감사 해시 불일치')
        current_state = STATES[action]
        result.append(dict(revision=rev, event_key=event['event_key'], action=action,
                           state=current_state, assumed_amount_minor=event['amount_minor'],
                           note=event['note'], digest=digest, previous_digest=previous,
                           created_at=event['created_at'], real_refund=False))
        previous = digest
    return result


def get(con, subscription_id):
    base = _base(con, subscription_id)
    events = history(con, subscription_id)
    return {**base, 'state': events[-1]['state'], 'revision': len(events),
            'latest_digest': events[-1]['digest'], 'simulation_only': True,
            'real_subscription': False, 'renewal_enabled': False,
            'real_cancellation': False, 'refund_issued': False,
            'payment_verified': False, 'customer_contacted': False}


def _append(con, base, rev, key, action, amount, note, prev):
    digest = _hash([base['order_digest'], base['plan_key'], rev, key, action, amount, note, prev])
    con.execute('''INSERT INTO local_mock_subscription_events
       (subscription_id,revision,event_key,action,amount_minor,note,previous_digest,digest)
       VALUES(?,?,?,?,?,?,?,?)''',
       (base['id'], rev, key, action, amount, note, prev, digest))


def create(con, order_id, plan_key, mode, periods):
    _ident(order_id)
    _key(plan_key)
    if mode not in MODES:
        raise ValueError('실제 구독 모드가 아닌 모의 계획만 허용합니다.')
    if type(periods) is not int or not 1 <= periods <= 12 or (mode == MODES[1] and periods != 1):
        raise ValueError('모의 기간은 1~12, 일회성은 1만 허용합니다.')
    order = order_base(con, order_id)
    existing = con.execute('SELECT id FROM local_mock_subscriptions WHERE plan_key=? OR simulated_order_id=?',
                           (plan_key,order_id)).fetchone()
    if existing:
        record = get(con,existing[0])
        if (record['simulated_order_id'] != order_id or record['plan_key'] != plan_key or
                record['mode'] != mode or record['periods'] != periods):
            raise ValueError('모의 계획 키 또는 주문 재사용 충돌')
        return {**record, 'duplicate': True}
    order_digest = _hash(order)
    cur = con.execute('''INSERT INTO local_mock_subscriptions
         (simulated_order_id,plan_key,mode,periods,currency,assumed_amount_minor,order_digest)
         VALUES(?,?,?,?,?,?,?)''',
         (order_id, plan_key, mode, periods, order['currency'], order['total_minor'], order_digest))
    base = _base(con,cur.lastrowid)
    _append(con,base,1,plan_key,'plan_created',0,'','')
    return {**get(con,cur.lastrowid), 'duplicate': False}


def transition(con, subscription_id, event_key, action, note='', amount_minor=0):
    _ident(subscription_id)
    _key(event_key)
    _note(note)
    if action not in STATES or action == 'plan_created':
        raise ValueError('모의 취소/환불 요청 작업만 허용합니다.')
    if type(amount_minor) is not int or amount_minor < 0:
        raise ValueError('환불 가정 금액은 0 이상의 정수만 허용합니다.')
    base = _base(con,subscription_id)
    if amount_minor > base['assumed_amount_minor'] or (action == 'refund_requested') != (amount_minor > 0):
        raise ValueError('실거래가 아닌 가정 환불 금액 범위 오류')
    # An event_key cannot be reused for another record or action (including old records).
    existing = con.execute('''SELECT subscription_id,action,amount_minor,note
                              FROM local_mock_subscription_events WHERE event_key=?''', (event_key,)).fetchone()
    if existing:
        if tuple(existing) != (subscription_id,action,amount_minor,note):
            raise ValueError('로컬 취소/환불 이벤트 키 재사용 충돌')
        return {**get(con,subscription_id), 'duplicate': True}
    previous = history(con,subscription_id)
    if action not in TRANSITIONS.get(previous[-1]['state'], ()):
        raise ValueError('모의 상태 전환이 허용되지 않습니다.')
    _append(con,base,len(previous)+1,event_key,action,amount_minor,note,previous[-1]['digest'])
    return {**get(con,subscription_id), 'duplicate': False}
