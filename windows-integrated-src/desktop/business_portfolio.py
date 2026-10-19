"""Stage61: generic local business-type and multi-business registry.

Planning metadata only. No revenue, transactions, account connections, external
calls, staff execution or autonomous decisions. The local SQLite DB is plaintext;
append-only event rows are an audit aid, not a tamper-proof security boundary.
"""
from __future__ import annotations

import hashlib
import json
import re
import sqlite3

# Examples from original specification §4.2, not an allowlist: custom types work.
EXAMPLE_TYPES = (
    ('software', '소프트웨어·프로그램 판매'),
    ('web_service', '웹사이트·온라인 서비스'),
    ('saas', 'SaaS 구독 서비스'),
    ('digital_goods', '디지털 상품 제작·판매'),
    ('content_ads', '콘텐츠·광고'),
    ('media_production', '영상·이미지·음악 제작'),
    ('ebook_documents', '전자책·문서 상품'),
    ('ai_assistance', 'AI 업무 대행'),
    ('automation', '자동화 프로그램'),
    ('data_analysis', '데이터 분석'),
    ('b2b_software', '기업 대상 소프트웨어'),
    ('online_education', '온라인 교육 콘텐츠'),
    ('design_products', '디자인 상품'),
    ('other_online', '기타 온라인 사업'),
)
_KEY = re.compile(r'[a-z][a-z0-9_]{2,47}\Z')
_STATES = frozenset({'draft', 'active', 'paused', 'closed'})
_TRANSITIONS = {'draft': {'active', 'closed'}, 'active': {'paused', 'closed'},
                'paused': {'active', 'closed'}, 'closed': set()}
_SECRET = re.compile(r'-----BEGIN .*PRIVATE KEY|\b(?:password|api[_-]?key|access[_-]?token)\s*[:=]\s*\S+|authorization\s*:\s*bearer\s+\S+', re.I)


def _label(value: str, field: str, max_len: int) -> str:
    if not isinstance(value, str):
        raise ValueError(f'{field}은 문자열이어야 합니다.')
    value = value.strip()
    if not 1 <= len(value) <= max_len or _SECRET.search(value) or any(
        ord(ch) < 32 or ord(ch) == 127 for ch in value
    ):
        raise ValueError(f'{field} 길이/내용이 유효하지 않습니다.')
    return value


def _id(value: int, label: str) -> int:
    if type(value) is not int or value < 1:
        raise ValueError(f'{label} ID가 유효하지 않습니다.')
    return value


def _hash(payload: dict) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False,
                                     separators=(',', ':')).encode('utf-8')).hexdigest()


def initialize(con: sqlite3.Connection) -> None:
    con.execute('''CREATE TABLE IF NOT EXISTS business_types (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        type_key TEXT NOT NULL COLLATE NOCASE UNIQUE,
        title TEXT NOT NULL CHECK(length(title) BETWEEN 1 AND 100),
        description TEXT NOT NULL DEFAULT '' CHECK(length(description) <= 300),
        built_in INTEGER NOT NULL DEFAULT 0 CHECK(built_in IN (0,1)),
        enabled INTEGER NOT NULL DEFAULT 1 CHECK(enabled IN (0,1)),
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    )''')
    con.execute('''CREATE TABLE IF NOT EXISTS managed_businesses (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        type_id INTEGER NOT NULL REFERENCES business_types(id) ON DELETE RESTRICT,
        name TEXT NOT NULL CHECK(length(name) BETWEEN 1 AND 120),
        goal TEXT NOT NULL CHECK(length(goal) BETWEEN 1 AND 500),
        budget_krw INTEGER NOT NULL DEFAULT 0 CHECK(budget_krw BETWEEN 0 AND 1000000000000),
        owner_employee_id INTEGER REFERENCES ai_employee_profiles(id) ON DELETE RESTRICT,
        state TEXT NOT NULL DEFAULT 'draft' CHECK(state IN ('draft','active','paused','closed')),
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    )''')
    con.execute('''CREATE TABLE IF NOT EXISTS business_participants (
        business_id INTEGER NOT NULL REFERENCES managed_businesses(id) ON DELETE RESTRICT,
        employee_id INTEGER NOT NULL REFERENCES ai_employee_profiles(id) ON DELETE RESTRICT,
        assigned_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY(business_id, employee_id)
    )''')
    con.execute('''CREATE TABLE IF NOT EXISTS business_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        business_id INTEGER REFERENCES managed_businesses(id) ON DELETE RESTRICT,
        type_id INTEGER REFERENCES business_types(id) ON DELETE RESTRICT,
        action TEXT NOT NULL CHECK(action IN
          ('type_added','type_disabled','business_added','state_changed','participant_added','participant_removed')),
        detail TEXT NOT NULL CHECK(length(detail) BETWEEN 2 AND 1200),
        digest TEXT NOT NULL CHECK(length(digest) = 64),
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        CHECK(business_id IS NOT NULL OR type_id IS NOT NULL)
    )''')
    con.execute('CREATE INDEX IF NOT EXISTS managed_businesses_by_type ON managed_businesses(type_id,state)')
    con.execute('CREATE INDEX IF NOT EXISTS business_events_by_business ON business_events(business_id,id)')
    for op in ('UPDATE', 'DELETE'):
        con.execute(f'''CREATE TRIGGER IF NOT EXISTS business_events_no_{op.lower()}
          BEFORE {op} ON business_events BEGIN
          SELECT RAISE(ABORT, 'business event log is append-only'); END''')
    # Seed only at first initialization; never re-enable owner-disabled templates.
    con.executemany('INSERT OR IGNORE INTO business_types(type_key,title,built_in) VALUES (?,?,1)', EXAMPLE_TYPES)


