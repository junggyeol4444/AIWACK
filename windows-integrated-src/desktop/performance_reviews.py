"""Stage50: offline, owner-authored evidence-linked task performance reviews.

No LLM scoring, autonomous evaluation, financial action or task mutation.
Completion ratio is a descriptive count, not an AI quality measurement.
"""
from __future__ import annotations
import sqlite3

DECISIONS = frozenset({'proposed', 'accepted', 'rejected'})


def initialize(con: sqlite3.Connection) -> None:
    con.execute('''CREATE TABLE IF NOT EXISTS task_performance_reviews (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      task_id INTEGER NOT NULL UNIQUE REFERENCES company_tasks(id) ON DELETE RESTRICT,
      task_status TEXT NOT NULL CHECK(task_status IN ('done','blocked')),
      rating INTEGER NOT NULL CHECK(rating BETWEEN 1 AND 5),
      evidence TEXT NOT NULL CHECK(length(trim(evidence)) BETWEEN 1 AND 1000),
      lesson TEXT NOT NULL CHECK(length(trim(lesson)) BETWEEN 1 AND 1000),
      created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    )''')
    con.execute('''CREATE TABLE IF NOT EXISTS task_improvement_proposals (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      review_id INTEGER NOT NULL REFERENCES task_performance_reviews(id) ON DELETE RESTRICT,
      title TEXT NOT NULL CHECK(length(trim(title)) BETWEEN 1 AND 160),
      action TEXT NOT NULL CHECK(length(trim(action)) BETWEEN 1 AND 1000),
      expected_result TEXT NOT NULL CHECK(length(trim(expected_result)) BETWEEN 1 AND 1000),
      state TEXT NOT NULL DEFAULT 'proposed' CHECK(state IN ('proposed','accepted','rejected')),
      created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
      decided_at TEXT
    )''')
    con.execute('''CREATE TABLE IF NOT EXISTS task_improvement_decisions (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      proposal_id INTEGER NOT NULL UNIQUE REFERENCES task_improvement_proposals(id) ON DELETE RESTRICT,
      decision TEXT NOT NULL CHECK(decision IN ('accepted','rejected')),
      reason TEXT NOT NULL CHECK(length(trim(reason)) BETWEEN 1 AND 1000),
      decided_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    )''')
    con.execute('CREATE INDEX IF NOT EXISTS task_review_task_idx ON task_performance_reviews(task_id)')
    con.execute('CREATE INDEX IF NOT EXISTS task_improvement_review_idx ON task_improvement_proposals(review_id,id)')
    for table in ('task_performance_reviews', 'task_improvement_decisions'):
        con.execute(f'''CREATE TRIGGER IF NOT EXISTS {table}_no_update BEFORE UPDATE ON {table}
          BEGIN SELECT RAISE(ABORT, 'review history is append-only'); END''')
        con.execute(f'''CREATE TRIGGER IF NOT EXISTS {table}_no_delete BEFORE DELETE ON {table}
          BEGIN SELECT RAISE(ABORT, 'review history is append-only'); END''')
    con.execute('''CREATE TRIGGER IF NOT EXISTS task_improvement_proposals_guard_update
        BEFORE UPDATE ON task_improvement_proposals BEGIN
          SELECT RAISE(ABORT,'only decision transition allowed') WHERE
             OLD.review_id IS NOT NEW.review_id OR OLD.title IS NOT NEW.title
             OR OLD.action IS NOT NEW.action OR OLD.expected_result IS NOT NEW.expected_result
             OR OLD.created_at IS NOT NEW.created_at OR OLD.state!='proposed'
             OR NEW.state NOT IN ('accepted','rejected') OR NEW.decided_at IS NULL;
        END''')
    con.execute('''CREATE TRIGGER IF NOT EXISTS task_improvement_proposals_no_delete
        BEFORE DELETE ON task_improvement_proposals BEGIN
          SELECT RAISE(ABORT,'improvement proposals cannot be deleted');
        END''')


def _id(value, label='ID'):
    if type(value) is not int or value < 1:
        raise ValueError(f'{label}는 양의 정수여야 합니다.')
    return value


def _text(value, label, limit):
    if not isinstance(value, str) or not 1 <= len(value.strip()) <= limit:
        raise ValueError(f'{label}은 1~{limit}자여야 합니다.')
    return value.strip()


def _get(con, table, record_id, label):
    con.row_factory = sqlite3.Row
    item = con.execute(f'SELECT * FROM {table} WHERE id=?', (_id(record_id,label),)).fetchone()
    if item is None:
        raise ValueError(f'{label} 기록이 없습니다.')
    return dict(item)


