"""Stage37 local event inbox: explicit allowlisted events become reviewable todo tasks.

No external listeners, AI calls, payments, or tool execution.
"""
EVENT_TYPES = {'manual_alert', 'local_failure', 'review_requested'}


def initialize(con):
    con.execute('''CREATE TABLE IF NOT EXISTS local_task_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        event_key TEXT NOT NULL UNIQUE,
        event_type TEXT NOT NULL CHECK(event_type IN ('manual_alert','local_failure','review_requested')),
        summary TEXT NOT NULL, details TEXT NOT NULL DEFAULT '',
        status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','dispatched')),
        task_id INTEGER UNIQUE REFERENCES company_tasks(id) ON DELETE RESTRICT,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        dispatched_at TEXT)''')


def dispatch(con, limit=20):
    from desktop.stage87_90_management import stopped
    if stopped(con):return []
    if type(limit) is not int or not 1 <= limit <= 100:
        raise ValueError('invalid event batch limit')
    rows = con.execute('''SELECT id,event_type,summary,details FROM local_task_events
                          WHERE status='pending' ORDER BY id LIMIT ?''', (limit,)).fetchall()
    ids = []
    for event_id, kind, summary, details in rows:
        title = f'[{kind}] {summary}'
        task_id = con.execute('INSERT INTO company_tasks(title,description) VALUES(?,?)',
                              (title, details)).lastrowid
        con.execute("INSERT INTO company_task_status_events(task_id,old_status,new_status) VALUES(?,NULL,'todo')", (task_id,))
        con.execute('''UPDATE local_task_events SET status='dispatched',task_id=?,dispatched_at=CURRENT_TIMESTAMP
                       WHERE id=? AND status='pending' ''', (task_id,event_id))
        ids.append(int(task_id))
    return ids
