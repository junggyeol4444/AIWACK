"""Stage42: offline owner-recorded department conversations.

A department is the room; no remote transport, live worker, or autonomous
message author is implied. Membership is checked when the message is posted.
Historical messages remain tied to their original department after transfers.
"""
from __future__ import annotations

import sqlite3


def initialize(con: sqlite3.Connection) -> None:
    con.execute("""CREATE TABLE IF NOT EXISTS department_chat_messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        department_id INTEGER NOT NULL REFERENCES company_departments(id) ON DELETE RESTRICT,
        sender_id INTEGER NOT NULL REFERENCES ai_employee_profiles(id) ON DELETE RESTRICT,
        body TEXT NOT NULL CHECK(length(trim(body)) BETWEEN 1 AND 4000),
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    )""")
    con.execute("CREATE INDEX IF NOT EXISTS idx_department_chat_room ON department_chat_messages(department_id,id DESC)")
    # Prevent writes that bypass LocalStore from forging membership; old history
    # stays intact if an employee subsequently changes department/lifecycle.
    con.execute("""CREATE TRIGGER IF NOT EXISTS department_chat_sender_guard
        BEFORE INSERT ON department_chat_messages
        WHEN NOT EXISTS (
            SELECT 1 FROM ai_employee_profiles
            WHERE id=NEW.sender_id AND department_id=NEW.department_id AND lifecycle='draft'
        )
        BEGIN SELECT RAISE(ABORT, 'sender not active member of department'); END
    """)
    con.execute("""CREATE TRIGGER IF NOT EXISTS department_chat_immutable
        BEFORE UPDATE OF department_id,sender_id,body ON department_chat_messages
        BEGIN SELECT RAISE(ABORT, 'department message is immutable'); END
    """)


def _positive_id(value: int, name: str) -> int:
    if type(value) is not int or value < 1:
        raise ValueError(f"올바른 {name} ID가 필요합니다.")
    return value


def send(con: sqlite3.Connection, department_id: int, sender_id: int, body: str) -> int:
    _positive_id(department_id, "부서")
    _positive_id(sender_id, "발신 직원")
    if not isinstance(body, str) or not 1 <= len(body.strip()) <= 4000:
        raise ValueError("메시지 본문은 1~4000자여야 합니다.")
    if con.execute("SELECT 1 FROM company_departments WHERE id=?", (department_id,)).fetchone() is None:
        raise ValueError("존재하지 않는 부서입니다.")
    row = con.execute(
        "SELECT department_id,lifecycle FROM ai_employee_profiles WHERE id=?", (sender_id,)
    ).fetchone()
    if row is None or row[0] != department_id or row[1] != 'draft':
        raise ValueError("발신 직원이 해당 부서의 활성 구성원이 아닙니다.")
    return int(con.execute(
        "INSERT INTO department_chat_messages(department_id,sender_id,body) VALUES(?,?,?)",
        (department_id, sender_id, body.strip()),
    ).lastrowid)


def list_messages(con: sqlite3.Connection, department_id: int, limit: int = 200) -> list[dict]:
    _positive_id(department_id, "부서")
    if type(limit) is not int or not 1 <= limit <= 500:
        raise ValueError("조회 건수는 1~500이어야 합니다.")
    if con.execute("SELECT 1 FROM company_departments WHERE id=?", (department_id,)).fetchone() is None:
        raise ValueError("존재하지 않는 부서입니다.")
    con.row_factory = sqlite3.Row
    # Only the requested department's history is returned; the latest messages
    # appear last in chat order for easier reading, with bounded queries.
    rows = con.execute("""SELECT m.id,m.department_id,m.sender_id,
                e.display_name AS sender_name,m.body,m.created_at
        FROM department_chat_messages m
        JOIN ai_employee_profiles e ON e.id=m.sender_id
        WHERE m.department_id=? ORDER BY m.id DESC LIMIT ?""", (department_id, limit)).fetchall()
    return [dict(row) for row in reversed(rows)]
