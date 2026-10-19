"""Stage70: offline-only service deployment/operations PLANNING, never deployment.

All records represent owner claims. No network, process launch, hosting, release,
order, payment, or monitoring daemon is provided. SQLite digests detect accidental
changes; they are not signatures or protection against an OS/database administrator.
"""
from __future__ import annotations

import json
import sqlite3

from desktop.business_portfolio import _hash, _id
from desktop.product_production import get as get_prototype
from desktop.product_release_review import history as release_history

ENVIRONMENTS = ('local_desktop_future', 'self_hosted_future', 'managed_hosting_future')
CHECKS = ('operator_assigned', 'backup_restore_plan', 'rollback_plan',
          'health_monitoring_plan', 'incident_response_plan')
ANSWERS = ('unverified', 'needs_work', 'owner_reports_prepared')
STATES = ('DRAFT_NO_DEPLOY', 'REVIEWED_NO_DEPLOY', 'RETIRED_NO_DEPLOY')
PLAN_FIELDS = ('id', 'prototype_id', 'release_review_digest', 'prototype_sha256',
               'catalog_version', 'environment', 'operations_note', 'backup_plan',
               'rollback_plan', 'monitoring_plan')


def initialize(con: sqlite3.Connection) -> None:
    con.execute('''CREATE TABLE IF NOT EXISTS local_service_operations_plans (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        prototype_id INTEGER NOT NULL REFERENCES local_product_prototypes(id) ON DELETE RESTRICT,
        release_review_digest TEXT NOT NULL CHECK(length(release_review_digest)=64),
        prototype_sha256 TEXT NOT NULL CHECK(length(prototype_sha256)=64),
        catalog_version INTEGER NOT NULL CHECK(catalog_version > 0),
        environment TEXT NOT NULL CHECK(environment IN
            ('local_desktop_future','self_hosted_future','managed_hosting_future')),
        operations_note TEXT NOT NULL CHECK(length(operations_note) BETWEEN 1 AND 500),
        backup_plan TEXT NOT NULL CHECK(length(backup_plan) BETWEEN 1 AND 500),
        rollback_plan TEXT NOT NULL CHECK(length(rollback_plan) BETWEEN 1 AND 500),
        monitoring_plan TEXT NOT NULL CHECK(length(monitoring_plan) BETWEEN 1 AND 500),
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    )''')
    con.execute('''CREATE TABLE IF NOT EXISTS local_service_operations_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        plan_id INTEGER NOT NULL REFERENCES local_service_operations_plans(id) ON DELETE RESTRICT,
        revision INTEGER NOT NULL CHECK(revision > 0),
        action TEXT NOT NULL CHECK(action IN ('created','readiness_recorded','retired')),
        checklist_json TEXT NOT NULL,
        note TEXT NOT NULL CHECK(length(note) <= 500),
        previous_digest TEXT NOT NULL,
        digest TEXT NOT NULL CHECK(length(digest)=64),
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(plan_id, revision)
    )''')
    con.execute('CREATE INDEX IF NOT EXISTS local_service_operations_events_by_plan ON local_service_operations_events(plan_id,revision)')
    for table in ('local_service_operations_plans', 'local_service_operations_events'):
        for op in ('UPDATE', 'DELETE'):
            con.execute(f'''CREATE TRIGGER IF NOT EXISTS {table}_no_{op.lower()}
                BEFORE {op} ON {table} BEGIN
                SELECT RAISE(ABORT, 'operations planning audit is append-only'); END''')


def _text(value: str, label: str, allow_empty: bool = False) -> str:
    if type(value) is not str or len(value) > 500 or (not allow_empty and not value.strip()) or '\x00' in value:
        raise ValueError(f'{label}: 1~500자 로컬 계획 문구가 필요합니다.')
    return value


def _checks(value: dict) -> dict:
    if type(value) is not dict or set(value) != set(CHECKS):
        raise ValueError('운영 준비 체크리스트 5개 항목이 필요합니다.')
    if any(type(value[k]) is not str or value[k] not in ANSWERS for k in CHECKS):
        raise ValueError('운영 준비 상태는 미검증/보완/관리자 주장만 허용합니다.')
    return {k: value[k] for k in CHECKS}


