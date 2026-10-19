"""Stage72: unpublished, owner-edited listing and assumed price drafts.

NO provider API, publication, order, currency conversion, payment or live price.
Source lineage is Stage71 reviewed DISCONNECTED contract -> Stage70 plan ->
Stage68 static prototype -> Stage67 catalogue. Every record stays unpublished.
"""
from __future__ import annotations

import json
import sqlite3

from desktop.business_portfolio import _hash, _id
from desktop.product_catalog import get as catalog_get
from desktop.product_production import get as prototype_get
from desktop.service_operations_plan import get as operations_get
from desktop.sales_channel_contracts import get as contract_get, _text

CURRENCIES = ('KRW', 'USD', 'EUR', 'JPY')
# Integer *minor* units: KRW/JPY won; USD/EUR cents. No FX conversions.
MINOR_UNIT = {'KRW': '원', 'JPY': '엔', 'USD': '센트', 'EUR': '센트'}
STATES = ('DRAFT_UNPUBLISHED', 'REVIEWED_UNPUBLISHED', 'RETIRED_UNPUBLISHED')
BASE_FIELDS = ('id', 'contract_id', 'contract_digest', 'catalog_item_id',
               'catalog_version', 'catalog_digest', 'created_at')
SNAP_FIELDS = ('title', 'description', 'currency', 'price_minor', 'price_note')
MAX_PRICE = 1_000_000_000_000


def initialize(con: sqlite3.Connection) -> None:
    con.execute('''CREATE TABLE IF NOT EXISTS local_unpublished_listings (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        contract_id INTEGER NOT NULL REFERENCES local_sales_channel_contracts(id) ON DELETE RESTRICT,
        contract_digest TEXT NOT NULL CHECK(length(contract_digest)=64),
        catalog_item_id INTEGER NOT NULL REFERENCES local_catalog_items(id) ON DELETE RESTRICT,
        catalog_version INTEGER NOT NULL CHECK(catalog_version > 0),
        catalog_digest TEXT NOT NULL CHECK(length(catalog_digest)=64),
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    )''')
    con.execute('''CREATE TABLE IF NOT EXISTS local_unpublished_listing_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        listing_id INTEGER NOT NULL REFERENCES local_unpublished_listings(id) ON DELETE RESTRICT,
        revision INTEGER NOT NULL CHECK(revision > 0),
        action TEXT NOT NULL CHECK(action IN ('created','revised','owner_reviewed','retired')),
        snapshot_json TEXT NOT NULL,
        note TEXT NOT NULL CHECK(length(note) <= 500),
        previous_digest TEXT NOT NULL,
        digest TEXT NOT NULL CHECK(length(digest)=64),
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(listing_id,revision)
    )''')
    con.execute('CREATE INDEX IF NOT EXISTS unpublished_listings_by_contract ON local_unpublished_listings(contract_id,id)')
    con.execute('CREATE INDEX IF NOT EXISTS unpublished_listing_events_by_listing ON local_unpublished_listing_events(listing_id,revision)')
    for table in ('local_unpublished_listings', 'local_unpublished_listing_events'):
        for op in ('UPDATE', 'DELETE'):
            con.execute(f'''CREATE TRIGGER IF NOT EXISTS {table}_no_{op.lower()}
                BEFORE {op} ON {table} BEGIN
                SELECT RAISE(ABORT,'unpublished listing audit is append-only'); END''')


def _snapshot(title, description, currency, price_minor, price_note):
    title = _text(title, '미게시 상품명', maximum=120)
    description = _text(description, '미게시 설명', maximum=1000)
    price_note = _text(price_note, '가격 가정 근거', maximum=500)
    if type(currency) is not str or currency not in CURRENCIES:
        raise ValueError('가격 통화는 KRW/USD/EUR/JPY 중 하나여야 합니다.')
    if type(price_minor) is not int or not 0 <= price_minor <= MAX_PRICE:
        raise ValueError('가격은 0~1조 정수 최소 화폐단위만 허용합니다.')
    return dict(title=title, description=description, currency=currency,
                price_minor=price_minor, price_note=price_note)


def _base(con, listing_id):
    _id(listing_id, '미게시 상품 등록 초안')
    con.row_factory = sqlite3.Row
    row = con.execute('SELECT * FROM local_unpublished_listings WHERE id=?', (listing_id,)).fetchone()
    if row is None:
        raise ValueError('미게시 상품 등록 초안이 존재하지 않습니다.')
    return {k: row[k] for k in BASE_FIELDS}


