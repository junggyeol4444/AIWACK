"""Stage67: owner-operated offline product/service information catalogue.

Planning metadata only. No release, customer, order, payment, publishing,
AI generation or external-service call. The local hash chain is not a signature.
"""
from __future__ import annotations

import json
import sqlite3

from desktop.business_portfolio import _hash, _id, _label
from desktop.business_projects import get as get_project

KINDS = ('product', 'service')
STATES = ('draft', 'review_pending', 'archived')
TRANSITIONS = {'draft': {'review_pending', 'archived'},
               'review_pending': {'draft', 'archived'}, 'archived': set()}
FIELDS = ('business_id', 'project_id', 'kind', 'name', 'description',
          'assumed_price_krw', 'delivery_note', 'state', 'version')


def initialize(con: sqlite3.Connection) -> None:
    con.execute('''CREATE TABLE IF NOT EXISTS local_catalog_items (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        business_id INTEGER NOT NULL REFERENCES managed_businesses(id) ON DELETE RESTRICT,
        project_id INTEGER REFERENCES managed_business_projects(id) ON DELETE RESTRICT,
        kind TEXT NOT NULL CHECK(kind IN ('product','service')),
        name TEXT NOT NULL CHECK(length(name) BETWEEN 1 AND 120),
        description TEXT NOT NULL CHECK(length(description) BETWEEN 1 AND 1000),
        assumed_price_krw INTEGER NOT NULL CHECK(assumed_price_krw BETWEEN 0 AND 1000000000000),
        delivery_note TEXT NOT NULL CHECK(length(delivery_note) BETWEEN 1 AND 400),
        state TEXT NOT NULL DEFAULT 'draft' CHECK(state IN ('draft','review_pending','archived')),
        version INTEGER NOT NULL DEFAULT 1 CHECK(version > 0),
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    )''')
    con.execute('''CREATE TABLE IF NOT EXISTS local_catalog_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        item_id INTEGER NOT NULL REFERENCES local_catalog_items(id) ON DELETE RESTRICT,
        action TEXT NOT NULL CHECK(action IN ('created','revised','state_changed')),
        snapshot_json TEXT NOT NULL,
        previous_digest TEXT NOT NULL,
        digest TEXT NOT NULL CHECK(length(digest)=64),
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    )''')
    con.execute('CREATE INDEX IF NOT EXISTS local_catalog_by_business ON local_catalog_items(business_id,id)')
    con.execute('CREATE INDEX IF NOT EXISTS local_catalog_events_by_item ON local_catalog_events(item_id,id)')
    for op in ('UPDATE', 'DELETE'):
        con.execute(f'''CREATE TRIGGER IF NOT EXISTS local_catalog_events_no_{op.lower()}
            BEFORE {op} ON local_catalog_events BEGIN
            SELECT RAISE(ABORT,'catalog audit is append-only'); END''')
    con.execute('''CREATE TRIGGER IF NOT EXISTS local_catalog_no_delete
        BEFORE DELETE ON local_catalog_items BEGIN
        SELECT RAISE(ABORT,'catalog item history is preserved'); END''')
    con.execute('''CREATE TRIGGER IF NOT EXISTS local_catalog_identity_guard
        BEFORE UPDATE OF business_id,project_id,kind,name ON local_catalog_items BEGIN
        SELECT RAISE(ABORT,'catalog identity and links are immutable'); END''')


def _price(value: int) -> int:
    if type(value) is not int or not 0 <= value <= 1_000_000_000_000:
        raise ValueError('가정 가격은 0~1조 원 정수여야 합니다.')
    return value


def _business_link(con: sqlite3.Connection, business_id: int, project_id: int | None) -> None:
    _id(business_id, '사업')
    row = con.execute('SELECT state FROM managed_businesses WHERE id=?', (business_id,)).fetchone()
    if not row or row[0] == 'closed':
        raise ValueError('존재하지 않거나 종료된 사업입니다.')
    if project_id is not None:
        _id(project_id, '프로젝트')
        project = get_project(con, project_id)  # Also verify Stage66 audit chain.
        if project['business_id'] != business_id or project['state'] in ('completed', 'cancelled'):
            raise ValueError('다른 사업 또는 종료된 프로젝트에는 연결할 수 없습니다.')


def _snapshot(row: dict) -> dict:
    return {field: row[field] for field in FIELDS}


def _event(con: sqlite3.Connection, item_id: int, action: str, snap: dict) -> None:
    prev_row = con.execute('SELECT digest FROM local_catalog_events WHERE item_id=? ORDER BY id DESC LIMIT 1',
                           (item_id,)).fetchone()
    previous = prev_row[0] if prev_row else ''
    raw = json.dumps(snap, ensure_ascii=False, sort_keys=True, separators=(',', ':'))
    digest = _hash({'item_id': item_id, 'action': action, 'snapshot': snap, 'previous_digest': previous})
    con.execute('''INSERT INTO local_catalog_events(item_id,action,snapshot_json,previous_digest,digest)
                   VALUES (?,?,?,?,?)''', (item_id, action, raw, previous, digest))


def create(con: sqlite3.Connection, business_id: int, kind: str, name: str,
           description: str, assumed_price_krw: int, delivery_note: str,
           project_id: int | None = None) -> int:
    _business_link(con, business_id, project_id)
    if type(kind) is not str or kind not in KINDS:
        raise ValueError('상품 또는 서비스 종류를 선택해야 합니다.')
    name = _label(name, '상품·서비스명', 120)
    description = _label(description, '설명', 1000)
    delivery_note = _label(delivery_note, '제공 계획', 400)
    _price(assumed_price_krw)
    cur = con.execute('''INSERT INTO local_catalog_items
        (business_id,project_id,kind,name,description,assumed_price_krw,delivery_note)
        VALUES (?,?,?,?,?,?,?)''',
        (business_id, project_id, kind, name, description, assumed_price_krw, delivery_note))
    item_id = int(cur.lastrowid)
    _event(con, item_id, 'created', _row(con, item_id))
    return item_id


