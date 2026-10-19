"""Stage38 durable local task queue. Explicit claims only; never launches a model."""
import time


def initialize(con):
    con.execute('''CREATE TABLE IF NOT EXISTS local_task_queue (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        task_id INTEGER NOT NULL UNIQUE REFERENCES company_tasks(id) ON DELETE RESTRICT,
        state TEXT NOT NULL DEFAULT 'pending' CHECK(state IN ('pending','claimed','done','failed','cancelled')),
        attempts INTEGER NOT NULL DEFAULT 0 CHECK(attempts>=0),
        max_attempts INTEGER NOT NULL DEFAULT 3 CHECK(max_attempts BETWEEN 1 AND 10),
        next_attempt_at INTEGER NOT NULL DEFAULT 0,
        last_error TEXT NOT NULL DEFAULT '',
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)''')
    con.execute('CREATE INDEX IF NOT EXISTS idx_local_task_queue_due ON local_task_queue(state,next_attempt_at,id)')
    con.execute('''CREATE TABLE IF NOT EXISTS local_task_queue_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        queue_id INTEGER NOT NULL REFERENCES local_task_queue(id) ON DELETE RESTRICT,
        action TEXT NOT NULL, detail TEXT NOT NULL DEFAULT '',
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)''')


def log(con, queue_id, action, detail=''):
    con.execute('INSERT INTO local_task_queue_events(queue_id,action,detail) VALUES(?,?,?)', (queue_id,action,detail))


def claim(con, now):
    from desktop.stage87_90_management import stopped
    if stopped(con):return None
    row = con.execute('''SELECT q.id,q.task_id FROM local_task_queue q JOIN company_tasks t ON t.id=q.task_id
        WHERE q.state='pending' AND q.next_attempt_at<=? AND t.status NOT IN ('done','cancelled','blocked')
        AND NOT EXISTS (SELECT 1 FROM company_task_dependencies d JOIN company_tasks p ON p.id=d.prerequisite_id
                        WHERE d.task_id=q.task_id AND p.status!='done')
        ORDER BY CASE COALESCE((SELECT priority FROM company_task_priorities WHERE task_id=q.task_id),'normal')
          WHEN 'urgent' THEN 0 WHEN 'high' THEN 1 WHEN 'normal' THEN 2 ELSE 3 END, q.id LIMIT 1''', (now,)).fetchone()
    if row is None:
        return None
    queue_id, task_id = row
    con.execute("UPDATE local_task_queue SET state='claimed',attempts=attempts+1,updated_at=CURRENT_TIMESTAMP WHERE id=? AND state='pending'", (queue_id,))
    log(con,queue_id,'claimed')
    return {'id':queue_id,'task_id':task_id}


def resolve(con, queue_id, success, error, now):
    row=con.execute('SELECT state,attempts,max_attempts FROM local_task_queue WHERE id=?',(queue_id,)).fetchone()
    if row is None or row[0]!='claimed':
        raise ValueError('처리 중인 대기열 항목이 아닙니다.')
    state='done' if success else ('failed' if row[1]>=row[2] else 'pending')
    delay=0 if success or state=='failed' else min(3600, 60 * (2 ** (row[1]-1)))
    con.execute('''UPDATE local_task_queue SET state=?,next_attempt_at=?,last_error=?,updated_at=CURRENT_TIMESTAMP WHERE id=?''',
                (state,now+delay,'' if success else error,queue_id))
    log(con,queue_id,state,error)
    return state


def recover_claimed(con, queue_id, now):
    """Owner-approved recovery after verifying the previous worker has stopped.

    Never silently replay a potentially side-effecting operation.
    """
    row = con.execute('SELECT state,attempts,max_attempts FROM local_task_queue WHERE id=?', (queue_id,)).fetchone()
    if row is None or row[0] != 'claimed':
        raise ValueError('복구할 선택 상태의 업무가 아닙니다.')
    state = 'failed' if row[1] >= row[2] else 'pending'
    due = now + 60 if state == 'pending' else now
    con.execute('UPDATE local_task_queue SET state=?,next_attempt_at=?,last_error=?,updated_at=CURRENT_TIMESTAMP WHERE id=?',
                (state,due,'관리자 확인 후 중단 작업 복구',queue_id))
    log(con,queue_id,'recovered',state)
    return state