def task_summary(con):
    """Snapshot of real internal task statuses, including tasks not reviewed.

    Exclude cancelled tasks from denominator; zeros mean 'not enough data'.
    These counts do not measure customer value, revenue or actual AI quality.
    """
    counts = dict(con.execute('SELECT status, COUNT(*) FROM company_tasks GROUP BY status'))
    result = {status: counts.get(status, 0) for status in ('todo','in_progress','blocked','done','cancelled')}
    eligible = sum(result[s] for s in ('todo','in_progress','blocked','done'))
    result['eligible'] = eligible
    result['completion_percent'] = round(result['done'] * 100 / eligible, 1) if eligible else None
    result['manual_reviews'] = con.execute('SELECT COUNT(*) FROM task_performance_reviews').fetchone()[0]
    result['pending_proposals'] = con.execute("SELECT COUNT(*) FROM task_improvement_proposals WHERE state='proposed'").fetchone()[0]
    return result


def review_task(con, task_id, rating, evidence, lesson):
    _id(task_id, '업무 ID')
    if type(rating) is not int or rating not in range(1,6):
        raise ValueError('수동 평가 점수는 1~5점이어야 합니다.')
    evidence = _text(evidence, '검증 근거', 1000)
    lesson = _text(lesson, '회고·교훈', 1000)
    task = con.execute('SELECT status FROM company_tasks WHERE id=?', (task_id,)).fetchone()
    if task is None:
        raise ValueError('평가할 업무가 없습니다.')
    if task[0] not in ('done','blocked'):
        raise ValueError('완료 또는 차단된 업무만 사후 평가할 수 있습니다.')
    if con.execute('SELECT 1 FROM task_performance_reviews WHERE task_id=?',(task_id,)).fetchone():
        raise ValueError('이미 평가된 업무입니다.')
    return int(con.execute('''INSERT INTO task_performance_reviews
      (task_id,task_status,rating,evidence,lesson) VALUES (?,?,?,?,?)''',
      (task_id,task[0],rating,evidence,lesson)).lastrowid)


def list_reviews(con, limit=200):
    if type(limit) is not int or not 1 <= limit <= 500:
        raise ValueError('조회 건수는 1~500건이어야 합니다.')
    con.row_factory = sqlite3.Row
    return [dict(r) for r in con.execute('''SELECT r.*,t.title AS task_title
       FROM task_performance_reviews r JOIN company_tasks t ON t.id=r.task_id
       ORDER BY r.id DESC LIMIT ?''',(limit,))]


def create_proposal(con, review_id, title, action, expected_result):
    _get(con,'task_performance_reviews',review_id,'평가')
    title = _text(title,'개선안 제목',160)
    action = _text(action,'개선 행동',1000)
    expected_result = _text(expected_result,'기대 효과(추정)',1000)
    return int(con.execute('''INSERT INTO task_improvement_proposals
       (review_id,title,action,expected_result) VALUES (?,?,?,?)''',
       (review_id,title,action,expected_result)).lastrowid)


def list_proposals(con, limit=200):
    if type(limit) is not int or not 1 <= limit <= 500:
        raise ValueError('조회 건수는 1~500건이어야 합니다.')
    con.row_factory = sqlite3.Row
    return [dict(r) for r in con.execute('''SELECT p.*,r.task_id,r.rating,
       d.reason AS decision_reason FROM task_improvement_proposals p
       JOIN task_performance_reviews r ON r.id=p.review_id
       LEFT JOIN task_improvement_decisions d ON d.proposal_id=p.id
       ORDER BY p.id DESC LIMIT ?''',(limit,))]


def decide_proposal(con, proposal_id, decision, reason):
    if decision not in ('accepted','rejected') or not isinstance(decision,str):
        raise ValueError('채택 또는 반려만 선택하세요.')
    reason = _text(reason,'결정 근거',1000)
    item = _get(con,'task_improvement_proposals',proposal_id,'개선안')
    if item['state'] != 'proposed':
        raise ValueError('이미 검토된 개선안입니다.')
    updated = con.execute('''UPDATE task_improvement_proposals SET state=?,decided_at=CURRENT_TIMESTAMP
      WHERE id=? AND state='proposed' ''',(decision,proposal_id))
    if updated.rowcount != 1:
        raise ValueError('이미 검토된 개선안입니다.')
    con.execute('''INSERT INTO task_improvement_decisions(proposal_id,decision,reason)
        VALUES(?,?,?)''',(proposal_id,decision,reason))
    return True
