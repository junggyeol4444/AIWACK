"""Stage63: owner-curated OFFLINE demand/competition evidence review.

Links local Stage62 hypotheses to manually captured Stage54 source excerpts.
No fetching, scraping, LLM, factual verification, market sizing or revenue estimate.
Source URLs and excerpts are user claims, not independently authenticated facts.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3

from desktop.business_portfolio import _hash, _id, _label

KINDS = frozenset({'demand', 'competition'})
STANCES = frozenset({'supports', 'challenges', 'context'})
REVIEWS = frozenset({'unreviewed', 'noted', 'excluded'})


_AIWACK_VALIDATION_311_IMMUTABLE = 'OLD.candidate_id IS NOT NEW.candidate_id\n          OR OLD.capture_id IS NOT NEW.capture_id OR OLD.kind IS NOT NEW.kind\n          OR OLD.stance IS NOT NEW.stance OR OLD.excerpt IS NOT NEW.excerpt\n          OR OLD.analyst_note IS NOT NEW.analyst_note OR OLD.source_digest IS NOT NEW.source_digest\n          OR OLD.link_digest IS NOT NEW.link_digest OR OLD.created_at IS NOT NEW.created_at'


def initialize(con: sqlite3.Connection) -> None:
    con.execute('''CREATE TABLE IF NOT EXISTS market_evidence_links (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      candidate_id INTEGER NOT NULL REFERENCES opportunity_candidates(id) ON DELETE RESTRICT,
      capture_id INTEGER NOT NULL REFERENCES offline_research_captures(id) ON DELETE RESTRICT,
      kind TEXT NOT NULL CHECK(kind IN ('demand','competition')),
      stance TEXT NOT NULL CHECK(stance IN ('supports','challenges','context')),
      excerpt TEXT NOT NULL CHECK(length(excerpt) BETWEEN 8 AND 240),
      analyst_note TEXT NOT NULL CHECK(length(analyst_note) BETWEEN 1 AND 300),
      source_digest TEXT NOT NULL CHECK(length(source_digest)=64),
      link_digest TEXT NOT NULL UNIQUE CHECK(length(link_digest)=64),
      review TEXT NOT NULL DEFAULT 'unreviewed'
        CHECK(review IN ('unreviewed','noted','excluded')),
      created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    )''')
    con.execute('''CREATE TABLE IF NOT EXISTS market_evidence_events (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      link_id INTEGER NOT NULL REFERENCES market_evidence_links(id) ON DELETE RESTRICT,
      action TEXT NOT NULL CHECK(action IN ('linked','review_changed')),
      detail TEXT NOT NULL CHECK(length(detail) BETWEEN 2 AND 700),
      digest TEXT NOT NULL CHECK(length(digest)=64),
      created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    )''')
    con.execute('CREATE INDEX IF NOT EXISTS market_evidence_candidate_idx ON market_evidence_links(candidate_id,id)')
    con.execute('CREATE INDEX IF NOT EXISTS market_evidence_events_link_idx ON market_evidence_events(link_id,id)')
    for op in ('UPDATE', 'DELETE'):
        con.execute(f'''CREATE TRIGGER IF NOT EXISTS market_evidence_events_no_{op.lower()}
          BEFORE {op} ON market_evidence_events BEGIN
          SELECT RAISE(ABORT,'market evidence events are append-only'); END''')
        con.execute(f'''CREATE TRIGGER IF NOT EXISTS market_evidence_links_no_{op.lower()}_content
          BEFORE {op} ON market_evidence_links BEGIN
          SELECT RAISE(ABORT,'market evidence links are immutable except review')
          WHERE {'1=1' if op == 'DELETE' else _AIWACK_VALIDATION_311_IMMUTABLE};
          END''')


def _event(con: sqlite3.Connection, link_id: int, action: str, payload: dict) -> None:
    detail = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(',', ':'))
    con.execute('INSERT INTO market_evidence_events(link_id,action,detail,digest) VALUES(?,?,?,?)',
                (link_id, action, detail, _hash(payload)))


def _capture(con: sqlite3.Connection, capture_id: int) -> dict:
    _id(capture_id, '자료')
    con.row_factory = sqlite3.Row
    row = con.execute('''SELECT id,title,source_url,body,content_sha256,source_verification,archived_at
      FROM offline_research_captures WHERE id=?''', (capture_id,)).fetchone()
    if row is None:
        raise ValueError('등록된 로컬 자료가 없습니다.')
    data = dict(row)
    actual = hashlib.sha256(data['body'].encode('utf-8')).hexdigest()
    if actual != data['content_sha256']:
        raise ValueError('로컬 자료 본문 무결성 오류')
    if data['source_verification'] != 'unverified':
        raise ValueError('예상하지 못한 출처 검증 상태')
    return data


def link(con: sqlite3.Connection, candidate_id: int, capture_id: int,
         kind: str, stance: str, excerpt: str, note: str) -> int:
    _id(candidate_id, '후보')
    if not isinstance(kind, str) or kind not in KINDS:
        raise ValueError('조사 범주는 수요/경쟁만 허용합니다.')
    if not isinstance(stance, str) or stance not in STANCES:
        raise ValueError('근거 방향이 유효하지 않습니다.')
    if any(isinstance(text, str) and any(ord(ch) < 32 or ord(ch) == 127 for ch in text)
           for text in (excerpt, note)):
        raise ValueError('줄바꿈 및 제어 문자는 허용되지 않습니다.')
    excerpt = _label(excerpt, '원문 발췌', 240)
    if len(excerpt) < 8:
        raise ValueError('발췌는 8자 이상이어야 합니다.')
    note = _label(note, '관리자 검토 메모', 300)
    if con.execute('SELECT 1 FROM opportunity_candidates WHERE id=?', (candidate_id,)).fetchone() is None:
        raise ValueError('사업 후보가 없습니다.')
    source = _capture(con, capture_id)
    if excerpt not in source['body']:
        raise ValueError('발췌문이 로컬 원문에 정확히 존재하지 않습니다.')
    if con.execute('SELECT COUNT(*) FROM market_evidence_links WHERE candidate_id=?',
                   (candidate_id,)).fetchone()[0] >= 100:
        raise ValueError('후보별 근거 연결은 최대 100개입니다.')
    fingerprint = _hash({'candidate_id': candidate_id, 'capture_id': capture_id,
                         'kind': kind, 'stance': stance, 'excerpt': excerpt})
    try:
        cur = con.execute('''INSERT INTO market_evidence_links
          (candidate_id,capture_id,kind,stance,excerpt,analyst_note,source_digest,link_digest)
          VALUES(?,?,?,?,?,?,?,?)''',
          (candidate_id, capture_id, kind, stance, excerpt, note,
           source['content_sha256'], fingerprint))
    except sqlite3.IntegrityError as exc:
        raise ValueError('동일한 원문 발췌·방향이 이미 연결되어 있습니다.') from exc
    link_id = int(cur.lastrowid)
    _event(con, link_id, 'linked', {'candidate_id': candidate_id, 'capture_id': capture_id,
                                   'kind': kind, 'stance': stance, 'source_digest': source['content_sha256']})
    return link_id


def review(con: sqlite3.Connection, link_id: int, new_state: str) -> dict:
    _id(link_id, '근거 연결')
    if not isinstance(new_state, str) or new_state not in REVIEWS:
        raise ValueError('검토 상태가 유효하지 않습니다.')
    row = con.execute('SELECT review FROM market_evidence_links WHERE id=?', (link_id,)).fetchone()
    if row is None or row[0] == new_state:
        raise ValueError('연결이 없거나 이미 같은 검토 상태입니다.')
    if con.execute('SELECT COUNT(*) FROM market_evidence_events WHERE link_id=?',
                   (link_id,)).fetchone()[0] >= 100:
        raise ValueError('근거별 검토 변경 한도(99회)에 도달했습니다.')
    con.execute('UPDATE market_evidence_links SET review=? WHERE id=?', (new_state, link_id))
    _event(con, link_id, 'review_changed', {'old': row[0], 'new': new_state})
    return {'id': link_id, 'review': new_state, 'source_verified': False}


def events(con: sqlite3.Connection, link_id: int, limit: int = 100) -> list[dict]:
    _id(link_id, '근거 연결')
    if type(limit) is not int or not 1 <= limit <= 200:
        raise ValueError('조회 개수는 1~200입니다.')
    if con.execute('SELECT 1 FROM market_evidence_links WHERE id=?', (link_id,)).fetchone() is None:
        raise ValueError('근거 연결이 없습니다.')
    con.row_factory = sqlite3.Row
    rows = []
    for row in con.execute('''SELECT * FROM market_evidence_events
        WHERE link_id=? ORDER BY id DESC LIMIT ?''', (link_id, limit)):
        item = dict(row)
        try:
            payload = json.loads(item['detail'])
        except (ValueError, TypeError) as exc:
            raise ValueError('감사 이벤트 JSON 손상') from exc
        if not isinstance(payload, dict) or _hash(payload) != item['digest']:
            raise ValueError('감사 이벤트 무결성 오류')
        rows.append(item)
    return rows


def evidence(con: sqlite3.Connection, candidate_id: int, limit: int = 100) -> list[dict]:
    _id(candidate_id, '후보')
    if type(limit) is not int or not 1 <= limit <= 100:
        raise ValueError('조회 개수는 1~100입니다.')
    if con.execute('SELECT 1 FROM opportunity_candidates WHERE id=?', (candidate_id,)).fetchone() is None:
        raise ValueError('사업 후보가 없습니다.')
    con.row_factory = sqlite3.Row
    result = []
    for row in con.execute('''SELECT e.*,r.title AS source_title,r.source_url,r.archived_at
       FROM market_evidence_links e JOIN offline_research_captures r ON r.id=e.capture_id
       WHERE e.candidate_id=? ORDER BY e.id DESC LIMIT ?''', (candidate_id, limit)):
        item = dict(row)
        source = _capture(con, item['capture_id'])
        if item['source_digest'] != source['content_sha256'] or item['excerpt'] not in source['body']:
            raise ValueError('근거 원문 또는 발췌 무결성 오류')
        expected = _hash({'candidate_id': item['candidate_id'], 'capture_id': item['capture_id'],
                          'kind': item['kind'], 'stance': item['stance'], 'excerpt': item['excerpt']})
        if item['link_digest'] != expected:
            raise ValueError('근거 연결 무결성 오류')
        # Check audit event history, including last recorded review state.
        history = events(con, item['id'])
        if not history or history[-1]['action'] != 'linked':
            raise ValueError('근거 연결 감사 기록 누락')
        state = 'unreviewed'
        for event in reversed(history):
            if event['action'] == 'review_changed':
                payload = json.loads(event['detail'])
                if payload['old'] != state or payload['new'] not in REVIEWS:
                    raise ValueError('근거 검토 이력 불일치')
                state = payload['new']
        if state != item['review']:
            raise ValueError('근거 검토 상태 불일치')
        item['source_verified'] = False
        result.append(item)
    return result


def summary(con: sqlite3.Connection, candidate_id: int) -> dict:
    """Coverage checklist, NOT proof of demand or competition.

    Repeated excerpts from one captured document never count as independent
    sources. Distinct captures can still be controlled by one claimant.
    """
    items = evidence(con, candidate_id)
    usable = [x for x in items if x['review'] == 'noted']
    categories = {}
    for kind in ('demand', 'competition'):
        selected = [x for x in usable if x['kind'] == kind]
        categories[kind] = {'reviewed_links': len(selected),
                            'local_capture_count': len({x['capture_id'] for x in selected}),
                            'supporting_claims': sum(x['stance'] == 'supports' for x in selected),
                            'challenging_claims': sum(x['stance'] == 'challenges' for x in selected),
                            'missing_local_material': not bool(selected)}
    return {'candidate_id': candidate_id, 'total_links': len(items),
            'unreviewed_links': sum(x['review'] == 'unreviewed' for x in items),
            'excluded_links': sum(x['review'] == 'excluded' for x in items),
            'categories': categories, 'market_demand_verified': False,
            'competition_verified': False, 'source_authenticity_verified': False,
            'independent_sources_verified': False, 'external_actions_executed': False,
            'warning': '관리자 제공 로컬 자료의 검토 현황일 뿐, 실제 시장조사·수요·경쟁 검증이 아닙니다.'}
