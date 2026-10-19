"""Stage71: offline, inert future sales-channel contracts; NEVER connect or sell.

No URLs, account identifiers, credentials, HTTP clients, tokens, network calls,
product listings, orders or financial events are stored or executed here.
Owner review is a *self-report*, not permission to connect. The SQLite hash chain
is an integrity check, not a cryptographic signature against a DB administrator.
"""
from __future__ import annotations

import json
import re
import sqlite3

from desktop.business_portfolio import _hash, _id
from desktop.service_operations_plan import get as get_operations_plan

KINDS = ('marketplace_future', 'own_store_future', 'digital_delivery_future', 'booking_future')
REGIONS = ('KR_future', 'international_future', 'unspecified_future')
MODES = ('manual_future', 'api_future')
SCOPES = ('catalog_metadata_future', 'listing_draft_future', 'orders_metadata_future',
          'support_metadata_future')
CHECKS = ('owner_authorization', 'provider_terms', 'privacy_review',
          'security_review', 'product_release_review')
ANSWERS = ('unverified', 'needs_work', 'owner_reports_prepared')
STATES = ('DRAFT_DISCONNECTED', 'REVIEWED_DISCONNECTED', 'RETIRED_DISCONNECTED')
FIELDS = ('id', 'operations_plan_id', 'operations_digest', 'channel_kind',
          'display_name', 'region', 'integration_mode', 'planned_scopes_json',
          'mapping_note', 'compliance_note')
# Deliberately refuse even accidental credential/account/endpoint storage.
SENSITIVE = re.compile(r'(?i)(?:https?://|www\.|\b(?:password|passwd|secret|api[_ -]?key|access[_ -]?token|bearer|credential|private[_ -]?key|client[_ -]?secret)\b|\bsk-[a-z0-9]|\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b)')


def initialize(con: sqlite3.Connection) -> None:
    con.execute('''CREATE TABLE IF NOT EXISTS local_sales_channel_contracts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        operations_plan_id INTEGER NOT NULL REFERENCES local_service_operations_plans(id) ON DELETE RESTRICT,
        operations_digest TEXT NOT NULL CHECK(length(operations_digest)=64),
        channel_kind TEXT NOT NULL CHECK(channel_kind IN
            ('marketplace_future','own_store_future','digital_delivery_future','booking_future')),
        display_name TEXT NOT NULL CHECK(length(display_name) BETWEEN 1 AND 80),
        region TEXT NOT NULL CHECK(region IN ('KR_future','international_future','unspecified_future')),
        integration_mode TEXT NOT NULL CHECK(integration_mode IN ('manual_future','api_future')),
        planned_scopes_json TEXT NOT NULL,
        mapping_note TEXT NOT NULL CHECK(length(mapping_note) BETWEEN 1 AND 500),
        compliance_note TEXT NOT NULL CHECK(length(compliance_note) BETWEEN 1 AND 500),
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    )''')
    con.execute('''CREATE TABLE IF NOT EXISTS local_sales_channel_contract_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        contract_id INTEGER NOT NULL REFERENCES local_sales_channel_contracts(id) ON DELETE RESTRICT,
        revision INTEGER NOT NULL CHECK(revision > 0),
        action TEXT NOT NULL CHECK(action IN ('created','owner_reviewed','retired')),
        checks_json TEXT NOT NULL,
        note TEXT NOT NULL CHECK(length(note) <= 500),
        previous_digest TEXT NOT NULL,
        digest TEXT NOT NULL CHECK(length(digest)=64),
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(contract_id,revision)
    )''')
    con.execute('CREATE INDEX IF NOT EXISTS sales_contracts_by_plan ON local_sales_channel_contracts(operations_plan_id)')
    con.execute('CREATE INDEX IF NOT EXISTS sales_contract_events_by_contract ON local_sales_channel_contract_events(contract_id,revision)')
    for table in ('local_sales_channel_contracts', 'local_sales_channel_contract_events'):
        for op in ('UPDATE', 'DELETE'):
            con.execute(f'''CREATE TRIGGER IF NOT EXISTS {table}_no_{op.lower()}
                BEFORE {op} ON {table} BEGIN
                SELECT RAISE(ABORT, 'sales channel contract audit is append-only'); END''')


def _text(value, label, *, maximum=500, empty=False):
    if (type(value) is not str or len(value) > maximum or '\x00' in value or
            (not empty and not value.strip()) or SENSITIVE.search(value)):
        raise ValueError(f'{label}: 비밀정보·주소·계정 없이 {maximum}자 이내 로컬 설명만 허용')
    return value


