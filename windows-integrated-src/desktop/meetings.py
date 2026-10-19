"""Stage 44: owner-managed *local* meeting agendas and invited AI employee records.

This is not an AI discussion, autonomous meeting, decision, or calendar integration.
The SQLite restrictions also apply if callers bypass LocalStore.
"""
from __future__ import annotations

import sqlite3


STATUSES = ('draft', 'scheduled', 'cancelled')


def initialize(con: sqlite3.Connection) -> None:
    con.execute('''CREATE TABLE IF NOT EXISTS local_ai_meetings (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL CHECK(length(trim(title)) BETWEEN 1 AND 120),
        purpose TEXT NOT NULL DEFAULT '' CHECK(length(purpose) <= 1000),
        status TEXT NOT NULL DEFAULT 'draft' CHECK(status IN ('draft','scheduled','cancelled')),
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    )''')
    con.execute('''CREATE TABLE IF NOT EXISTS local_meeting_agenda (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        meeting_id INTEGER NOT NULL REFERENCES local_ai_meetings(id) ON DELETE RESTRICT,
        position INTEGER NOT NULL CHECK(position BETWEEN 1 AND 20),
        topic TEXT NOT NULL CHECK(length(trim(topic)) BETWEEN 1 AND 500),
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(meeting_id,position)
    )''')
    con.execute('''CREATE TABLE IF NOT EXISTS local_meeting_attendees (
        meeting_id INTEGER NOT NULL REFERENCES local_ai_meetings(id) ON DELETE RESTRICT,
        employee_id INTEGER NOT NULL REFERENCES ai_employee_profiles(id) ON DELETE RESTRICT,
        invited_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY(meeting_id,employee_id)
    )''')
    con.execute('CREATE INDEX IF NOT EXISTS idx_local_meeting_agenda ON local_meeting_agenda(meeting_id,position)')
    con.execute('''CREATE TRIGGER IF NOT EXISTS meeting_agenda_insert_guard
        BEFORE INSERT ON local_meeting_agenda
        WHEN NOT EXISTS (SELECT 1 FROM local_ai_meetings WHERE id=NEW.meeting_id AND status='draft')
        BEGIN SELECT RAISE(ABORT,'meeting agenda requires draft'); END''')
    con.execute('''CREATE TRIGGER IF NOT EXISTS meeting_agenda_delete_guard
        BEFORE DELETE ON local_meeting_agenda
        WHEN NOT EXISTS (SELECT 1 FROM local_ai_meetings WHERE id=OLD.meeting_id AND status='draft')
        BEGIN SELECT RAISE(ABORT,'meeting agenda is frozen'); END''')
    con.execute('''CREATE TRIGGER IF NOT EXISTS meeting_agenda_update_guard
        BEFORE UPDATE ON local_meeting_agenda
        BEGIN SELECT RAISE(ABORT,'meeting agenda items are immutable'); END''')
    con.execute('''CREATE TRIGGER IF NOT EXISTS meeting_attendee_insert_guard
        BEFORE INSERT ON local_meeting_attendees
        WHEN NOT EXISTS (SELECT 1 FROM local_ai_meetings WHERE id=NEW.meeting_id AND status='draft')
          OR NOT EXISTS (SELECT 1 FROM ai_employee_profiles WHERE id=NEW.employee_id AND lifecycle='draft')
          OR (SELECT COUNT(*) FROM local_meeting_attendees WHERE meeting_id=NEW.meeting_id)>=30
        BEGIN SELECT RAISE(ABORT,'meeting requires draft and active employee (max 30)'); END''')
    con.execute('''CREATE TRIGGER IF NOT EXISTS meeting_attendee_delete_guard
        BEFORE DELETE ON local_meeting_attendees
        WHEN NOT EXISTS (SELECT 1 FROM local_ai_meetings WHERE id=OLD.meeting_id AND status='draft')
        BEGIN SELECT RAISE(ABORT,'meeting attendees are frozen'); END''')
    con.execute('''CREATE TRIGGER IF NOT EXISTS meeting_attendee_update_guard
        BEFORE UPDATE ON local_meeting_attendees
        BEGIN SELECT RAISE(ABORT,'meeting attendee identity is immutable'); END''')
    con.execute('''CREATE TRIGGER IF NOT EXISTS meeting_ready_guard
        BEFORE UPDATE OF status ON local_ai_meetings
        WHEN NEW.status='scheduled' AND (OLD.status!='draft'
          OR NOT EXISTS (SELECT 1 FROM local_meeting_agenda WHERE meeting_id=OLD.id)
          OR (SELECT COUNT(*) FROM local_meeting_attendees WHERE meeting_id=OLD.id)<2
          OR EXISTS (SELECT 1 FROM local_meeting_attendees a
              JOIN ai_employee_profiles e ON e.id=a.employee_id
              WHERE a.meeting_id=OLD.id AND e.lifecycle!='draft'))
        BEGIN SELECT RAISE(ABORT,'meeting needs agenda and two active attendees'); END''')
    con.execute('''CREATE TRIGGER IF NOT EXISTS meeting_status_guard
        BEFORE UPDATE OF status ON local_ai_meetings
        WHEN OLD.status='cancelled' OR (OLD.status='scheduled' AND NEW.status!='cancelled')
        BEGIN SELECT RAISE(ABORT,'meeting status cannot return to draft'); END''')


