"""Stage 43: offline, owner-mediated project collaboration rooms.

A room is a *local coordination record*, not an operating business/project or
an autonomous AI conversation. Historical posts survive participant removal.
"""
from __future__ import annotations

import sqlite3


def initialize(con: sqlite3.Connection) -> None:
    con.execute("""CREATE TABLE IF NOT EXISTS local_project_rooms (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL CHECK(length(trim(name)) BETWEEN 1 AND 120),
        description TEXT NOT NULL DEFAULT '' CHECK(length(description) <= 1000),
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    )""")
    con.execute("""CREATE TABLE IF NOT EXISTS local_project_participants (
        project_id INTEGER NOT NULL REFERENCES local_project_rooms(id) ON DELETE RESTRICT,
        employee_id INTEGER NOT NULL REFERENCES ai_employee_profiles(id) ON DELETE RESTRICT,
        joined_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY(project_id,employee_id)
    )""")
    con.execute("""CREATE TABLE IF NOT EXISTS local_project_messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        project_id INTEGER NOT NULL REFERENCES local_project_rooms(id) ON DELETE RESTRICT,
        sender_id INTEGER NOT NULL REFERENCES ai_employee_profiles(id) ON DELETE RESTRICT,
        body TEXT NOT NULL CHECK(length(trim(body)) BETWEEN 1 AND 4000),
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    )""")
    con.execute('CREATE INDEX IF NOT EXISTS idx_project_messages_room ON local_project_messages(project_id,id DESC)')
    con.execute("""CREATE TRIGGER IF NOT EXISTS project_member_insert_guard
        BEFORE INSERT ON local_project_participants
        WHEN NOT EXISTS (SELECT 1 FROM ai_employee_profiles
                         WHERE id=NEW.employee_id AND lifecycle='draft')
        BEGIN SELECT RAISE(ABORT,'project participant must be active'); END
    """)
    con.execute("""CREATE TRIGGER IF NOT EXISTS project_participant_immutable_update
        BEFORE UPDATE ON local_project_participants
        BEGIN SELECT RAISE(ABORT,'project participant identity is immutable'); END
    """)
    con.execute("""CREATE TRIGGER IF NOT EXISTS project_message_sender_guard
        BEFORE INSERT ON local_project_messages
        WHEN NOT EXISTS (SELECT 1 FROM local_project_participants p
                         JOIN ai_employee_profiles e ON e.id=p.employee_id
                         WHERE p.project_id=NEW.project_id AND p.employee_id=NEW.sender_id
                               AND e.lifecycle='draft')
        BEGIN SELECT RAISE(ABORT,'sender is not an active project participant'); END
    """)
    con.execute("""CREATE TRIGGER IF NOT EXISTS project_message_immutable_update
        BEFORE UPDATE ON local_project_messages
        BEGIN SELECT RAISE(ABORT,'project message is immutable'); END
    """)
    con.execute("""CREATE TRIGGER IF NOT EXISTS project_message_immutable_delete
        BEFORE DELETE ON local_project_messages
        BEGIN SELECT RAISE(ABORT,'project message is immutable'); END
    """)


def positive(value: int, label: str) -> int:
    if type(value) is not int or value < 1:
        raise ValueError(f'올바른 {label} ID가 필요합니다.')
    return value


def text_value(value: str, label: str, maximum: int, *, required: bool = True) -> str:
    if not isinstance(value, str) or len(value.strip()) > maximum or (required and not value.strip()):
        raise ValueError(f'{label}: {"1~" if required else "최대 "}{maximum}자 이내로 입력하세요.')
    return value.strip()


def require_project(con: sqlite3.Connection, project_id: int) -> None:
    positive(project_id, '프로젝트')
    if con.execute('SELECT 1 FROM local_project_rooms WHERE id=?', (project_id,)).fetchone() is None:
        raise ValueError('존재하지 않는 프로젝트 대화방입니다.')