def _source(con: sqlite3.Connection, database_path, prototype_id: int):
    prototype = get_prototype(con, database_path, prototype_id)
    if prototype['state'] != 'review_requested' or prototype['catalog_changed_since_build']:
        raise ValueError('최신 카탈로그의 검토 요청 시제품만 운영 계획 가능')
    reviews = release_history(con, database_path, prototype_id)
    if not reviews or reviews[-1]['decision'] not in ('HOLD_NO_RELEASE', 'REJECTED_NO_RELEASE'):
        raise ValueError('Stage69 출시 보류 검토 기록이 필요합니다.')
    return prototype, reviews[-1]


def _plan_row(con: sqlite3.Connection, plan_id: int) -> dict:
    _id(plan_id, '운영 계획')
    con.row_factory = sqlite3.Row
    row = con.execute('SELECT * FROM local_service_operations_plans WHERE id=?', (plan_id,)).fetchone()
    if row is None:
        raise ValueError('운영 계획이 존재하지 않습니다.')
    return {k: row[k] for k in PLAN_FIELDS}


def _event_payload(plan_id: int, revision: int, action: str, checklist: dict,
                   note: str, previous_digest: str, plan_digest: str) -> dict:
    return {'plan_id': plan_id, 'revision': revision, 'action': action,
            'checklist': checklist, 'note': note, 'previous_digest': previous_digest,
            'plan_digest': plan_digest}


def _append(con: sqlite3.Connection, plan_id: int, action: str, checklist: dict, note: str) -> None:
    row = con.execute('''SELECT revision,digest FROM local_service_operations_events
        WHERE plan_id=? ORDER BY revision DESC LIMIT 1''', (plan_id,)).fetchone()
    revision, previous = (int(row[0]) + 1, row[1]) if row else (1, '')
    payload = _event_payload(plan_id, revision, action, checklist, note, previous,
                             _hash(_plan_row(con, plan_id)))
    con.execute('''INSERT INTO local_service_operations_events
        (plan_id,revision,action,checklist_json,note,previous_digest,digest)
        VALUES (?,?,?,?,?,?,?)''', (plan_id, revision, action,
        json.dumps(checklist, ensure_ascii=False, sort_keys=True, separators=(',', ':')),
        note, previous, _hash(payload)))


def history(con: sqlite3.Connection, database_path, plan_id: int) -> list[dict]:
    plan = _plan_row(con, plan_id)
    # Re-verify immutable source bytes, catalogue digest and prior review audit.
    prototype = get_prototype(con, database_path, plan['prototype_id'])
    reviews = release_history(con, database_path, plan['prototype_id'])
    if (prototype['sha256'] != plan['prototype_sha256'] or
        prototype['catalog_version'] != plan['catalog_version'] or
        plan['release_review_digest'] not in {r['digest'] for r in reviews}):
        raise ValueError('운영 계획의 시제품/검토 원본 불일치')
    if plan['environment'] not in ENVIRONMENTS or any(
        not isinstance(plan[k], str) or not plan[k].strip() or len(plan[k]) > 500
        for k in ('operations_note','backup_plan','rollback_plan','monitoring_plan')):
        raise ValueError('운영 계획 내용 손상')
    con.row_factory = sqlite3.Row
    rows = con.execute('''SELECT * FROM local_service_operations_events
        WHERE plan_id=? ORDER BY revision''', (plan_id,)).fetchall()
    if not rows:
        raise ValueError('운영 계획 감사 기록 누락')
    previous = ''
    output = []
    for index, row in enumerate(rows, 1):
        try:
            checks = _checks(json.loads(row['checklist_json']))
        except (ValueError, TypeError) as exc:
            raise ValueError('운영 준비 체크리스트 손상') from exc
        action = row['action']
        if (row['revision'] != index or row['previous_digest'] != previous or
            (index == 1 and (action != 'created' or any(v != 'unverified' for v in checks.values()))) or
            (index > 1 and action not in ('readiness_recorded', 'retired')) or
            (output and output[-1]['action'] == 'retired') or
            (action == 'retired' and any(v != 'unverified' for v in checks.values())) or
            type(row['note']) is not str or len(row['note']) > 500):
            raise ValueError('운영 계획 감사 연속성·상태 불일치')
        payload = _event_payload(plan_id, index, action, checks, row['note'], previous,
                                 _hash(plan))
        if _hash(payload) != row['digest']:
            raise ValueError('운영 계획 감사 해시 불일치')
        previous = row['digest']
        output.append({'id': row['id'], **payload, 'digest': previous,
                       'created_at': row['created_at']})
    return output