def _source(con, database_path, contract_id):
    contract = contract_get(con, database_path, contract_id)
    plan = operations_get(con, database_path, contract['operations_plan_id'])
    prototype = prototype_get(con, database_path, plan['prototype_id'])
    item = catalog_get(con, prototype['catalog_item_id'])
    return contract, item


def _source_ok(contract, item):
    if (contract['state'] != 'REVIEWED_DISCONNECTED' or contract['stale_source'] or
            'listing_draft_future' not in contract['planned_scopes'] or
            item['state'] == 'archived'):
        raise ValueError('Stage71 미연결 관리자 검토 계획/초안 권한 및 활성 상품이 필요합니다.')


def _payload(listing_id, revision, action, snapshot, note, previous, base_digest):
    return dict(listing_id=listing_id, revision=revision, action=action,
                snapshot=snapshot, note=note, previous_digest=previous,
                base_digest=base_digest)


def _append(con, listing_id, action, snapshot, note):
    base = _base(con, listing_id)
    last = con.execute('''SELECT revision,digest FROM local_unpublished_listing_events
        WHERE listing_id=? ORDER BY revision DESC LIMIT 1''', (listing_id,)).fetchone()
    revision, previous = (int(last[0]) + 1, last[1]) if last else (1, '')
    payload = _payload(listing_id, revision, action, snapshot, note, previous, _hash(base))
    con.execute('''INSERT INTO local_unpublished_listing_events
        (listing_id,revision,action,snapshot_json,note,previous_digest,digest)
        VALUES (?,?,?,?,?,?,?)''', (listing_id, revision, action,
        json.dumps(snapshot, ensure_ascii=False, sort_keys=True, separators=(',', ':')),
        note, previous, _hash(payload)))


def history(con, database_path, listing_id):
    base = _base(con, listing_id)
    contract, item = _source(con, database_path, base['contract_id'])
    # All reads verify full upstream audit and original file, even when stale.
    if contract['id'] != base['contract_id'] or item['id'] != base['catalog_item_id']:
        raise ValueError('상품/채널 연결 원본 불일치')
    con.row_factory = sqlite3.Row
    events = con.execute('''SELECT * FROM local_unpublished_listing_events
        WHERE listing_id=? ORDER BY revision''', (listing_id,)).fetchall()
    if not events:
        raise ValueError('미게시 상품 등록 감사 이력 누락')
    previous, result = '', []
    for revision, event in enumerate(events, 1):
        try:
            snap = json.loads(event['snapshot_json'])
            if type(snap) is not dict or set(snap) != set(SNAP_FIELDS):
                raise ValueError('snapshot fields')
            normalized = _snapshot(**snap)
            if normalized != snap or json.dumps(snap, ensure_ascii=False, sort_keys=True, separators=(',', ':')) != event['snapshot_json']:
                raise ValueError('snapshot canonical')
        except (TypeError, ValueError) as exc:
            raise ValueError('미게시 상품 가격 감사 스냅샷 손상') from exc
        action, note = event['action'], event['note']
        if (event['revision'] != revision or event['previous_digest'] != previous or
                type(note) is not str or len(note) > 500 or '\x00' in note):
            raise ValueError('미게시 상품 감사 연속성 불일치')
        _text(note, '감사 메모', empty=True)
        if revision == 1:
            if action != 'created' or note:
                raise ValueError('최초 미게시 초안 감사 불일치')
        else:
            prev = result[-1]
            if (prev['action'] == 'retired' or action not in ('revised','owner_reviewed','retired') or
                    (action == 'revised' and (prev['action'] != 'created' and prev['action'] != 'revised' or snap == prev['snapshot'])) or
                    (action != 'revised' and snap != prev['snapshot']) or
                    (action == 'owner_reviewed' and prev['action'] == 'owner_reviewed') or
                    (action == 'retired' and not note.strip())):
                raise ValueError('미게시 상품 감사 상태 전환 불일치')
        payload = _payload(listing_id, revision, action, snap, note, previous, _hash(base))
        if event['digest'] != _hash(payload):
            raise ValueError('미게시 상품 감사 해시 불일치')
        previous = event['digest']
        result.append({**payload, 'digest': previous, 'created_at': event['created_at']})
    return result