def _row(con: sqlite3.Connection, item_id: int) -> dict:
    _id(item_id, '상품·서비스')
    con.row_factory = sqlite3.Row
    row = con.execute('SELECT * FROM local_catalog_items WHERE id=?', (item_id,)).fetchone()
    if row is None:
        raise ValueError('상품·서비스가 존재하지 않습니다.')
    return _snapshot(dict(row))


def get(con: sqlite3.Connection, item_id: int) -> dict:
    current = _row(con, item_id)
    events = con.execute('''SELECT action,snapshot_json,previous_digest,digest
                            FROM local_catalog_events WHERE item_id=? ORDER BY id''', (item_id,)).fetchall()
    if not events:
        raise ValueError('상품·서비스 생성 감사 기록 누락')
    previous = ''
    prior = None
    for index, event in enumerate(events):
        try:
            snap = json.loads(event['snapshot_json'])
        except (ValueError, TypeError) as exc:
            raise ValueError('상품·서비스 감사 JSON 손상') from exc
        action = event['action']
        expected = _hash({'item_id': item_id, 'action': action,
                          'snapshot': snap, 'previous_digest': previous})
        if event['previous_digest'] != previous or event['digest'] != expected:
            raise ValueError('상품·서비스 감사 무결성 오류')
        if not isinstance(snap, dict) or set(snap) != set(FIELDS):
            raise ValueError('상품·서비스 감사 스냅샷 불일치')
        if index == 0:
            if action != 'created' or snap['version'] != 1 or snap['state'] != 'draft':
                raise ValueError('상품·서비스 생성 감사 불일치')
        else:
            if action not in ('revised', 'state_changed') or snap['version'] != prior['version'] + 1:
                raise ValueError('상품·서비스 감사 버전 불일치')
            if any(snap[k] != prior[k] for k in ('business_id','project_id','kind','name')):
                raise ValueError('상품·서비스 연결 감사 불일치')
            if action == 'revised':
                if prior['state'] != 'draft' or snap['state'] != 'draft' or not any(
                        snap[k] != prior[k] for k in ('description','assumed_price_krw','delivery_note')):
                    raise ValueError('상품·서비스 수정 감사 불일치')
            elif (snap['state'] not in TRANSITIONS.get(prior['state'], set()) or
                  any(snap[k] != prior[k] for k in ('description','assumed_price_krw','delivery_note'))):
                raise ValueError('상품·서비스 상태 감사 불일치')
        prior = snap
        previous = event['digest']
    if prior != current:
        raise ValueError('상품·서비스 현재 상태와 감사 기록 불일치')
    return {'id': item_id, **current, 'external_actions_executed': False,
            'actual_sales_verified': False, 'price_is_assumption': True}


def revise(con: sqlite3.Connection, item_id: int, description: str,
           assumed_price_krw: int, delivery_note: str) -> dict:
    old = get(con, item_id)
    if old['state'] != 'draft':
        raise ValueError('초안 상태에서만 정보를 수정할 수 있습니다.')
    description = _label(description, '설명', 1000)
    delivery_note = _label(delivery_note, '제공 계획', 400)
    _price(assumed_price_krw)
    if all(old[k] == v for k, v in [('description', description),
             ('assumed_price_krw', assumed_price_krw), ('delivery_note', delivery_note)]):
        raise ValueError('변경된 정보가 없습니다.')
    con.execute('''UPDATE local_catalog_items SET description=?,assumed_price_krw=?,
        delivery_note=?,version=version+1,updated_at=CURRENT_TIMESTAMP WHERE id=?''',
        (description, assumed_price_krw, delivery_note, item_id))
    _event(con, item_id, 'revised', _row(con, item_id))
    return get(con, item_id)


def change_state(con: sqlite3.Connection, item_id: int, new_state: str) -> dict:
    old = get(con, item_id)
    if type(new_state) is not str or new_state not in TRANSITIONS[old['state']]:
        raise ValueError('상품·서비스 검토 상태 전환이 허용되지 않습니다.')
    con.execute('''UPDATE local_catalog_items SET state=?,version=version+1,
        updated_at=CURRENT_TIMESTAMP WHERE id=?''', (new_state, item_id))
    _event(con, item_id, 'state_changed', _row(con, item_id))
    return get(con, item_id)


def list_items(con: sqlite3.Connection, business_id: int | None = None, limit: int = 100) -> list[dict]:
    if business_id is not None:
        _id(business_id, '사업')
        if not con.execute('SELECT 1 FROM managed_businesses WHERE id=?', (business_id,)).fetchone():
            raise ValueError('사업이 존재하지 않습니다.')
    if type(limit) is not int or not 1 <= limit <= 200:
        raise ValueError('조회 개수는 1~200입니다.')
    where = '' if business_id is None else ' WHERE business_id=?'
    params = (limit,) if business_id is None else (business_id, limit)
    ids = [r[0] for r in con.execute(
        'SELECT id FROM local_catalog_items' + where + ' ORDER BY id DESC LIMIT ?', params)]
    return [get(con, item_id) for item_id in ids]


def events(con: sqlite3.Connection, item_id: int) -> list[dict]:
    get(con, item_id)
    con.row_factory = sqlite3.Row
    return [dict(r) for r in con.execute('''SELECT id,action,snapshot_json,previous_digest,digest,created_at
        FROM local_catalog_events WHERE item_id=? ORDER BY id''', (item_id,))]
