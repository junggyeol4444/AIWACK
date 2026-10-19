"""Owner-entered, append-only manual notes on previously captured HTML link URLs.

Notes are local triage annotations, NEVER evidence of visiting or validating a site.
No HTTP, DNS, browser, subprocess, or file I/O is performed here.
"""
from __future__ import annotations

import sqlite3

from desktop.research_captures import validate_url

ACTIONS = frozenset({'noted', 'deferred', 'reopen'})
MAX_NOTE_LENGTH = 500
MAX_HISTORY = 20


def initialize(con: sqlite3.Connection) -> None:
    con.execute('''CREATE TABLE IF NOT EXISTS offline_research_followup_notes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        linked_url TEXT NOT NULL CHECK(length(linked_url) BETWEEN 8 AND 2048),
        action TEXT NOT NULL CHECK(action IN ('noted','deferred','reopen')),
        note TEXT NOT NULL CHECK(length(trim(note)) BETWEEN 1 AND 500),
        recorded_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    )''')
    con.execute('''CREATE INDEX IF NOT EXISTS idx_research_followup_notes_url_id
        ON offline_research_followup_notes(linked_url,id DESC)''')
    con.execute('''CREATE TRIGGER IF NOT EXISTS research_followup_notes_no_update
        BEFORE UPDATE ON offline_research_followup_notes BEGIN
        SELECT RAISE(ABORT,'manual follow-up history is append-only'); END''')
    con.execute('''CREATE TRIGGER IF NOT EXISTS research_followup_notes_no_delete
        BEFORE DELETE ON offline_research_followup_notes BEGIN
        SELECT RAISE(ABORT,'manual follow-up history cannot be deleted'); END''')


def _known_url(con: sqlite3.Connection, linked_url: str) -> str:
    url = validate_url(linked_url)
    # Exact stored URL match only. This does not verify remote existence.
    exists = con.execute('''SELECT 1 FROM offline_research_html_links
        WHERE linked_url=? LIMIT 1''', (url,)).fetchone()
    if exists is None:
        raise ValueError('저장된 HTML 링크 목록에 있는 URL만 수동 기록할 수 있습니다.')
    return url


def record_note(con: sqlite3.Connection, linked_url: str, action: str, note: str) -> int:
    if type(action) is not str or action not in ACTIONS:
        raise ValueError('올바른 수동 검토 동작을 선택해 주세요.')
    if (type(note) is not str or not 1 <= len(note.strip()) <= MAX_NOTE_LENGTH or
            any(ord(c) < 32 and c not in '\n\t' for c in note)):
        raise ValueError('검토 메모는 1~500자이며 제어문자를 포함할 수 없습니다.')
    url = _known_url(con, linked_url)
    return con.execute('''INSERT INTO offline_research_followup_notes(linked_url,action,note)
        VALUES(?,?,?)''', (url, action, note.strip())).lastrowid


def history(con: sqlite3.Connection, linked_url: str, limit: int = MAX_HISTORY) -> dict:
    if type(limit) is not int or not 1 <= limit <= MAX_HISTORY:
        raise ValueError('조회 범위는 1~20건입니다.')
    url = _known_url(con, linked_url)
    con.row_factory = sqlite3.Row
    records = con.execute('''SELECT id,action,note,recorded_at
        FROM offline_research_followup_notes WHERE linked_url=?
        ORDER BY id DESC LIMIT ?''', (url, limit + 1)).fetchall()
    return {'linked_url': url, 'items': [dict(r) for r in records[:limit]],
            'truncated': len(records) > limit,
            'source_authenticity_verified': False, 'network_accessed': False}


def latest_for_urls(con: sqlite3.Connection, urls: list[str]) -> dict[str, dict]:
    """Attach only latest annotations for displayed URLs; <=40 bind parameters."""
    if not urls:
        return {}
    if len(urls) > 40:
        raise ValueError('표시 URL은 최대 40개입니다.')
    placeholders = ','.join('?' for _ in urls)
    con.row_factory = sqlite3.Row
    rows = con.execute(f'''SELECT linked_url,action,note,recorded_at
        FROM offline_research_followup_notes WHERE id IN
        (SELECT MAX(id) FROM offline_research_followup_notes
         WHERE linked_url IN ({placeholders}) GROUP BY linked_url)''', urls).fetchall()
    return {r['linked_url']: dict(r) for r in rows}


def latest_actions_for_queue(con: sqlite3.Connection, urls: list[str]) -> dict[str, str]:
    """Read latest *manual* triage actions for a bounded URL inventory.

    Process in chunks for older SQLite builds with low bind-variable limits.
    The result does not indicate that any website was visited or verified.
    """
    if type(urls) is not list or len(urls) > 2000 or any(type(url) is not str for url in urls):
        raise ValueError('수동 검토 상태 조회는 최대 2,000개 URL만 허용합니다.')
    actions: dict[str, str] = {}
    for offset in range(0, len(urls), 250):
        chunk = urls[offset:offset + 250]
        placeholders = ','.join('?' for _ in chunk)
        rows = con.execute(f'''SELECT linked_url,action
            FROM offline_research_followup_notes WHERE id IN
            (SELECT MAX(id) FROM offline_research_followup_notes
             WHERE linked_url IN ({placeholders}) GROUP BY linked_url)''', chunk).fetchall()
        for row in rows:
            actions[row[0]] = row[1]
    return actions
