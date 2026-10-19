"""Stage62: local, deterministic business *hypothesis* generator.

No demand discovery, market evidence, profitability prediction, model call,
network access, autonomous business launch, or transaction occurs here.
User-entered audience/problem + registered types produce UNVERIFIED drafts.
SQLite history is append-only at the application DB level, not tamper-proof.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3

from desktop.business_portfolio import _label, _id, _hash

_STATES = {'draft', 'shortlisted', 'rejected'}
_ALLOWED = {'draft': {'shortlisted', 'rejected'}, 'shortlisted': {'rejected', 'draft'}, 'rejected': {'draft'}}


def initialize(con: sqlite3.Connection) -> None:
    con.execute('''CREATE TABLE IF NOT EXISTS opportunity_runs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        input_digest TEXT NOT NULL CHECK(length(input_digest)=64),
        proposed INTEGER NOT NULL CHECK(proposed BETWEEN 0 AND 20),
        skipped INTEGER NOT NULL CHECK(skipped BETWEEN 0 AND 20),
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    )''')
    con.execute('''CREATE TABLE IF NOT EXISTS opportunity_candidates (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        run_id INTEGER NOT NULL REFERENCES opportunity_runs(id) ON DELETE RESTRICT,
        type_id INTEGER NOT NULL REFERENCES business_types(id) ON DELETE RESTRICT,
        audience TEXT NOT NULL CHECK(length(audience) BETWEEN 1 AND 120),
        problem TEXT NOT NULL CHECK(length(problem) BETWEEN 1 AND 240),
        hypothesis TEXT NOT NULL CHECK(length(hypothesis) BETWEEN 1 AND 500),
        candidate_key TEXT NOT NULL UNIQUE CHECK(length(candidate_key)=64),
        source_kind TEXT NOT NULL DEFAULT 'owner_input_unverified'
          CHECK(source_kind='owner_input_unverified'),
        state TEXT NOT NULL DEFAULT 'draft' CHECK(state IN ('draft','shortlisted','rejected')),
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    )''')
    con.execute('''CREATE TABLE IF NOT EXISTS opportunity_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        candidate_id INTEGER NOT NULL REFERENCES opportunity_candidates(id) ON DELETE RESTRICT,
        action TEXT NOT NULL CHECK(action IN ('proposed','state_changed')),
        detail TEXT NOT NULL CHECK(length(detail) BETWEEN 2 AND 700),
        digest TEXT NOT NULL CHECK(length(digest)=64),
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    )''')
    con.execute('CREATE INDEX IF NOT EXISTS opportunity_by_state ON opportunity_candidates(state,id)')
    con.execute('CREATE INDEX IF NOT EXISTS opportunity_events_candidate ON opportunity_events(candidate_id,id)')
    for op in ('UPDATE', 'DELETE'):
        con.execute(f'''CREATE TRIGGER IF NOT EXISTS opportunity_events_no_{op.lower()}
            BEFORE {op} ON opportunity_events BEGIN
            SELECT RAISE(ABORT,'opportunity events are append-only'); END''')
        con.execute(f'''CREATE TRIGGER IF NOT EXISTS opportunity_runs_no_{op.lower()}
            BEFORE {op} ON opportunity_runs BEGIN
            SELECT RAISE(ABORT,'opportunity runs are append-only'); END''')


def _event(con: sqlite3.Connection, candidate_id: int, action: str, payload: dict) -> None:
    detail = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(',', ':'))
    con.execute('INSERT INTO opportunity_events(candidate_id,action,detail,digest) VALUES (?,?,?,?)',
                (candidate_id, action, detail, _hash(payload)))


def _candidate_key(type_id: int, audience: str, problem: str) -> str:
    canonical = json.dumps([type_id, ' '.join(audience.casefold().split()),
                            ' '.join(problem.casefold().split())], ensure_ascii=False)
    return hashlib.sha256(canonical.encode('utf-8')).hexdigest()


def generate(con: sqlite3.Connection, audience: str, problem: str, max_candidates: int = 8) -> dict:
    """Produce hypotheses from *user input*, not validated market opportunities.

    Caller must use one SQLite transaction; a failed insert rolls it all back.
    """
    audience = _label(audience, '대상 고객', 120)
    problem = _label(problem, '가정한 고객 문제', 240)
    if type(max_candidates) is not int or not 1 <= max_candidates <= 20:
        raise ValueError('후보 생성 수는 1~20 정수여야 합니다.')
    active = con.execute('''SELECT id,title FROM business_types WHERE enabled=1
                            ORDER BY id LIMIT ?''', (max_candidates,)).fetchall()
    if not active:
        raise ValueError('활성 사업 유형이 없습니다.')
    # Digest is a fingerprint, not independent evidence or a verified source.
    fingerprint = _hash({'audience': audience, 'problem': problem, 'max_candidates': max_candidates})
    proposals = []
    skipped = 0
    for type_id, title in active:
        key = _candidate_key(type_id, audience, problem)
        if con.execute('SELECT 1 FROM opportunity_candidates WHERE candidate_key=?', (key,)).fetchone():
            skipped += 1
            continue
        hypothesis = (f'{title} 방식으로 {audience}의 문제 「{problem}」를 해결하는 '
                      '최소 제품·서비스 가설. 수요·경쟁·비용·매출은 조사되지 않았음.')
        if len(hypothesis) > 500:
            raise ValueError('후보 설명이 너무 깁니다.')
        proposals.append((type_id, hypothesis, key))
    # Insert finalized run counts once, so the audit trigger never needs bypass.
    run = con.execute('INSERT INTO opportunity_runs(input_digest,proposed,skipped) VALUES (?,?,?)',
                      (fingerprint, len(proposals), skipped))
    run_id = int(run.lastrowid)
    ids: list[int] = []
    for type_id, hypothesis, key in proposals:
        cur = con.execute('INSERT INTO opportunity_candidates '
                          '(run_id,type_id,audience,problem,hypothesis,candidate_key) '
                          'VALUES (?,?,?,?,?,?)',
                          (run_id, type_id, audience, problem, hypothesis, key))
        cid = int(cur.lastrowid)
        _event(con, cid, 'proposed', {'run_id': run_id, 'type_id': type_id,
                                     'source_kind': 'owner_input_unverified'})
        ids.append(cid)
    return {'run_id': run_id, 'created_ids': ids, 'skipped_duplicates': skipped,
            'verified_market_data': False, 'external_actions_executed': False}


def candidates(con: sqlite3.Connection, state: str | None = None, limit: int = 100) -> list[dict]:
    if state is not None and (not isinstance(state, str) or state not in _STATES):
        raise ValueError('후보 상태가 유효하지 않습니다.')
    if type(limit) is not int or not 1 <= limit <= 500:
        raise ValueError('조회 제한이 유효하지 않습니다.')
    con.row_factory = sqlite3.Row
    sql = '''SELECT c.id,c.run_id,c.type_id,t.title AS type_title,c.audience,c.problem,
         c.hypothesis,c.source_kind,c.state,c.created_at
         FROM opportunity_candidates c JOIN business_types t ON t.id=c.type_id'''
    args: tuple = ()
    if state is not None:
        sql += ' WHERE c.state=?'
        args = (state,)
    return [dict(row) for row in con.execute(sql + ' ORDER BY c.id DESC LIMIT ?', args + (limit,))]


def change_state(con: sqlite3.Connection, candidate_id: int, new_state: str) -> dict:
    _id(candidate_id, '후보')
    if not isinstance(new_state, str) or new_state not in _STATES:
        raise ValueError('후보 상태가 유효하지 않습니다.')
    row = con.execute('SELECT state FROM opportunity_candidates WHERE id=?', (candidate_id,)).fetchone()
    if row is None:
        raise ValueError('후보가 없습니다.')
    old = row[0]
    if new_state not in _ALLOWED[old]:
        raise ValueError('동일 상태로 변경할 수 없습니다.')
    con.execute('UPDATE opportunity_candidates SET state=? WHERE id=?', (new_state, candidate_id))
    _event(con, candidate_id, 'state_changed', {'old': old, 'new': new_state})
    return {'id': candidate_id, 'state': new_state, 'external_actions_executed': False}


def events(con: sqlite3.Connection, candidate_id: int, limit: int = 100) -> list[dict]:
    _id(candidate_id, '후보')
    if type(limit) is not int or not 1 <= limit <= 500:
        raise ValueError('조회 제한이 유효하지 않습니다.')
    if not con.execute('SELECT 1 FROM opportunity_candidates WHERE id=?', (candidate_id,)).fetchone():
        raise ValueError('후보가 없습니다.')
    con.row_factory = sqlite3.Row
    result = []
    for row in con.execute('SELECT * FROM opportunity_events WHERE candidate_id=? ORDER BY id DESC LIMIT ?',
                           (candidate_id, limit)):
        data = dict(row)
        try:
            payload = json.loads(data['detail'])
        except (ValueError, TypeError) as exc:
            raise ValueError('후보 감사 기록 JSON 손상') from exc
        if not isinstance(payload, dict) or _hash(payload) != data['digest']:
            raise ValueError('후보 감사 기록 무결성 오류')
        result.append(data)
    return result


def runs(con: sqlite3.Connection, limit: int = 50) -> list[dict]:
    if type(limit) is not int or not 1 <= limit <= 500:
        raise ValueError('조회 제한이 유효하지 않습니다.')
    con.row_factory = sqlite3.Row
    return [dict(row) for row in con.execute(
        'SELECT * FROM opportunity_runs ORDER BY id DESC LIMIT ?', (limit,))]