def get(con: sqlite3.Connection, database_path, plan_id: int) -> dict:
    plan = _plan_row(con, plan_id)
    events = history(con, database_path, plan_id)
    prototype = get_prototype(con, database_path, plan['prototype_id'])
    reviews = release_history(con, database_path, plan['prototype_id'])
    stale = (prototype['catalog_changed_since_build'] or
             prototype['state'] != 'review_requested' or
             reviews[-1]['digest'] != plan['release_review_digest'])
    latest = events[-1]
    state = ('RETIRED_NO_DEPLOY' if latest['action'] == 'retired' else
             'REVIEWED_NO_DEPLOY' if latest['action'] == 'readiness_recorded' else
             'DRAFT_NO_DEPLOY')
    return {**plan, 'state': state, 'stale_source': stale,
            'latest_checklist': latest['checklist'], 'event_count': len(events),
            'latest_digest': latest['digest'], 'deployment_performed': False,
            'service_running': False, 'release_approved': False, 'sales_performed': False}


def create(con: sqlite3.Connection, database_path, prototype_id: int,
           environment: str, operations_note: str, backup_plan: str,
           rollback_plan: str, monitoring_plan: str) -> dict:
    if type(environment) is not str or environment not in ENVIRONMENTS:
        raise ValueError('허용된 미래 배포 환경 계획만 등록 가능합니다.')
    fields = [_text(value, label) for value, label in zip(
        (operations_note, backup_plan, rollback_plan, monitoring_plan),
        ('운영 책임 계획', '백업 계획', '롤백 계획', '모니터링 계획'))]
    prototype, review = _source(con, database_path, prototype_id)
    cur = con.execute('''INSERT INTO local_service_operations_plans
        (prototype_id,release_review_digest,prototype_sha256,catalog_version,
         environment,operations_note,backup_plan,rollback_plan,monitoring_plan)
        VALUES (?,?,?,?,?,?,?,?,?)''', (prototype_id, review['digest'], prototype['sha256'],
        prototype['catalog_version'], environment, *fields))
    ident = int(cur.lastrowid)
    _append(con, ident, 'created', {k: 'unverified' for k in CHECKS}, '')
    return get(con, database_path, ident)


def record_readiness(con: sqlite3.Connection, database_path, plan_id: int,
                     checklist: dict, note: str) -> dict:
    checks = _checks(checklist)
    _text(note, '검토 메모', allow_empty=True)
    plan = get(con, database_path, plan_id)
    if plan['state'] == 'RETIRED_NO_DEPLOY' or plan['stale_source']:
        raise ValueError('폐기 또는 원본 변경된 운영 계획은 검토할 수 없습니다.')
    _append(con, plan_id, 'readiness_recorded', checks, note)
    return get(con, database_path, plan_id)


def retire(con: sqlite3.Connection, database_path, plan_id: int, note: str) -> dict:
    _text(note, '폐기 사유')
    plan = get(con, database_path, plan_id)
    if plan['state'] == 'RETIRED_NO_DEPLOY':
        raise ValueError('이미 폐기된 계획입니다.')
    _append(con, plan_id, 'retired', {k: 'unverified' for k in CHECKS}, note)
    return get(con, database_path, plan_id)


def list_plans(con: sqlite3.Connection, database_path, limit: int = 100) -> list[dict]:
    if type(limit) is not int or not 1 <= limit <= 200:
        raise ValueError('조회 개수는 1~200입니다.')
    ids = con.execute('SELECT id FROM local_service_operations_plans ORDER BY id DESC LIMIT ?',
                      (limit,)).fetchall()
    return [get(con, database_path, row[0]) for row in ids]