def _scopes(value):
    if (type(value) not in (list, tuple) or not 1 <= len(value) <= len(SCOPES) or
            any(type(s) is not str or s not in SCOPES for s in value) or
            len(set(value)) != len(value)):
        raise ValueError('계획된 권한 범위는 허용된 중복 없는 항목 1~4개만 가능')
    return sorted(value)


def _checks(value):
    if type(value) is not dict or set(value) != set(CHECKS):
        raise ValueError('채널 연결 준비 체크리스트 5개 항목이 필요합니다.')
    if any(type(value[k]) is not str or value[k] not in ANSWERS for k in CHECKS):
        raise ValueError('관리자 주장/미검증/보완 상태만 허용합니다.')
    return {k: value[k] for k in CHECKS}


def _source(con, database_path, operations_plan_id):
    plan = get_operations_plan(con, database_path, operations_plan_id)
    if plan['state'] != 'REVIEWED_NO_DEPLOY' or plan['stale_source']:
        raise ValueError('원본 변경 없는 Stage70 관리자 자체 검토 계획만 참조 가능')
    return plan


def _row(con, contract_id):
    _id(contract_id, '판매 채널 계약')
    con.row_factory = sqlite3.Row
    row = con.execute('SELECT * FROM local_sales_channel_contracts WHERE id=?', (contract_id,)).fetchone()
    if row is None:
        raise ValueError('판매 채널 계획이 없습니다.')
    return {k: row[k] for k in FIELDS}


def _validate_row(row):
    if row['channel_kind'] not in KINDS or row['region'] not in REGIONS or row['integration_mode'] not in MODES:
        raise ValueError('판매 채널 계획 필드 손상')
    _text(row['display_name'], '채널 별칭', maximum=80)
    _text(row['mapping_note'], '데이터 매핑 계획')
    _text(row['compliance_note'], '규정 검토 계획')
    try:
        scopes = json.loads(row['planned_scopes_json'])
        if _scopes(scopes) != scopes or json.dumps(scopes, separators=(',', ':')) != row['planned_scopes_json']:
            raise ValueError('invalid canonical scopes')
    except (ValueError, TypeError) as exc:
        raise ValueError('계획된 권한 범위 손상') from exc
    return scopes


def _payload(contract_id, revision, action, checks, note, previous, row_hash):
    return {'contract_id': contract_id, 'revision': revision, 'action': action,
            'checks': checks, 'note': note, 'previous_digest': previous,
            'contract_digest': row_hash}


def _append(con, contract_id, action, checks, note):
    last = con.execute('''SELECT revision,digest FROM local_sales_channel_contract_events
        WHERE contract_id=? ORDER BY revision DESC LIMIT 1''', (contract_id,)).fetchone()
    revision, previous = (int(last[0])+1, last[1]) if last else (1, '')
    payload = _payload(contract_id, revision, action, checks, note, previous,
                       _hash(_row(con, contract_id)))
    con.execute('''INSERT INTO local_sales_channel_contract_events
        (contract_id,revision,action,checks_json,note,previous_digest,digest)
        VALUES (?,?,?,?,?,?,?)''', (contract_id, revision, action,
        json.dumps(checks, ensure_ascii=False, sort_keys=True, separators=(',', ':')),
        note, previous, _hash(payload)))


def history(con, database_path, contract_id):
    row = _row(con, contract_id)
    _validate_row(row)
    # Recheck source artifact, release audit and Stage70 audit even on reads.
    plan = get_operations_plan(con, database_path, row['operations_plan_id'])
    con.row_factory = sqlite3.Row
    records = con.execute('''SELECT * FROM local_sales_channel_contract_events
        WHERE contract_id=? ORDER BY revision''', (contract_id,)).fetchall()
    if not records:
        raise ValueError('채널 계약 감사 기록 누락')
    previous = ''
    output = []
    for revision, event in enumerate(records, 1):
        try:
            checks = _checks(json.loads(event['checks_json']))
            if json.dumps(checks, ensure_ascii=False, sort_keys=True, separators=(',', ':')) != event['checks_json']:
                raise ValueError('not canonical')
        except (ValueError, TypeError) as exc:
            raise ValueError('채널 체크리스트 손상') from exc
        action = event['action']
        if (event['revision'] != revision or event['previous_digest'] != previous or
                (revision == 1 and (action != 'created' or any(v != 'unverified' for v in checks.values()))) or
                (revision > 1 and action not in ('owner_reviewed','retired')) or
                (output and output[-1]['action'] == 'retired') or
                (action == 'retired' and any(v != 'unverified' for v in checks.values())) or
                type(event['note']) is not str or len(event['note']) > 500 or
                SENSITIVE.search(event['note'])):
            raise ValueError('채널 감사 연속성·상태 불일치')
        payload = _payload(contract_id, revision, action, checks, event['note'],
                           previous, _hash(row))
        if _hash(payload) != event['digest']:
            raise ValueError('채널 감사 해시 불일치')
        previous = event['digest']
        output.append({'id': event['id'], **payload, 'digest': previous,
                       'created_at': event['created_at']})
    return output


