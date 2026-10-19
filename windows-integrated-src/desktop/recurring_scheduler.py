"""Stage36: bounded offline recurring task creation; never invokes an AI or tool."""
from __future__ import annotations

import time


def initialize(con):
    con.execute('''CREATE TABLE IF NOT EXISTS recurring_task_schedules (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL, description TEXT NOT NULL DEFAULT '',
        interval_minutes INTEGER NOT NULL CHECK(interval_minutes BETWEEN 5 AND 10080),
        next_due INTEGER NOT NULL, enabled INTEGER NOT NULL DEFAULT 0 CHECK(enabled IN (0,1)),
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)''')
    con.execute('''CREATE TABLE IF NOT EXISTS recurring_task_occurrences (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        schedule_id INTEGER NOT NULL REFERENCES recurring_task_schedules(id) ON DELETE RESTRICT,
        due_at INTEGER NOT NULL, task_id INTEGER NOT NULL UNIQUE REFERENCES company_tasks(id) ON DELETE RESTRICT,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(schedule_id,due_at))''')


def dispatch(con, now: int, limit: int = 20) -> list[int]:
    """One occurrence per enabled schedule per tick; skip missed slots, no backlog storm."""
    if not isinstance(now, int) or now < 0 or not 1 <= limit <= 100:
        raise ValueError('invalid scheduler arguments')
    from desktop.stage87_90_management import stopped
    if stopped(con):return []
    rows = con.execute('''SELECT id,title,description,interval_minutes,next_due
                          FROM recurring_task_schedules WHERE enabled=1 AND next_due<=?
                          ORDER BY next_due,id LIMIT ?''', (now, limit)).fetchall()
    created = []
    for schedule_id, title, description, minutes, due in rows:
        # Advance to the first future slot, including if the app was closed for days.
        interval = minutes * 60
        future = due + ((now - due) // interval + 1) * interval
        task_id = con.execute('INSERT INTO company_tasks(title,description) VALUES(?,?)',
                              (title, description)).lastrowid
        con.execute("INSERT INTO company_task_status_events(task_id,old_status,new_status) VALUES(?,NULL,'todo')", (task_id,))
        con.execute('INSERT INTO recurring_task_occurrences(schedule_id,due_at,task_id) VALUES(?,?,?)',
                    (schedule_id, due, task_id))
        con.execute('UPDATE recurring_task_schedules SET next_due=? WHERE id=? AND next_due=?',
                    (future, schedule_id, due))
        created.append(int(task_id))
    return created