def get(con, database_path, listing_id):
    base = _base(con, listing_id)
    events = history(con, database_path, listing_id)
    contract, item = _source(con, database_path, base['contract_id'])
    stale = (contract['stale_source'] or contract['state'] != 'REVIEWED_DISCONNECTED' or
             contract['latest_digest'] != base['contract_digest'] or
             item['version'] != base['catalog_version'] or
             _hash(item) != base['catalog_digest'] or item['state'] == 'archived')
    state = ('RETIRED_UNPUBLISHED' if events[-1]['action'] == 'retired' else
             'REVIEWED_UNPUBLISHED' if events[-1]['action'] == 'owner_reviewed' else 'DRAFT_UNPUBLISHED')
    return {**base, **events[-1]['snapshot'], 'state': state, 'stale_source': stale,
            'revision': len(events), 'latest_digest': events[-1]['digest'],
            'price_is_assumption': True, 'currency_minor_unit': MINOR_UNIT[events[-1]['snapshot']['currency']],
            'published': False, 'connected': False, 'price_synced': False,
            'orders_received': False, 'payments_received': False}


def create(con, database_path, contract_id, catalog_item_id, title, description,
           currency, price_minor, price_note):
    _id(catalog_item_id, '상품·서비스')
    snap = _snapshot(title, description, currency, price_minor, price_note)
    contract, item = _source(con, database_path, contract_id)
    _source_ok(contract, item)
    if item['id'] != catalog_item_id:
        raise ValueError('Stage71 계획과 동일한 상품·서비스만 미게시 등록 초안 생성 가능')
    ids = con.execute('''SELECT id FROM local_unpublished_listings
        WHERE contract_id=? AND catalog_item_id=?''', (contract_id, catalog_item_id)).fetchall()
    for ident, in ids:
        if get(con, database_path, ident)['state'] != 'RETIRED_UNPUBLISHED':
            raise ValueError('동일 채널/상품의 미폐기 초안이 이미 있습니다.')
    cur = con.execute('''INSERT INTO local_unpublished_listings
        (contract_id,contract_digest,catalog_item_id,catalog_version,catalog_digest)
        VALUES (?,?,?,?,?)''', (contract_id, contract['latest_digest'], catalog_item_id,
                                item['version'], _hash(item)))
    ident = int(cur.lastrowid)
    _append(con, ident, 'created', snap, '')
    return get(con, database_path, ident)


def revise(con, database_path, listing_id, title, description, currency, price_minor, price_note):
    old = get(con, database_path, listing_id)
    if old['state'] != 'DRAFT_UNPUBLISHED' or old['stale_source']:
        raise ValueError('원본 변경 없는 미게시 초안 상태에서만 가격 수정 가능')
    snap = _snapshot(title, description, currency, price_minor, price_note)
    if all(old[k] == snap[k] for k in SNAP_FIELDS):
        raise ValueError('변경된 상품·가격 가정이 없습니다.')
    _append(con, listing_id, 'revised', snap, '')
    return get(con, database_path, listing_id)


def review(con, database_path, listing_id, note):
    _text(note, '관리자 검토 메모')
    old = get(con, database_path, listing_id)
    if old['state'] != 'DRAFT_UNPUBLISHED' or old['stale_source']:
        raise ValueError('원본 변경 없는 미게시 초안만 자체 검토 가능')
    _append(con, listing_id, 'owner_reviewed', {k: old[k] for k in SNAP_FIELDS}, note)
    return get(con, database_path, listing_id)


def retire(con, database_path, listing_id, note):
    _text(note, '폐기 사유')
    old = get(con, database_path, listing_id)
    if old['state'] == 'RETIRED_UNPUBLISHED':
        raise ValueError('이미 폐기된 초안')
    _append(con, listing_id, 'retired', {k: old[k] for k in SNAP_FIELDS}, note)
    return get(con, database_path, listing_id)


def list_drafts(con, database_path, limit=100):
    if type(limit) is not int or not 1 <= limit <= 200:
        raise ValueError('조회 개수 1~200만 가능')
    ids = [row[0] for row in con.execute('''SELECT id FROM local_unpublished_listings
        ORDER BY id DESC LIMIT ?''', (limit,)).fetchall()]
    return [get(con, database_path, ident) for ident in ids]