def get(con, database_path, contract_id):
    row = _row(con, contract_id)
    scopes = _validate_row(row)
    events = history(con, database_path, contract_id)
    plan = get_operations_plan(con, database_path, row['operations_plan_id'])
    stale = (plan['stale_source'] or plan['state'] != 'REVIEWED_NO_DEPLOY' or
             plan['latest_digest'] != row['operations_digest'])
    action = events[-1]['action']
    state = ('RETIRED_DISCONNECTED' if action == 'retired' else
             'REVIEWED_DISCONNECTED' if action == 'owner_reviewed' else 'DRAFT_DISCONNECTED')
    return {**row, 'planned_scopes': scopes, 'state': state, 'stale_source': stale,
            'latest_checks': events[-1]['checks'], 'event_count': len(events),
            'latest_digest': events[-1]['digest'], 'connected': False,
            'credentials_stored': False, 'listing_created': False,
            'orders_received': False, 'payments_received': False}


def create(con, database_path, operations_plan_id, channel_kind, display_name,
           region, integration_mode, planned_scopes, mapping_note, compliance_note):
    if type(channel_kind) is not str or channel_kind not in KINDS:
        raise ValueError('허용된 미래 채널 종류만 가능')
    if type(region) is not str or region not in REGIONS:
        raise ValueError('허용된 미래 지역만 가능')
    if type(integration_mode) is not str or integration_mode not in MODES:
        raise ValueError('허용된 미래 연결 방식만 가능')
    name = _text(display_name, '채널 별칭', maximum=80)
    mapping = _text(mapping_note, '데이터 매핑 계획')
    compliance = _text(compliance_note, '규정 검토 계획')
    scopes = _scopes(planned_scopes)
    plan = _source(con, database_path, operations_plan_id)
    cursor = con.execute('''INSERT INTO local_sales_channel_contracts
        (operations_plan_id,operations_digest,channel_kind,display_name,region,
         integration_mode,planned_scopes_json,mapping_note,compliance_note)
        VALUES (?,?,?,?,?,?,?,?,?)''', (operations_plan_id, plan['latest_digest'],
        channel_kind, name, region, integration_mode,
        json.dumps(scopes, separators=(',', ':')), mapping, compliance))
    ident = int(cursor.lastrowid)
    _append(con, ident, 'created', {k: 'unverified' for k in CHECKS}, '')
    return get(con, database_path, ident)


def review(con, database_path, contract_id, checklist, note):
    checks = _checks(checklist)
    _text(note, '검토 메모', empty=True)
    contract = get(con, database_path, contract_id)
    if contract['state'] == 'RETIRED_DISCONNECTED' or contract['stale_source']:
        raise ValueError('폐기 또는 원본 변경된 계약은 검토 불가')
    _append(con, contract_id, 'owner_reviewed', checks, note)
    return get(con, database_path, contract_id)


def retire(con, database_path, contract_id, note):
    _text(note, '폐기 사유')
    contract = get(con, database_path, contract_id)
    if contract['state'] == 'RETIRED_DISCONNECTED':
        raise ValueError('이미 폐기된 계약입니다.')
    _append(con, contract_id, 'retired', {k: 'unverified' for k in CHECKS}, note)
    return get(con, database_path, contract_id)


def list_contracts(con, database_path, limit=100):
    if type(limit) is not int or not 1 <= limit <= 200:
        raise ValueError('조회 개수 1~200만 가능')
    rows = con.execute('SELECT id FROM local_sales_channel_contracts ORDER BY id DESC LIMIT ?',
                       (limit,)).fetchall()
    return [get(con, database_path, row[0]) for row in rows]
