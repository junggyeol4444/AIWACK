"""Stage51: owner-maintained local tool *catalog*, not a tool executor.

Entries describe possible future adapters. Neither registering nor retiring an
entry changes employee grants, loads code, opens URLs, or executes commands.
"""
from __future__ import annotations

import re
import sqlite3

from desktop.access_policy import CAPABILITIES

CATEGORIES = (
    'web', 'browser', 'file', 'development', 'image', 'video', 'data',
    'communication', 'publishing', 'commerce', 'operations', 'management',
)


def initialize(con: sqlite3.Connection) -> None:
    con.execute('''CREATE TABLE IF NOT EXISTS tool_registry (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        tool_key TEXT NOT NULL UNIQUE CHECK(length(tool_key) BETWEEN 3 AND 64),
        name TEXT NOT NULL CHECK(length(trim(name)) BETWEEN 1 AND 120),
        category TEXT NOT NULL CHECK(category IN (
           'web','browser','file','development','image','video','data',
           'communication','publishing','commerce','operations','management')),
        description TEXT NOT NULL CHECK(length(trim(description)) BETWEEN 1 AND 1000),
        required_capability TEXT NOT NULL DEFAULT '',
        state TEXT NOT NULL DEFAULT 'registered' CHECK(state IN ('registered','retired')),
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        retired_at TEXT
    )''')
    con.execute('''CREATE TABLE IF NOT EXISTS tool_registry_audit (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        tool_id INTEGER NOT NULL REFERENCES tool_registry(id) ON DELETE RESTRICT,
        event TEXT NOT NULL CHECK(event IN ('registered','retired')),
        reason TEXT NOT NULL CHECK(length(trim(reason)) BETWEEN 1 AND 500),
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    )''')
    con.execute('''CREATE TRIGGER IF NOT EXISTS tool_registry_audit_no_update
        BEFORE UPDATE ON tool_registry_audit BEGIN
        SELECT RAISE(ABORT,'tool registration audit is immutable'); END''')
    con.execute('''CREATE TRIGGER IF NOT EXISTS tool_registry_audit_no_delete
        BEFORE DELETE ON tool_registry_audit BEGIN
        SELECT RAISE(ABORT,'tool registration audit is immutable'); END''')
    con.execute('''CREATE TRIGGER IF NOT EXISTS tool_registry_guard_update
        BEFORE UPDATE ON tool_registry BEGIN
        SELECT RAISE(ABORT,'tool catalog is append-only except retirement')
        WHERE OLD.tool_key IS NOT NEW.tool_key OR OLD.name IS NOT NEW.name
        OR OLD.category IS NOT NEW.category
        OR OLD.description IS NOT NEW.description
        OR OLD.required_capability IS NOT NEW.required_capability
        OR OLD.created_at IS NOT NEW.created_at OR OLD.state != 'registered'
        OR NEW.state != 'retired' OR NEW.retired_at IS NULL;
        END''')
    con.execute('''CREATE TRIGGER IF NOT EXISTS tool_registry_no_delete
        BEFORE DELETE ON tool_registry BEGIN
        SELECT RAISE(ABORT,'tool registrations cannot be deleted'); END''')


def _text(value, label: str, maximum: int) -> str:
    if not isinstance(value, str) or not 1 <= len(value.strip()) <= maximum:
        raise ValueError(f'{label}: 1~{maximum}자 문자열이 필요합니다.')
    return value.strip()


def _id(value) -> int:
    if type(value) is not int or value < 1:
        raise ValueError('도구 ID는 양의 정수여야 합니다.')
    return value


def register(con: sqlite3.Connection, tool_key: str, name: str, category: str,
             description: str, required_capability: str = '') -> int:
    key = _text(tool_key, '도구 식별자', 64)
    if not re.fullmatch(r'[a-z][a-z0-9_]{2,63}', key, flags=re.ASCII):
        raise ValueError('도구 식별자는 영어 소문자로 시작하고 영문 소문자·숫자·밑줄만 허용합니다.')
    name = _text(name, '이름', 120)
    if not isinstance(category, str) or category not in CATEGORIES:
        raise ValueError('등록된 도구 분류를 선택해야 합니다.')
    description = _text(description, '설명', 1000)
    if not isinstance(required_capability, str) or (required_capability and required_capability not in CAPABILITIES):
        raise ValueError('알 수 없는 직원 권한입니다.')
    try:
        cursor = con.execute('''INSERT INTO tool_registry(tool_key,name,category,description,required_capability)
            VALUES(?,?,?,?,?)''', (key,name,category,description,required_capability))
    except sqlite3.IntegrityError as exc:
        raise ValueError('도구 식별자가 이미 등록되었거나 유효하지 않습니다.') from exc
    tool_id = int(cursor.lastrowid)
    con.execute('INSERT INTO tool_registry_audit(tool_id,event,reason) VALUES(?,?,?)',
                (tool_id,'registered','관리자 수동 등록; 실행 기능 없음'))
    return tool_id


def list_tools(con: sqlite3.Connection, *, include_retired: bool = False, limit: int = 200) -> list[dict]:
    if type(limit) is not int or not 1 <= limit <= 1000:
        raise ValueError('조회 제한은 1~1000 사이 정수여야 합니다.')
    con.row_factory = sqlite3.Row
    rows = con.execute('''SELECT * FROM tool_registry WHERE (? = 1 OR state='registered')
                          ORDER BY id DESC LIMIT ?''', (int(include_retired), limit)).fetchall()
    return [dict(row) for row in rows]


def read(con: sqlite3.Connection, tool_id: int) -> dict:
    con.row_factory = sqlite3.Row
    row = con.execute('SELECT * FROM tool_registry WHERE id=?', (_id(tool_id),)).fetchone()
    if row is None:
        raise ValueError('등록된 도구가 없습니다.')
    return dict(row)


def retire(con: sqlite3.Connection, tool_id: int, reason: str) -> bool:
    tool_id = _id(tool_id)
    reason = _text(reason, '보관 사유', 500)
    row = read(con, tool_id)
    if row['state'] != 'registered':
        raise ValueError('이미 보관된 도구입니다.')
    con.execute("UPDATE tool_registry SET state='retired',retired_at=CURRENT_TIMESTAMP WHERE id=? AND state='registered'", (tool_id,))
    con.execute('INSERT INTO tool_registry_audit(tool_id,event,reason) VALUES(?,?,?)',
                (tool_id,'retired',reason))
    return True


def audit(con: sqlite3.Connection, tool_id: int) -> list[dict]:
    read(con, tool_id)
    con.row_factory = sqlite3.Row
    return [dict(row) for row in con.execute('''SELECT * FROM tool_registry_audit
        WHERE tool_id=? ORDER BY id''', (tool_id,))]
