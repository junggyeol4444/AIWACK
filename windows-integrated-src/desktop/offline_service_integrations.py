"""Stage59: local-only email/post/external-service integration *contracts*.

A deliberately non-transporting boundary.  There is no socket, HTTP, SMTP,
web browser, credential handling, plugin loading, or dispatch API in this module.
Owner-reviewed drafts are NOT permission to transmit. SQLite data is plaintext.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
import re
import sqlite3


@dataclass(frozen=True)
class ServiceContract:
    key: str
    kind: str
    operation: str
    planned_transport: str
    planned_auth: str
    planned_permissions: tuple[str, ...]
    planned_rate_limit_per_minute: int
    recovery_policy: str
    requires_owner_approval: bool = True
    connection_enabled: bool = False
    dispatch_enabled: bool = False
    credential_storage_enabled: bool = False


CONTRACTS = (
    ServiceContract('email', 'communication', 'send_message', 'SMTP or provider API (not implemented)',
                    'provider-specific OAuth/app password (not implemented)', ('send_email',), 10,
                    'manual review, no automatic retry'),
    ServiceContract('post', 'publishing', 'publish_content', 'platform API/browser (not implemented)',
                    'platform-scoped authorization (not implemented)', ('publish_post',), 5,
                    'manual review, no automatic repost'),
    ServiceContract('service', 'external', 'invoke_approved_operation', 'provider API (not implemented)',
                    'provider-scoped authorization (not implemented)', ('invoke_service',), 5,
                    'manual review, no automatic retry'),
)
_BY_KEY = {c.key: c for c in CONTRACTS}
_EMAIL = re.compile(r'^[A-Za-z0-9.!#$%&\'*+/=?^_`{|}~-]+@[A-Za-z0-9](?:[A-Za-z0-9.-]{0,251}[A-Za-z0-9])?\.[A-Za-z]{2,63}$')
_LOCAL_TARGET = re.compile(r'^[A-Za-z0-9_@][A-Za-z0-9_.@-]{0,119}$')
_SECRETS = re.compile(r'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----|authorization\s*:\s*bearer\s+\S+|\b(?:api[_-]?key|access[_-]?token|password)\s*[:=]\s*\S+', re.I)


def available_contracts() -> list[dict]:
    return [asdict(c) for c in CONTRACTS]


def _text(value: str, label: str, max_len: int) -> str:
    if not isinstance(value, str):
        raise ValueError(f'{label}은 문자열이어야 합니다.')
    value = value.strip()
    if not 1 <= len(value) <= max_len:
        raise ValueError(f'{label} 길이는 1~{max_len}자입니다.')
    if any(ord(c) < 32 and c not in '\n\t' for c in value) or '\x7f' in value:
        raise ValueError(f'{label}에 제어문자를 사용할 수 없습니다.')
    if _SECRETS.search(value):
        raise ValueError('비밀번호·토큰·비밀키처럼 보이는 내용은 로컬 초안에 저장하지 않습니다.')
    return value


def validate_draft(kind: str, target: str, title: str, body: str) -> dict:
    if not isinstance(kind, str) or kind not in _BY_KEY:
        raise ValueError('등록되지 않은 연동 유형입니다.')
    target = _text(target, '대상', 120)
    title = _text(title, '제목', 120)
    if '\n' in title or '\t' in title:
        raise ValueError('제목에는 줄바꿈·탭을 사용할 수 없습니다.')
    body = _text(body, '본문', 5000)
    if '\n' in target or '\r' in target or '\t' in target:
        raise ValueError('대상에는 줄바꿈·탭을 사용할 수 없습니다.')
    if kind == 'email':
        domain = target.rsplit('@', 1)[-1]
        if (not _EMAIL.fullmatch(target) or '..' in domain or
                any(part.startswith('-') or part.endswith('-') for part in domain.split('.'))):
            raise ValueError('이메일 대상은 단일 주소만 허용합니다.')
    elif not _LOCAL_TARGET.fullmatch(target) or '://' in target:
        raise ValueError('게시/서비스 대상은 로컬 식별자만 허용합니다. URL/경로는 금지합니다.')
    payload = {'kind': kind, 'target': target, 'title': title, 'body': body}
    digest = hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True,
                                       separators=(',', ':')).encode('utf-8')).hexdigest()
    return {**payload, 'sha256': digest}


def initialize(con: sqlite3.Connection) -> None:
    con.execute('''CREATE TABLE IF NOT EXISTS service_drafts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        kind TEXT NOT NULL CHECK(kind IN ('email','post','service')),
        target TEXT NOT NULL CHECK(length(target) BETWEEN 1 AND 120),
        title TEXT NOT NULL CHECK(length(title) BETWEEN 1 AND 120),
        body TEXT NOT NULL CHECK(length(body) BETWEEN 1 AND 5000),
        sha256 TEXT NOT NULL CHECK(length(sha256) = 64),
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    )''')
    con.execute('''CREATE TABLE IF NOT EXISTS service_draft_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        draft_id INTEGER NOT NULL REFERENCES service_drafts(id),
        action TEXT NOT NULL CHECK(action IN ('prepared','reviewed_local_only','rejected')),
        note TEXT NOT NULL DEFAULT '' CHECK(length(note) <= 200),
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    )''')
    con.execute('CREATE INDEX IF NOT EXISTS service_draft_events_by_draft ON service_draft_events(draft_id,id)')
    for table in ('service_drafts', 'service_draft_events'):
        for operation in ('UPDATE', 'DELETE'):
            con.execute(f'''CREATE TRIGGER IF NOT EXISTS {table}_no_{operation.lower()}
                BEFORE {operation} ON {table} BEGIN
                SELECT RAISE(ABORT,'service draft audit is append-only'); END''')


def prepare(con: sqlite3.Connection, kind: str, target: str, title: str, body: str) -> dict:
    draft = validate_draft(kind, target, title, body)
    cur = con.execute('''INSERT INTO service_drafts(kind,target,title,body,sha256)
                         VALUES (:kind,:target,:title,:body,:sha256)''', draft)
    draft_id = int(cur.lastrowid)
    con.execute('INSERT INTO service_draft_events(draft_id,action) VALUES (?,?)',
                (draft_id, 'prepared'))
    return {'id': draft_id, 'sha256': draft['sha256'], 'state': 'prepared',
            'transport_enabled': False}


def _get(con: sqlite3.Connection, draft_id: int) -> dict:
    if type(draft_id) is not int or draft_id <= 0:
        raise ValueError('유효한 초안 ID가 필요합니다.')
    con.row_factory = sqlite3.Row
    row = con.execute('SELECT * FROM service_drafts WHERE id=?', (draft_id,)).fetchone()
    if row is None:
        raise ValueError('초안이 없습니다.')
    draft = dict(row)
    valid = validate_draft(*(draft[k] for k in ('kind','target','title','body')))
    if valid['sha256'] != draft['sha256']:
        raise ValueError('저장된 초안 해시가 일치하지 않습니다.')
    events = [dict(r) for r in con.execute(
        'SELECT id,action,note,created_at FROM service_draft_events WHERE draft_id=? ORDER BY id',
        (draft_id,))]
    if not events or events[0]['action'] != 'prepared':
        raise ValueError('초안 감사 이력이 유효하지 않습니다.')
    draft['state'] = events[-1]['action']
    draft['events'] = events
    draft['transport_enabled'] = False
    return draft


def review(con: sqlite3.Connection, draft_id: int, accept: bool, note: str = '') -> dict:
    if type(accept) is not bool:
        raise ValueError('검토 여부는 불리언이어야 합니다.')
    if (not isinstance(note, str) or len(note) > 200 or _SECRETS.search(note) or
            any(ord(c) < 32 and c not in '\n\t' for c in note)):
        raise ValueError('검토 메모가 유효하지 않습니다.')
    draft = _get(con, draft_id)
    if draft['state'] != 'prepared':
        raise ValueError('이미 검토된 초안은 다시 검토할 수 없습니다.')
    action = 'reviewed_local_only' if accept else 'rejected'
    con.execute('INSERT INTO service_draft_events(draft_id,action,note) VALUES (?,?,?)',
                (draft_id, action, note))
    return {'id': draft_id, 'state': action, 'transport_enabled': False}


def detail(con: sqlite3.Connection, draft_id: int) -> dict:
    return _get(con, draft_id)


def history(con: sqlite3.Connection, limit: int = 50) -> list[dict]:
    if type(limit) is not int or not 1 <= limit <= 200:
        raise ValueError('조회 상한은 1~200입니다.')
    con.row_factory = sqlite3.Row
    rows = con.execute('''SELECT d.id,d.kind,d.target,d.title,d.sha256,d.created_at,
          (SELECT e.action FROM service_draft_events e WHERE e.draft_id=d.id
           ORDER BY e.id DESC LIMIT 1) AS state
          FROM service_drafts d ORDER BY d.id DESC LIMIT ?''', (limit,)).fetchall()
    return [dict(row, transport_enabled=False) for row in rows]
