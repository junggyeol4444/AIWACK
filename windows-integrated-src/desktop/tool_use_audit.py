"""Stage60: local append-only audit for selected tool boundaries and manual failure review.

No tools are executed by this module. No automatic retry, credentials, or
untrusted exception text are persisted. SQLite is NOT an adversarially secure log.
"""
from __future__ import annotations

import hashlib
import json
import re
import sqlite3

OPERATIONS = frozenset({'media_inspect', 'service_draft_prepare', 'service_draft_review'})
ERROR_CODES = frozenset({'none', 'validation', 'permission', 'filesystem', 'internal'})
_ACTIONS = frozenset({'acknowledged', 'resolved'})
_NOTE_SECRET = re.compile(r'-----BEGIN .*PRIVATE KEY|\b(?:password|api[_-]?key|access[_-]?token)\s*[:=]\s*\S+|authorization\s*:\s*bearer\s+\S+', re.I)


def _digest(payload: dict) -> str:
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True,
                                     separators=(',', ':')).encode('utf-8')).hexdigest()


def initialize(con: sqlite3.Connection) -> None:
    con.execute('''CREATE TABLE IF NOT EXISTS tool_use_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        operation TEXT NOT NULL CHECK(operation IN ('media_inspect','service_draft_prepare','service_draft_review')),
        outcome TEXT NOT NULL CHECK(outcome IN ('success','failure')),
        error_code TEXT NOT NULL CHECK(error_code IN ('none','validation','permission','filesystem','internal')),
        reference_id INTEGER CHECK(reference_id IS NULL OR reference_id > 0),
        summary TEXT NOT NULL CHECK(length(summary) BETWEEN 1 AND 160),
        digest TEXT NOT NULL CHECK(length(digest) = 64),
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        CHECK((outcome='success' AND error_code='none') OR (outcome='failure' AND error_code!='none'))
    )''')
    con.execute('''CREATE TABLE IF NOT EXISTS tool_failure_actions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        event_id INTEGER NOT NULL REFERENCES tool_use_events(id),
        action TEXT NOT NULL CHECK(action IN ('acknowledged','resolved')),
        note TEXT NOT NULL DEFAULT '' CHECK(length(note) <= 160),
        digest TEXT NOT NULL CHECK(length(digest) = 64),
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    )''')
    con.execute('CREATE INDEX IF NOT EXISTS tool_use_events_by_operation ON tool_use_events(operation,id)')
    con.execute('CREATE INDEX IF NOT EXISTS tool_failure_actions_by_event ON tool_failure_actions(event_id,id)')
    for table in ('tool_use_events', 'tool_failure_actions'):
        for operation in ('UPDATE', 'DELETE'):
            con.execute(f'''CREATE TRIGGER IF NOT EXISTS {table}_no_{operation.lower()}
                BEFORE {operation} ON {table} BEGIN
                SELECT RAISE(ABORT,'tool audit is append-only'); END''')


def classify(exc: Exception) -> str:
    # Deliberately do not persist str(exc), file paths, credentials, or tracebacks.
    if isinstance(exc, PermissionError):
        return 'permission'
    if isinstance(exc, ValueError):
        return 'validation'
    if isinstance(exc, OSError):
        return 'filesystem'
    return 'internal'


def record(con: sqlite3.Connection, operation: str, outcome: str,
           error_code: str = 'none', reference_id: int | None = None) -> int:
    if operation not in OPERATIONS or outcome not in ('success', 'failure') or error_code not in ERROR_CODES:
        raise ValueError('등록되지 않은 도구 작업/결과입니다.')
    if (outcome == 'success') != (error_code == 'none'):
        raise ValueError('성공/실패 코드가 일치하지 않습니다.')
    if reference_id is not None and (type(reference_id) is not int or reference_id < 1):
        raise ValueError('참조 ID가 유효하지 않습니다.')
    summary = f'{operation}: {outcome} ({error_code})'  # Fixed, safe text only.
    payload = dict(operation=operation, outcome=outcome, error_code=error_code,
                   reference_id=reference_id, summary=summary)
    cur = con.execute('''INSERT INTO tool_use_events(operation,outcome,error_code,reference_id,summary,digest)
                         VALUES (:operation,:outcome,:error_code,:reference_id,:summary,:digest)''',
                      {**payload, 'digest': _digest(payload)})
    return int(cur.lastrowid)


