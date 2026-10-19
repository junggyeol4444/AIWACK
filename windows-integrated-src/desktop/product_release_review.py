"""Stage69: local, owner-entered product prototype review; NEVER authorizes release.

The checklist is a record of *claims*, not independent quality assurance.  No
remote account, deployment, execution, payment or release capability exists.
"""
from __future__ import annotations

import json
import sqlite3

from desktop.business_portfolio import _hash, _id
from desktop.product_production import get as get_prototype

CHECKS = (
    'description_matches_intent', 'functional_test_evidence',
    'security_privacy_evidence', 'legal_rights_evidence',
    'accessibility_evidence', 'operational_readiness_evidence',
)
ANSWERS = ('unverified', 'needs_work', 'owner_reports_checked')
DECISIONS = ('HOLD_NO_RELEASE', 'REJECTED_NO_RELEASE')


def initialize(con: sqlite3.Connection) -> None:
    con.execute('''CREATE TABLE IF NOT EXISTS local_product_release_reviews (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        prototype_id INTEGER NOT NULL REFERENCES local_product_prototypes(id) ON DELETE RESTRICT,
        revision INTEGER NOT NULL CHECK(revision >= 1),
        prototype_sha256 TEXT NOT NULL CHECK(length(prototype_sha256)=64),
        catalog_version INTEGER NOT NULL CHECK(catalog_version > 0),
        checklist_json TEXT NOT NULL,
        reviewer_note TEXT NOT NULL CHECK(length(reviewer_note) <= 1000),
        decision TEXT NOT NULL CHECK(decision IN ('HOLD_NO_RELEASE','REJECTED_NO_RELEASE')),
        previous_digest TEXT NOT NULL,
        digest TEXT NOT NULL CHECK(length(digest)=64),
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(prototype_id, revision)
    )''')
    con.execute('''CREATE INDEX IF NOT EXISTS local_release_review_by_prototype
        ON local_product_release_reviews(prototype_id, revision)''')
    for op in ('UPDATE', 'DELETE'):
        con.execute(f'''CREATE TRIGGER IF NOT EXISTS local_release_reviews_no_{op.lower()}
            BEFORE {op} ON local_product_release_reviews BEGIN
            SELECT RAISE(ABORT, 'release review history is append-only'); END''')


def _validate_checklist(checklist: dict) -> dict:
    if type(checklist) is not dict or set(checklist) != set(CHECKS):
        raise ValueError('필수 검수 항목 6개가 정확히 필요합니다.')
    if any(type(checklist[k]) is not str or checklist[k] not in ANSWERS for k in CHECKS):
        raise ValueError('검수 상태는 미검증/보완 필요/관리자 확인 주장만 허용합니다.')
    return {k: checklist[k] for k in CHECKS}


def _payload(prototype_id: int, revision: int, sha: str, version: int,
             checklist: dict, note: str, decision: str, previous: str) -> dict:
    return {'prototype_id': prototype_id, 'revision': revision,
            'prototype_sha256': sha, 'catalog_version': version,
            'checklist': checklist, 'reviewer_note': note,
            'decision': decision, 'previous_digest': previous}


def history(con: sqlite3.Connection, database_path, prototype_id: int) -> list[dict]:
    _id(prototype_id, '시제품')
    prototype = get_prototype(con, database_path, prototype_id)
    con.row_factory = sqlite3.Row
    rows = con.execute('''SELECT * FROM local_product_release_reviews
        WHERE prototype_id=? ORDER BY revision''', (prototype_id,)).fetchall()
    previous = ''
    output = []
    for index, row in enumerate(rows, 1):
        try:
            checklist = json.loads(row['checklist_json'])
            checklist = _validate_checklist(checklist)
        except (ValueError, TypeError) as exc:
            raise ValueError('검수 감사 체크리스트 손상') from exc
        if (row['revision'] != index or row['previous_digest'] != previous or
            row['prototype_sha256'] != prototype['sha256'] or
            row['catalog_version'] != prototype['catalog_version'] or
            row['decision'] not in DECISIONS or
            type(row['reviewer_note']) is not str or
            len(row['reviewer_note']) > 1000):
            raise ValueError('검수 감사 연속성·원본 불일치')
        payload = _payload(prototype_id, index, row['prototype_sha256'],
                           row['catalog_version'], checklist, row['reviewer_note'],
                           row['decision'], previous)
        if row['digest'] != _hash(payload):
            raise ValueError('검수 감사 해시 불일치')
        previous = row['digest']
        output.append({'id': row['id'], **payload, 'digest': previous,
                       'created_at': row['created_at'],
                       'release_approved': False, 'quality_verified': False})
    return output


def record(con: sqlite3.Connection, database_path, prototype_id: int,
           checklist: dict, reviewer_note: str, decision: str = 'HOLD_NO_RELEASE') -> dict:
    checks = _validate_checklist(checklist)
    if type(reviewer_note) is not str or len(reviewer_note) > 1000:
        raise ValueError('관리자 검토 메모는 1000자 이내입니다.')
    if type(decision) is not str or decision not in DECISIONS:
        raise ValueError('실제 출시 승인은 지원하지 않습니다.')
    prototype = get_prototype(con, database_path, prototype_id)
    if prototype['state'] != 'review_requested':
        raise ValueError('검토 요청된 시제품만 기록할 수 있습니다.')
    if prototype['catalog_changed_since_build']:
        raise ValueError('카탈로그가 변경되어 이전 시제품 검토를 차단합니다.')
    past = history(con, database_path, prototype_id)
    revision = len(past) + 1
    previous = past[-1]['digest'] if past else ''
    payload = _payload(prototype_id, revision, prototype['sha256'],
                       prototype['catalog_version'], checks, reviewer_note,
                       decision, previous)
    digest = _hash(payload)
    con.execute('''INSERT INTO local_product_release_reviews
        (prototype_id,revision,prototype_sha256,catalog_version,checklist_json,
         reviewer_note,decision,previous_digest,digest) VALUES (?,?,?,?,?,?,?,?,?)''',
        (prototype_id, revision, prototype['sha256'], prototype['catalog_version'],
         json.dumps(checks, ensure_ascii=False, sort_keys=True, separators=(',', ':')),
         reviewer_note, decision, previous, digest))
    return history(con, database_path, prototype_id)[-1]


def summary(con: sqlite3.Connection, database_path, prototype_id: int) -> dict:
    prototype = get_prototype(con, database_path, prototype_id)
    rows = history(con, database_path, prototype_id)
    return {'prototype_id': prototype_id, 'review_count': len(rows),
            'latest_review': rows[-1] if rows else None,
            'artifact_integrity_checked': True,
            'catalog_changed_since_build': prototype['catalog_changed_since_build'],
            'release_approved': False, 'quality_verified': False,
            'deployment_performed': False, 'sales_performed': False,
            'decision': rows[-1]['decision'] if rows else 'HOLD_NO_RELEASE'}
