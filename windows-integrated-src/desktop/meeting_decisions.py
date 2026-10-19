"""Stage46 owner-authorized offline meeting decisions and one linked follow-up todo.

This records the OWNER'S decision, not an AI vote, legal/financial approval or
permission to run tools. Changes are atomic and visible after restarting SQLite.
"""
from __future__ import annotations

import sqlite3

from desktop.meetings import _id, _meeting, _text

DECISIONS = ('approved', 'deferred', 'rejected')


def initialize(con: sqlite3.Connection) -> None:
    con.execute('''CREATE TABLE IF NOT EXISTS local_meeting_decisions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        meeting_id INTEGER NOT NULL REFERENCES local_ai_meetings(id) ON DELETE RESTRICT,
        agenda_id INTEGER NOT NULL UNIQUE REFERENCES local_meeting_agenda(id) ON DELETE RESTRICT,
        outcome TEXT NOT NULL CHECK(outcome IN ('approved','deferred','rejected')),
        rationale TEXT NOT NULL CHECK(length(trim(rationale)) BETWEEN 1 AND 2000),
        opinions_count INTEGER NOT NULL CHECK(opinions_count >= 1),
        missing_count INTEGER NOT NULL CHECK(missing_count >= 0),
        dissent_acknowledged INTEGER NOT NULL CHECK(dissent_acknowledged = 1),
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    )''')
    con.execute('''CREATE TRIGGER IF NOT EXISTS meeting_decision_insert_guard
        BEFORE INSERT ON local_meeting_decisions
        WHEN NOT EXISTS(SELECT 1 FROM local_ai_meetings m WHERE m.id=NEW.meeting_id AND m.status='scheduled')
          OR NOT EXISTS(SELECT 1 FROM local_meeting_agenda a WHERE a.id=NEW.agenda_id AND a.meeting_id=NEW.meeting_id)
          OR (SELECT COUNT(*) FROM local_meeting_opinions o WHERE o.agenda_id=NEW.agenda_id
                  AND o.meeting_id=NEW.meeting_id)!=NEW.opinions_count
          OR (SELECT COUNT(*) FROM local_meeting_attendees WHERE meeting_id=NEW.meeting_id)
             - NEW.opinions_count!=NEW.missing_count
        BEGIN SELECT RAISE(ABORT,'meeting decision requires scheduled meeting, matching agenda and correct opinion counts'); END''')
    con.execute('''CREATE TRIGGER IF NOT EXISTS meeting_decision_update_guard
        BEFORE UPDATE ON local_meeting_decisions
        BEGIN SELECT RAISE(ABORT,'meeting decisions are immutable'); END''')
    con.execute('''CREATE TRIGGER IF NOT EXISTS meeting_decision_delete_guard
        BEFORE DELETE ON local_meeting_decisions
        BEGIN SELECT RAISE(ABORT,'meeting decisions are immutable'); END''')
    con.execute('''CREATE TRIGGER IF NOT EXISTS meeting_decided_agenda_opinion_guard
        BEFORE INSERT ON local_meeting_opinions
        WHEN EXISTS(SELECT 1 FROM local_meeting_decisions WHERE agenda_id=NEW.agenda_id)
        BEGIN SELECT RAISE(ABORT,'decided agenda cannot accept new opinions'); END''')
    con.execute('''CREATE TABLE IF NOT EXISTS local_meeting_followups (
        decision_id INTEGER PRIMARY KEY REFERENCES local_meeting_decisions(id) ON DELETE RESTRICT,
        task_id INTEGER NOT NULL UNIQUE REFERENCES company_tasks(id) ON DELETE RESTRICT,
        assignee_id INTEGER NOT NULL REFERENCES ai_employee_profiles(id) ON DELETE RESTRICT,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    )''')
    con.execute('''CREATE TRIGGER IF NOT EXISTS meeting_followup_insert_guard
        BEFORE INSERT ON local_meeting_followups
        WHEN NOT EXISTS (SELECT 1 FROM local_meeting_decisions d
              JOIN local_ai_meetings m ON m.id=d.meeting_id
              JOIN local_meeting_attendees a ON a.meeting_id=d.meeting_id AND a.employee_id=NEW.assignee_id
              JOIN ai_employee_profiles e ON e.id=a.employee_id
              LEFT JOIN ai_reporting_lines r ON r.employee_id=e.id
              WHERE d.id=NEW.decision_id AND d.outcome='approved' AND m.status='scheduled'
                AND e.lifecycle='draft' AND (r.tier IS NULL OR r.tier='staff'))
          OR NOT EXISTS(SELECT 1 FROM company_task_assignments a
              WHERE a.task_id=NEW.task_id AND a.employee_id=NEW.assignee_id)
        BEGIN SELECT RAISE(ABORT,'follow-up requires owner-approved decision and valid task assignee'); END''')
    for action in ('UPDATE', 'DELETE'):
        con.execute(f'''CREATE TRIGGER IF NOT EXISTS meeting_followup_{action.lower()}_guard
            BEFORE {action} ON local_meeting_followups
            BEGIN SELECT RAISE(ABORT,'meeting follow-up linkage is immutable'); END''')