def _event(con: sqlite3.Connection, event_id: int) -> dict:
    if type(event_id) is not int or event_id < 1:
        raise ValueError('유효한 기록 ID가 필요합니다.')
    con.row_factory = sqlite3.Row
    row = con.execute('SELECT * FROM tool_use_events WHERE id=?', (event_id,)).fetchone()
    if row is None:
        raise ValueError('기록이 없습니다.')
    data = dict(row)
    payload = {key: data[key] for key in ('operation', 'outcome', 'error_code', 'reference_id', 'summary')}
    if (data['operation'] not in OPERATIONS or data['error_code'] not in ERROR_CODES or
        data['summary'] != f"{data['operation']}: {data['outcome']} ({data['error_code']})" or
        data['digest'] != _digest(payload)):
        raise ValueError('도구 사용 기록 무결성 오류')
    return data


def _note(note: str) -> str:
    if not isinstance(note, str) or len(note) > 160 or _NOTE_SECRET.search(note) or any(
        ord(c) < 32 or ord(c) == 127 for c in note
    ):
        raise ValueError('메모가 유효하지 않거나 비밀정보가 포함되었습니다.')
    return note


def failure_action(con: sqlite3.Connection, event_id: int, action: str, note: str = '') -> dict:
    if action not in _ACTIONS:
        raise ValueError('등록되지 않은 실패 처리 상태입니다.')
    note = _note(note)
    event = _event(con, event_id)
    if event['outcome'] != 'failure':
        raise ValueError('성공한 기록은 실패 처리할 수 없습니다.')
    previous = con.execute('SELECT action FROM tool_failure_actions WHERE event_id=? ORDER BY id DESC LIMIT 1',
                           (event_id,)).fetchone()
    if previous and (previous[0] == 'resolved' or previous[0] == action):
        raise ValueError('이미 처리된 상태입니다.')
    if action == 'resolved' and (not previous or previous[0] != 'acknowledged'):
        raise ValueError('확인 처리 후에만 해결 상태로 변경할 수 있습니다.')
    payload = dict(event_id=event_id, action=action, note=note)
    cur = con.execute('INSERT INTO tool_failure_actions(event_id,action,note,digest) VALUES (?,?,?,?)',
                      (event_id, action, note, _digest(payload)))
    return {'id': int(cur.lastrowid), 'event_id': event_id, 'action': action,
            'retry_executed': False}


def history(con: sqlite3.Connection, limit: int = 50) -> list[dict]:
    if type(limit) is not int or not 1 <= limit <= 200:
        raise ValueError('조회 개수는 1~200입니다.')
    con.row_factory = sqlite3.Row
    ids = [row[0] for row in con.execute('SELECT id FROM tool_use_events ORDER BY id DESC LIMIT ?', (limit,))]
    results = []
    for event_id in ids:
        item = _event(con, event_id)
        actions = con.execute('SELECT * FROM tool_failure_actions WHERE event_id=? ORDER BY id', (event_id,)).fetchall()
        state = 'unreviewed' if item['outcome'] == 'failure' else 'not_applicable'
        for row in actions:
            a = dict(row)
            if a['digest'] != _digest({key: a[key] for key in ('event_id', 'action', 'note')}):
                raise ValueError('실패 처리 이력 무결성 오류')
            if a['action'] not in _ACTIONS:
                raise ValueError('실패 처리 이력 상태 오류')
            state = a['action']
        item['review_state'] = state
        item['retry_executed'] = False
        results.append(item)
    return results
