"""Stage73 local-only, NON-TRANSACTIONAL order-state simulations.

No customer records, providers, payment events, shipping, stock reservation,
real sales, or network operations. A local reference token is not a customer ID.
"""
from __future__ import annotations

import re
import sqlite3

from desktop.business_portfolio import _hash, _id
from desktop.offline_listing_prices import get as listing_get, MAX_PRICE
from desktop.sales_channel_contracts import _text, SENSITIVE

TOKEN = re.compile(r'[A-Za-z0-9_-]{8,48}\Z', re.ASCII)
STATES = ('RECEIVED_SIMULATED', 'REVIEWED_SIMULATED',
          'CANCELLED_SIMULATED', 'CLOSED_SIMULATED')
ACTIONS = {'created': 'RECEIVED_SIMULATED', 'owner_reviewed': 'REVIEWED_SIMULATED',
           'cancelled': 'CANCELLED_SIMULATED', 'closed': 'CLOSED_SIMULATED'}
TRANSITIONS = {'RECEIVED_SIMULATED': ('owner_reviewed', 'cancelled'),
               'REVIEWED_SIMULATED': ('closed', 'cancelled')}
MAX_QUANTITY = 1000
MAX_TOTAL = 1_000_000_000_000_000
BASE_FIELDS = ('id', 'listing_id', 'listing_digest', 'listing_revision',
               'client_token', 'quantity', 'currency', 'unit_price_minor',
               'total_minor', 'created_at')


def initialize(con: sqlite3.Connection) -> None:
    con.execute('''CREATE TABLE IF NOT EXISTS local_simulated_orders (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        listing_id INTEGER NOT NULL REFERENCES local_unpublished_listings(id) ON DELETE RESTRICT,
        listing_digest TEXT NOT NULL CHECK(length(listing_digest)=64),
        listing_revision INTEGER NOT NULL CHECK(listing_revision>0),
        client_token TEXT NOT NULL UNIQUE CHECK(length(client_token) BETWEEN 8 AND 48),
        quantity INTEGER NOT NULL CHECK(quantity BETWEEN 1 AND 1000),
        currency TEXT NOT NULL CHECK(currency IN ('KRW','USD','EUR','JPY')),
        unit_price_minor INTEGER NOT NULL CHECK(unit_price_minor BETWEEN 0 AND 1000000000000),
        total_minor INTEGER NOT NULL CHECK(total_minor BETWEEN 0 AND 1000000000000000),
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    )''')
    con.execute('''CREATE TABLE IF NOT EXISTS local_simulated_order_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        order_id INTEGER NOT NULL REFERENCES local_simulated_orders(id) ON DELETE RESTRICT,
        revision INTEGER NOT NULL CHECK(revision>0),
        action TEXT NOT NULL CHECK(action IN ('created','owner_reviewed','cancelled','closed')),
        note TEXT NOT NULL CHECK(length(note)<=500),
        previous_digest TEXT NOT NULL,
        digest TEXT NOT NULL CHECK(length(digest)=64),
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(order_id,revision)
    )''')
    con.execute('CREATE INDEX IF NOT EXISTS simulated_orders_listing_idx ON local_simulated_orders(listing_id,id)')
    con.execute('CREATE INDEX IF NOT EXISTS simulated_order_events_idx ON local_simulated_order_events(order_id,revision)')
    for table in ('local_simulated_orders', 'local_simulated_order_events'):
        for op in ('UPDATE', 'DELETE'):
            con.execute(f'''CREATE TRIGGER IF NOT EXISTS {table}_no_{op.lower()}
                BEFORE {op} ON {table} BEGIN
                SELECT RAISE(ABORT,'simulated order audit is append-only'); END''')


def _base(con, order_id):
    _id(order_id, '모의 주문')
    con.row_factory = sqlite3.Row
    row = con.execute('SELECT * FROM local_simulated_orders WHERE id=?', (order_id,)).fetchone()
    if row is None:
        raise ValueError('모의 주문이 존재하지 않습니다.')
    result = {key: row[key] for key in BASE_FIELDS}
    if (not TOKEN.fullmatch(result['client_token']) or
            type(result['quantity']) is not int or not 1 <= result['quantity'] <= MAX_QUANTITY or
            type(result['unit_price_minor']) is not int or not 0 <= result['unit_price_minor'] <= MAX_PRICE or
            result['total_minor'] != result['quantity'] * result['unit_price_minor'] or
            result['total_minor'] > MAX_TOTAL):
        raise ValueError('모의 주문 고정 원본 손상')
    return result


def _event_digest(base, revision, action, note, previous):
    return _hash(dict(base_digest=_hash(base), revision=revision, action=action,
                      note=note, previous_digest=previous))