def decide(con: sqlite3.Connection, meeting_id: int, agenda_id: int,
           outcome: str, rationale: str, acknowledge: bool) -> int:
    """Always called inside an authenticated owner transaction (BEGIN IMMEDIATE)."""
    if _meeting(con, meeting_id) != 'scheduled':
        raise ValueError('예정 상태 회의에서만 결정할 수 있습니다.')
    _id(agenda_id, '안건')
    if type(outcome) is not str or outcome not in DECISIONS:
        raise ValueError('결정은 채택·보류·반려 중 하나여야 합니다.')
    reason = _text(rationale, '결정 근거', 2000)
    if acknowledge is not True:
        raise ValueError('반대·보류 의견과 미제출 참석자 확인이 필요합니다.')
    if not con.execute('SELECT 1 FROM local_meeting_agenda WHERE id=? AND meeting_id=?',
                       (agenda_id, meeting_id)).fetchone():
        raise ValueError('해당 회의의 안건이 아닙니다.')
    if con.execute('SELECT 1 FROM local_meeting_decisions WHERE agenda_id=?', (agenda_id,)).fetchone():
        raise ValueError('이미 결정한 안건입니다. 변경할 수 없습니다.')
    submitted = con.execute('SELECT COUNT(*) FROM local_meeting_opinions WHERE meeting_id=? AND agenda_id=?',
                            (meeting_id, agenda_id)).fetchone()[0]
    if submitted < 1:
        raise ValueError('결정 전 최소 1개의 직원 의견이 필요합니다.')
    total = con.execute('SELECT COUNT(*) FROM local_meeting_attendees WHERE meeting_id=?', (meeting_id,)).fetchone()[0]
    return int(con.execute('''INSERT INTO local_meeting_decisions
        (meeting_id,agenda_id,outcome,rationale,opinions_count,missing_count,dissent_acknowledged)
        VALUES(?,?,?,?,?,?,1)''', (meeting_id, agenda_id, outcome, reason, submitted, total-submitted)).lastrowid)


def create_followup(con: sqlite3.Connection, decision_id: int, employee_id: int,
                    title: str, description: str = '') -> int:
    """One TODO per approved decision. No model, payment, queue or external execution."""
    _id(decision_id, '결정')
    _id(employee_id, '담당 직원')
    name = _text(title, '후속 업무 제목', 120)
    detail = _text(description, '후속 업무 설명', 1000, required=False)
    decision = con.execute('''SELECT d.meeting_id,d.outcome,m.status
              FROM local_meeting_decisions d JOIN local_ai_meetings m ON m.id=d.meeting_id
              WHERE d.id=?''', (decision_id,)).fetchone()
    if decision is None:
        raise ValueError('존재하지 않는 결정입니다.')
    if decision[1] != 'approved' or decision[2] != 'scheduled':
        raise ValueError('취소되지 않은 회의의 채택 결정만 후속 업무를 만들 수 있습니다.')
    if con.execute('SELECT 1 FROM local_meeting_followups WHERE decision_id=?', (decision_id,)).fetchone():
        raise ValueError('이 결정의 후속 업무는 이미 등록되었습니다.')
    worker = con.execute('''SELECT e.lifecycle,r.tier FROM ai_employee_profiles e
        LEFT JOIN ai_reporting_lines r ON r.employee_id=e.id
        JOIN local_meeting_attendees a ON a.employee_id=e.id
        WHERE a.meeting_id=? AND e.id=?''', (decision[0],employee_id)).fetchone()
    if worker is None or worker[0] != 'draft' or worker[1] not in (None,'staff'):
        raise ValueError('회의 참석자인 활성 실무 직원만 후속 업무 담당자로 지정할 수 있습니다.')
    task_id = int(con.execute('INSERT INTO company_tasks(title,description) VALUES(?,?)', (name,detail)).lastrowid)
    con.execute("INSERT INTO company_task_status_events(task_id,old_status,new_status) VALUES(?,NULL,'todo')", (task_id,))
    con.execute('''INSERT INTO company_task_assignments(task_id,employee_id,reason)
        VALUES(?,?,?)''',(task_id,employee_id,f'관리자 승인 회의 결정 #{decision_id} 후속 업무'))
    con.execute('''INSERT INTO company_task_assignment_events(task_id,employee_id,action,detail)
        VALUES(?,?,'auto_assigned',?)''', (task_id,employee_id,f'관리자 명시적 회의 후속 업무 배정 (결정 #{decision_id}); AI 자동 배정 아님'))
    con.execute('INSERT INTO local_meeting_followups(decision_id,task_id,assignee_id) VALUES(?,?,?)',
                (decision_id,task_id,employee_id))
    return task_id


def list_decisions(con: sqlite3.Connection, meeting_id: int) -> list[dict]:
    _meeting(con, meeting_id)
    con.row_factory = sqlite3.Row
    return [dict(r) for r in con.execute('''SELECT d.*,a.position,a.topic,f.task_id,f.assignee_id,
                  e.display_name AS assignee_name
        FROM local_meeting_decisions d JOIN local_meeting_agenda a ON a.id=d.agenda_id
        LEFT JOIN local_meeting_followups f ON f.decision_id=d.id
        LEFT JOIN ai_employee_profiles e ON e.id=f.assignee_id
        WHERE d.meeting_id=? ORDER BY a.position''',(meeting_id,))]
