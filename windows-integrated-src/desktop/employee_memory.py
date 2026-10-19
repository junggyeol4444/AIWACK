"""Stage47: explicit owner-managed, durable and employee-scoped offline memories.

This does not automatically inject memories into an AI model or let agents read
another employee's records. The local database is not encrypted at rest.
"""
from __future__ import annotations

from datetime import date
import re
import sqlite3

KINDS = frozenset(('fact', 'lesson', 'procedure', 'decision'))
COLS = ('id', 'employee_id', 'kind', 'title', 'content', 'source', 'confidence',
        'expires_on', 'created_at', 'archived_at')


def initialize(con: sqlite3.Connection) -> None:
    con.execute("""CREATE TABLE IF NOT EXISTS employee_long_term_memories (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      employee_id INTEGER NOT NULL REFERENCES ai_employee_profiles(id) ON DELETE RESTRICT,
      kind TEXT NOT NULL CHECK(kind IN ('fact','lesson','procedure','decision')),
      title TEXT NOT NULL CHECK(length(trim(title)) BETWEEN 1 AND 120),
      content TEXT NOT NULL CHECK(length(trim(content)) BETWEEN 1 AND 4000),
      source TEXT NOT NULL CHECK(length(trim(source)) BETWEEN 1 AND 500),
      confidence INTEGER NOT NULL CHECK(confidence BETWEEN 0 AND 100),
      expires_on TEXT CHECK(expires_on IS NULL OR
        (length(expires_on)=10 AND expires_on GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]')),
      created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
      archived_at TEXT
    )""")
    con.execute('CREATE INDEX IF NOT EXISTS idx_memory_employee ON employee_long_term_memories(employee_id, id DESC)')
    con.execute("""CREATE TRIGGER IF NOT EXISTS employee_memory_immutable
      BEFORE UPDATE ON employee_long_term_memories BEGIN
      SELECT RAISE(ABORT,'memory contents are immutable; archive instead')
        WHERE OLD.employee_id IS NOT NEW.employee_id
           OR OLD.kind IS NOT NEW.kind OR OLD.title IS NOT NEW.title
           OR OLD.content IS NOT NEW.content OR OLD.source IS NOT NEW.source
           OR OLD.confidence IS NOT NEW.confidence OR OLD.expires_on IS NOT NEW.expires_on
           OR OLD.created_at IS NOT NEW.created_at
           OR OLD.archived_at IS NOT NULL OR NEW.archived_at IS NULL;
    END""")
    con.execute("""CREATE TRIGGER IF NOT EXISTS employee_memory_no_delete
      BEFORE DELETE ON employee_long_term_memories BEGIN
        SELECT RAISE(ABORT,'memory records cannot be deleted');
    END""")


def employee_id(value):
    if type(value) is not int or value < 1:
        raise ValueError('올바른 직원 ID가 필요합니다.')
    return value


def required(value, label, max_length):
    if not isinstance(value, str) or not 1 <= len(value.strip()) <= max_length:
        raise ValueError(f'{label}은 1~{max_length}자여야 합니다.')
    return value.strip()


def save(con, employee, kind, title, content, source, confidence=70, expires_on=None):
    employee_id(employee)
    if type(kind) is not str or kind not in KINDS:
        raise ValueError('지원하지 않는 기억 분류입니다.')
    title=required(title,'제목',120)
    content=required(content,'본문',4000)
    source=required(source,'출처',500)
    if type(confidence) is not int or not 0 <= confidence <= 100:
        raise ValueError('신뢰도는 0~100 사이 정수여야 합니다.')
    if expires_on is not None:
        if type(expires_on) is not str or not re.fullmatch(r'\d{4}-\d{2}-\d{2}',expires_on):
            raise ValueError('유효기간은 YYYY-MM-DD 형식이어야 합니다.')
        try:
            date.fromisoformat(expires_on)
        except ValueError as exc:
            raise ValueError('존재하지 않는 날짜입니다.') from exc
    active=con.execute('SELECT lifecycle FROM ai_employee_profiles WHERE id=?',(employee,)).fetchone()
    if active is None or active[0]!='draft':
        raise ValueError('등록된 활성 직원에게만 새 기억을 저장할 수 있습니다.')
    return con.execute("""INSERT INTO employee_long_term_memories
        (employee_id,kind,title,content,source,confidence,expires_on)
        VALUES(?,?,?,?,?,?,?)""",
        (employee,kind,title,content,source,confidence,expires_on)).lastrowid


def read(con, employee, memory_id):
    employee_id(employee)
    if type(memory_id) is not int or memory_id < 1:
        raise ValueError('올바른 기억 ID가 필요합니다.')
    con.row_factory=sqlite3.Row
    row=con.execute('SELECT * FROM employee_long_term_memories WHERE id=? AND employee_id=?',
                    (memory_id,employee)).fetchone()
    if row is None:
        raise ValueError('직원의 기억 기록을 찾을 수 없습니다.')
    return dict(row)


def list_memories(con, employee, *, query='', include_archived=False, include_expired=False, limit=200):
    employee_id(employee)
    if not isinstance(query,str) or len(query)>120:
        raise ValueError('검색어는 120자 이하여야 합니다.')
    if type(include_archived) is not bool or type(include_expired) is not bool:
        raise ValueError('조회 옵션이 올바르지 않습니다.')
    if type(limit) is not int or not 1<=limit<=500:
        raise ValueError('조회 건수는 1~500 사이여야 합니다.')
    sql='SELECT * FROM employee_long_term_memories WHERE employee_id=?'
    args=[employee]
    if not include_archived:sql+=' AND archived_at IS NULL'
    if not include_expired:sql+=" AND (expires_on IS NULL OR expires_on >= date('now'))"
    if query.strip():
        # instr() is a literal substring match (no LIKE wildcard surprise).
        sql+=' AND (instr(title,?)>0 OR instr(content,?)>0 OR instr(source,?)>0)'
        args.extend([query.strip()]*3)
    con.row_factory=sqlite3.Row
    return [dict(row) for row in con.execute(sql+' ORDER BY id DESC LIMIT ?',(*args,limit))]


def archive(con, employee, memory_id):
    employee_id(employee)
    if type(memory_id) is not int or memory_id<1:
        raise ValueError('올바른 기억 ID가 필요합니다.')
    # Guard by both IDs so one employee's memory cannot be archived as another's.
    cursor=con.execute("""UPDATE employee_long_term_memories SET archived_at=CURRENT_TIMESTAMP
        WHERE id=? AND employee_id=? AND archived_at IS NULL""",(memory_id,employee))
    if cursor.rowcount!=1:
        raise ValueError('기억이 없거나 이미 보관 처리되었습니다.')
    return True