def history(con, database_path, order_id):
    base = _base(con, order_id)
    listing_get(con, database_path, base['listing_id'])  # verifies upstream chain
    con.row_factory = sqlite3.Row
    events = con.execute('''SELECT * FROM local_simulated_order_events
        WHERE order_id=? ORDER BY revision''', (order_id,)).fetchall()
    if not events:
        raise ValueError('모의 주문 감사 기록 누락')
    result, previous, state = [], '', None
    for revision, event in enumerate(events, 1):
        action, note = event['action'], event['note']
        if (event['revision'] != revision or event['previous_digest'] != previous or
                type(note) is not str or len(note) > 500 or '\x00' in note):
            raise ValueError('모의 주문 감사 연속성 불일치')
        _text(note, '상태 기록', maximum=500, empty=(revision == 1))
        if revision == 1:
            if action != 'created' or note:
                raise ValueError('모의 주문 최초 이벤트 불일치')
        elif action not in TRANSITIONS.get(state, ()):
            raise ValueError('모의 주문 상태 전환 감사 불일치')
        expected = _event_digest(base, revision, action, note, previous)
        if event['digest'] != expected:
            raise ValueError('모의 주문 감사 해시 불일치')
        state, previous = ACTIONS[action], expected
        result.append(dict(revision=revision, action=action, state=state,
                           note=note, previous_digest=event['previous_digest'],
                           digest=expected, created_at=event['created_at']))
    return result


def get(con, database_path, order_id):
    base = _base(con, order_id)
    events = history(con, database_path, order_id)
    listing = listing_get(con, database_path, base['listing_id'])
    stale = (listing['stale_source'] or listing['state'] != 'REVIEWED_UNPUBLISHED' or
             listing['latest_digest'] != base['listing_digest'] or
             listing['revision'] != base['listing_revision'])
    return {**base, 'state': events[-1]['state'], 'revision': len(events),
            'latest_digest': events[-1]['digest'], 'stale_source': stale,
            'simulation_only': True, 'real_order': False, 'customer_recorded': False,
            'payment_received': False, 'inventory_reserved': False,
            'delivery_performed': False, 'revenue_recognized': False,
            'external_channel_connected': False}


def _append(con, order_id, action, note):
    base = _base(con, order_id)
    last = con.execute('''SELECT revision,digest FROM local_simulated_order_events
        WHERE order_id=? ORDER BY revision DESC LIMIT 1''', (order_id,)).fetchone()
    revision, previous = (last[0]+1, last[1]) if last else (1, '')
    digest = _event_digest(base, revision, action, note, previous)
    con.execute('''INSERT INTO local_simulated_order_events
        (order_id,revision,action,note,previous_digest,digest)
        VALUES (?,?,?,?,?,?)''', (order_id,revision,action,note,previous,digest))


def create(con, database_path, listing_id, client_token, quantity):
    _id(listing_id, '미게시 상품 초안')
    if (type(client_token) is not str or not TOKEN.fullmatch(client_token) or
            SENSITIVE.search(client_token) or
            any(word in client_token.lower() for word in ('api_key', 'secret', 'token', 'password', 'credential', 'bearer'))):
        raise ValueError('로컬 중복 방지 토큰은 영문/숫자/_/- 8~48자만 허용합니다. 고객 정보 금지.')
    if type(quantity) is not int or not 1 <= quantity <= MAX_QUANTITY:
        raise ValueError('모의 수량은 정수 1~1000만 허용합니다.')
    # Unique idempotency token across ALL local simulations, including cancelled ones.
    existing = con.execute('SELECT id FROM local_simulated_orders WHERE client_token=?',
                           (client_token,)).fetchone()
    if existing:
        row = get(con, database_path, existing[0])
        if row['listing_id'] != listing_id or row['quantity'] != quantity:
            raise ValueError('동일 중복 방지 토큰으로 다른 모의 주문을 생성할 수 없습니다.')
        return row
    listing = listing_get(con, database_path, listing_id)
    if listing['state'] != 'REVIEWED_UNPUBLISHED' or listing['stale_source']:
        raise ValueError('원본 변경 없는 관리자 자체 검토 미게시 초안만 모의 주문 가능')
    total = listing['price_minor'] * quantity
    if total > MAX_TOTAL:
        raise ValueError('모의 총액 상한 초과')
    cur = con.execute('''INSERT INTO local_simulated_orders
        (listing_id,listing_digest,listing_revision,client_token,quantity,currency,
         unit_price_minor,total_minor) VALUES (?,?,?,?,?,?,?,?)''',
        (listing_id,listing['latest_digest'],listing['revision'],client_token,
         quantity,listing['currency'],listing['price_minor'],total))
    _append(con, int(cur.lastrowid), 'created', '')
    return get(con, database_path, int(cur.lastrowid))


def transition(con, database_path, order_id, action, note):
    if action not in ('owner_reviewed','cancelled','closed'):
        raise ValueError('허용되지 않은 모의 상태 전환')
    note = _text(note, '상태 전환 사유', maximum=500)
    old = get(con, database_path, order_id)
    if old['stale_source']:
        raise ValueError('원본 초안이 변경되어 모의 상태 전환 보류')
    if action not in TRANSITIONS.get(old['state'], ()):
        raise ValueError('허용되지 않은 모의 상태 전환')
    _append(con, order_id, action, note)
    return get(con, database_path, order_id)


def list_orders(con, database_path, limit=100):
    if type(limit) is not int or not 1 <= limit <= 200:
        raise ValueError('조회 개수 1~200만 허용')
    ids = [r[0] for r in con.execute('SELECT id FROM local_simulated_orders ORDER BY id DESC LIMIT ?',
                                     (limit,)).fetchall()]
    return [get(con, database_path, ident) for ident in ids]