def _event(con: sqlite3.Connection, action: str, payload: dict,
           business_id: int | None = None, type_id: int | None = None) -> None:
    detail = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(',', ':'))
    if len(detail) > 1200:
        raise ValueError('감사 기록이 너무 깁니다.')
    con.execute('INSERT INTO business_events(business_id,type_id,action,detail,digest) VALUES (?,?,?,?,?)',
                (business_id, type_id, action, detail, _hash(payload)))


def add_type(con: sqlite3.Connection, type_key: str, title: str, description: str = '') -> int:
    if not isinstance(type_key, str) or not _KEY.fullmatch(type_key):
        raise ValueError('사업 유형 키는 소문자 영문·숫자·밑줄 3~48자입니다.')
    title = _label(title, '사업 유형명', 100)
    if not isinstance(description, str) or len(description) > 300 or _SECRET.search(description) or any(
        ord(c) < 32 or ord(c) == 127 for c in description
    ):
        raise ValueError('설명이 유효하지 않습니다.')
    try:
        row = con.execute('INSERT INTO business_types(type_key,title,description) VALUES (?,?,?)',
                          (type_key, title, description))
    except sqlite3.IntegrityError as exc:
        raise ValueError('중복된 사업 유형 키입니다.') from exc
    type_id = int(row.lastrowid)
    _event(con, 'type_added', {'key': type_key, 'title': title}, type_id=type_id)
    return type_id


def types(con: sqlite3.Connection, include_disabled: bool = True) -> list[dict]:
    if type(include_disabled) is not bool:
        raise ValueError('조회 옵션이 유효하지 않습니다.')
    con.row_factory = sqlite3.Row
    query = 'SELECT id,type_key,title,description,built_in,enabled FROM business_types'
    if not include_disabled:
        query += ' WHERE enabled=1'
    return [dict(r) for r in con.execute(query + ' ORDER BY id')]


def disable_type(con: sqlite3.Connection, type_id: int) -> None:
    _id(type_id, '유형')
    row = con.execute('SELECT enabled FROM business_types WHERE id=?', (type_id,)).fetchone()
    if not row or not row[0]:
        raise ValueError('이미 비활성 또는 없는 유형입니다.')
    # Historical businesses remain intact; no new business can use this type.
    con.execute('UPDATE business_types SET enabled=0 WHERE id=?', (type_id,))
    _event(con, 'type_disabled', {'type_id': type_id}, type_id=type_id)


def _employee(con: sqlite3.Connection, employee_id: int | None) -> None:
    if employee_id is None:
        return
    _id(employee_id, '직원')
    if con.execute('SELECT 1 FROM ai_employee_profiles WHERE id=?', (employee_id,)).fetchone() is None:
        raise ValueError('등록되지 않은 AI 직원입니다.')


def add_business(con: sqlite3.Connection, type_id: int, name: str, goal: str,
                 budget_krw: int = 0, owner_employee_id: int | None = None) -> int:
    _id(type_id, '사업 유형')
    name = _label(name, '사업명', 120)
    goal = _label(goal, '사업 목표', 500)
    if type(budget_krw) is not int or not 0 <= budget_krw <= 1_000_000_000_000:
        raise ValueError('계획 예산은 0~1조 원 정수여야 합니다.')
    _employee(con, owner_employee_id)
    row = con.execute('SELECT enabled FROM business_types WHERE id=?', (type_id,)).fetchone()
    if not row or not row[0]:
        raise ValueError('사용 가능한 사업 유형이 아닙니다.')
    cur = con.execute('''INSERT INTO managed_businesses(type_id,name,goal,budget_krw,owner_employee_id)
                         VALUES (?,?,?,?,?)''', (type_id, name, goal, budget_krw, owner_employee_id))
    business_id = int(cur.lastrowid)
    _event(con, 'business_added', {'type_id': type_id, 'name': name, 'goal': goal,
                                   'budget_krw': budget_krw, 'owner_employee_id': owner_employee_id},
           business_id=business_id)
    if owner_employee_id is not None:
        con.execute('INSERT INTO business_participants(business_id,employee_id) VALUES (?,?)',
                    (business_id, owner_employee_id))
        _event(con, 'participant_added', {'employee_id': owner_employee_id}, business_id=business_id)
    return business_id