def create_room(con: sqlite3.Connection, name: str, description: str = '') -> int:
    title = text_value(name, '프로젝트명', 120)
    info = text_value(description, '설명', 1000, required=False)
    return int(con.execute('INSERT INTO local_project_rooms(name,description) VALUES(?,?)', (title, info)).lastrowid)


def list_rooms(con: sqlite3.Connection) -> list[dict]:
    con.row_factory = sqlite3.Row
    return [dict(row) for row in con.execute('''SELECT r.id,r.name,r.description,r.created_at,
        (SELECT COUNT(*) FROM local_project_participants p WHERE p.project_id=r.id) AS participant_count,
        (SELECT COUNT(*) FROM local_project_messages m WHERE m.project_id=r.id) AS message_count
        FROM local_project_rooms r ORDER BY r.id DESC LIMIT 500''')]


def add_participant(con: sqlite3.Connection, project_id: int, employee_id: int) -> None:
    require_project(con, project_id)
    positive(employee_id, '직원')
    row = con.execute('SELECT lifecycle FROM ai_employee_profiles WHERE id=?', (employee_id,)).fetchone()
    if row is None or row[0] != 'draft':
        raise ValueError('활성 직원만 참여할 수 있습니다.')
    if con.execute('SELECT 1 FROM local_project_participants WHERE project_id=? AND employee_id=?',
                   (project_id, employee_id)).fetchone():
        raise ValueError('이미 참여 중인 직원입니다.')
    con.execute('INSERT INTO local_project_participants(project_id,employee_id) VALUES(?,?)',
                (project_id, employee_id))


def remove_participant(con: sqlite3.Connection, project_id: int, employee_id: int) -> None:
    require_project(con, project_id)
    positive(employee_id, '직원')
    result = con.execute('DELETE FROM local_project_participants WHERE project_id=? AND employee_id=?',
                         (project_id, employee_id))
    if result.rowcount != 1:
        raise ValueError('해당 프로젝트의 참여 직원이 아닙니다.')


def list_participants(con: sqlite3.Connection, project_id: int) -> list[dict]:
    require_project(con, project_id)
    con.row_factory = sqlite3.Row
    return [dict(row) for row in con.execute('''SELECT p.employee_id,e.display_name,e.lifecycle,p.joined_at
        FROM local_project_participants p JOIN ai_employee_profiles e ON e.id=p.employee_id
        WHERE p.project_id=? ORDER BY p.employee_id''', (project_id,))]


def send(con: sqlite3.Connection, project_id: int, sender_id: int, body: str) -> int:
    require_project(con, project_id)
    positive(sender_id, '발신 직원')
    content = text_value(body, '메시지', 4000)
    present = con.execute('''SELECT 1 FROM local_project_participants p
        JOIN ai_employee_profiles e ON e.id=p.employee_id
        WHERE p.project_id=? AND p.employee_id=? AND e.lifecycle='draft' ''',
        (project_id, sender_id)).fetchone()
    if not present:
        raise ValueError('발신 직원이 해당 프로젝트의 활성 참여자가 아닙니다.')
    return int(con.execute('INSERT INTO local_project_messages(project_id,sender_id,body) VALUES(?,?,?)',
                           (project_id, sender_id, content)).lastrowid)


def list_messages(con: sqlite3.Connection, project_id: int, limit: int = 200) -> list[dict]:
    require_project(con, project_id)
    if type(limit) is not int or not 1 <= limit <= 500:
        raise ValueError('조회 건수는 1~500이어야 합니다.')
    con.row_factory = sqlite3.Row
    rows = con.execute('''SELECT m.id,m.project_id,m.sender_id,e.display_name AS sender_name,
        m.body,m.created_at FROM local_project_messages m
        JOIN ai_employee_profiles e ON e.id=m.sender_id
        WHERE m.project_id=? ORDER BY m.id DESC LIMIT ?''', (project_id, limit)).fetchall()
    return [dict(row) for row in reversed(rows)]