def _id(value: int, name: str) -> int:
    if type(value) is not int or value < 1:
        raise ValueError(f'올바른 {name} ID가 필요합니다.')
    return value


def _text(value: str, name: str, length: int, *, required: bool = True) -> str:
    if not isinstance(value, str) or (required and not value.strip()) or len(value.strip()) > length:
        raise ValueError(f'{name}은 최대 {length}자 이내로 입력하세요.')
    return value.strip()


def _meeting(con: sqlite3.Connection, meeting_id: int, *, draft: bool = False) -> str:
    _id(meeting_id, '회의')
    row = con.execute('SELECT status FROM local_ai_meetings WHERE id=?',(meeting_id,)).fetchone()
    if row is None:
        raise ValueError('존재하지 않는 회의입니다.')
    if draft and row[0]!='draft':
        raise ValueError('초안 상태 회의에서만 변경할 수 있습니다.')
    return row[0]


def create(con: sqlite3.Connection, title: str, purpose: str = '') -> int:
    name = _text(title, '회의 제목', 120)
    info = _text(purpose, '회의 목적', 1000, required=False)
    return int(con.execute('INSERT INTO local_ai_meetings(title,purpose) VALUES(?,?)', (name,info)).lastrowid)


def list_meetings(con: sqlite3.Connection) -> list[dict]:
    con.row_factory = sqlite3.Row
    return [dict(r) for r in con.execute('''SELECT m.id,m.title,m.purpose,m.status,m.created_at,
        (SELECT COUNT(*) FROM local_meeting_attendees WHERE meeting_id=m.id) AS attendee_count,
        (SELECT COUNT(*) FROM local_meeting_agenda WHERE meeting_id=m.id) AS agenda_count
        FROM local_ai_meetings m ORDER BY m.id DESC LIMIT 500''')]


def read(con: sqlite3.Connection, meeting_id: int) -> dict:
    _meeting(con, meeting_id)
    con.row_factory = sqlite3.Row
    head = dict(con.execute('SELECT * FROM local_ai_meetings WHERE id=?',(meeting_id,)).fetchone())
    head['agenda'] = [dict(r) for r in con.execute('''SELECT id,position,topic,created_at FROM local_meeting_agenda
                                        WHERE meeting_id=? ORDER BY position''',(meeting_id,))]
    head['attendees'] = [dict(r) for r in con.execute('''SELECT a.employee_id,e.display_name,e.lifecycle,a.invited_at
          FROM local_meeting_attendees a JOIN ai_employee_profiles e ON e.id=a.employee_id
          WHERE a.meeting_id=? ORDER BY a.employee_id''',(meeting_id,))]
    return head


def add_agenda(con: sqlite3.Connection, meeting_id: int, topic: str) -> int:
    _meeting(con, meeting_id, draft=True)
    value = _text(topic, '안건', 500)
    position = con.execute('SELECT COALESCE(MAX(position),0)+1 FROM local_meeting_agenda WHERE meeting_id=?',(meeting_id,)).fetchone()[0]
    if position>20:
        raise ValueError('회의당 안건은 최대 20개입니다.')
    return int(con.execute('INSERT INTO local_meeting_agenda(meeting_id,position,topic) VALUES(?,?,?)',
                           (meeting_id,position,value)).lastrowid)


def add_attendee(con: sqlite3.Connection, meeting_id: int, employee_id: int) -> None:
    _meeting(con, meeting_id, draft=True)
    _id(employee_id, '직원')
    row = con.execute('SELECT lifecycle FROM ai_employee_profiles WHERE id=?',(employee_id,)).fetchone()
    if row is None or row[0]!='draft':
        raise ValueError('활성 직원만 회의 참석자로 지정할 수 있습니다.')
    if con.execute('SELECT 1 FROM local_meeting_attendees WHERE meeting_id=? AND employee_id=?',
                   (meeting_id,employee_id)).fetchone():
        raise ValueError('이미 지정된 참석자입니다.')
    if con.execute('SELECT COUNT(*) FROM local_meeting_attendees WHERE meeting_id=?',(meeting_id,)).fetchone()[0]>=30:
        raise ValueError('회의 참석자는 최대 30명입니다.')
    con.execute('INSERT INTO local_meeting_attendees(meeting_id,employee_id) VALUES(?,?)',(meeting_id,employee_id))


def remove_attendee(con: sqlite3.Connection, meeting_id: int, employee_id: int) -> None:
    _meeting(con, meeting_id, draft=True)
    _id(employee_id, '직원')
    if con.execute('DELETE FROM local_meeting_attendees WHERE meeting_id=? AND employee_id=?',
                   (meeting_id,employee_id)).rowcount!=1:
        raise ValueError('회의 참석자가 아닙니다.')


def set_status(con: sqlite3.Connection, meeting_id: int, status: str) -> None:
    current = _meeting(con, meeting_id)
    if status not in ('scheduled','cancelled') or current=='cancelled' or current=='scheduled' and status!='cancelled':
        raise ValueError('허용된 상태 전환이 아닙니다.')
    if status=='scheduled':
        record=read(con, meeting_id)
        if not record['agenda'] or len(record['attendees'])<2 or any(p['lifecycle']!='draft' for p in record['attendees']):
            raise ValueError('안건 1개 이상과 활성 참석자 2명 이상이 필요합니다.')
    con.execute('UPDATE local_ai_meetings SET status=?,updated_at=CURRENT_TIMESTAMP WHERE id=?', (status,meeting_id))