def businesses(con: sqlite3.Connection, limit: int = 200) -> list[dict]:
    if type(limit) is not int or not 1 <= limit <= 500:
        raise ValueError('조회 제한이 유효하지 않습니다.')
    con.row_factory = sqlite3.Row
    return [dict(row) for row in con.execute('''SELECT b.id,b.type_id,t.type_key,t.title AS type_title,
         b.name,b.goal,b.budget_krw,b.owner_employee_id,b.state,b.created_at,b.updated_at,
         (SELECT count(*) FROM business_participants p WHERE p.business_id=b.id) AS participant_count
         FROM managed_businesses b JOIN business_types t ON t.id=b.type_id
         ORDER BY b.id DESC LIMIT ?''', (limit,))]


def change_state(con: sqlite3.Connection, business_id: int, new_state: str) -> dict:
    _id(business_id, '사업')
    if not isinstance(new_state, str) or new_state not in _STATES:
        raise ValueError('사업 상태가 유효하지 않습니다.')
    row = con.execute('SELECT state FROM managed_businesses WHERE id=?', (business_id,)).fetchone()
    if not row or new_state not in _TRANSITIONS[row[0]]:
        raise ValueError('허용되지 않는 사업 상태 전환입니다.')
    previous = row[0]
    con.execute('UPDATE managed_businesses SET state=?,updated_at=CURRENT_TIMESTAMP WHERE id=?',
                (new_state, business_id))
    _event(con, 'state_changed', {'from': previous, 'to': new_state}, business_id=business_id)
    return {'id': business_id, 'state': new_state, 'external_actions_executed': False}


def participant(con: sqlite3.Connection, business_id: int, employee_id: int, add: bool) -> None:
    _id(business_id, '사업')
    _id(employee_id, '직원')
    _employee(con, employee_id)
    if type(add) is not bool:
        raise ValueError('참여 여부가 유효하지 않습니다.')
    row = con.execute('SELECT state,owner_employee_id FROM managed_businesses WHERE id=?',
                      (business_id,)).fetchone()
    if not row or row[0] == 'closed':
        raise ValueError('없는 사업 또는 종료된 사업입니다.')
    if not add and row[1] == employee_id:
        raise ValueError('책임 직원은 참여 해제할 수 없습니다.')
    if add:
        cur = con.execute('INSERT OR IGNORE INTO business_participants(business_id,employee_id) VALUES (?,?)',
                          (business_id, employee_id))
        action = 'participant_added'
    else:
        cur = con.execute('DELETE FROM business_participants WHERE business_id=? AND employee_id=?',
                          (business_id, employee_id))
        action = 'participant_removed'
    if cur.rowcount == 0:
        raise ValueError('이미 적용된 참여 상태입니다.')
    _event(con, action, {'employee_id': employee_id}, business_id=business_id)


def participants(con: sqlite3.Connection, business_id: int) -> list[dict]:
    _id(business_id, '사업')
    if not con.execute('SELECT 1 FROM managed_businesses WHERE id=?', (business_id,)).fetchone():
        raise ValueError('사업이 없습니다.')
    con.row_factory = sqlite3.Row
    return [dict(r) for r in con.execute('''SELECT p.employee_id,e.employee_key,e.display_name,p.assigned_at
       FROM business_participants p JOIN ai_employee_profiles e ON e.id=p.employee_id
       WHERE p.business_id=? ORDER BY p.employee_id''', (business_id,))]


def events(con: sqlite3.Connection, business_id: int | None = None, limit: int = 100) -> list[dict]:
    if business_id is not None:
        _id(business_id, '사업')
    if type(limit) is not int or not 1 <= limit <= 500:
        raise ValueError('조회 제한이 유효하지 않습니다.')
    con.row_factory = sqlite3.Row
    if business_id is None:
        rows = con.execute('SELECT * FROM business_events ORDER BY id DESC LIMIT ?', (limit,))
    else:
        rows = con.execute('SELECT * FROM business_events WHERE business_id=? ORDER BY id DESC LIMIT ?',
                           (business_id, limit))
    output = []
    for row in rows:
        data = dict(row)
        try:
            payload = json.loads(data['detail'])
        except (TypeError, ValueError) as exc:
            raise ValueError('사업 감사 기록 JSON 손상') from exc
        if not isinstance(payload, dict) or _hash(payload) != data['digest']:
            raise ValueError('사업 감사 기록 무결성 오류')
        output.append(data)
    return output
