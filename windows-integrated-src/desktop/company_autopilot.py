"""Owner-enabled, auditable LOCAL recurring company operations (no LLM or purchases).

Tick processing is an explicitly opted-in, bounded local Windows EXE activity.
Persisted SQLite due-time claim prevents two concurrent EXE sessions from
generating the same proposals, scheduled tasks, or local event tasks.
"""
from __future__ import annotations
import time
from desktop.stage87_90_management import stopped


def initialize(store):
    store.require_permission('company:manage')
    with store._connect() as con:
        con.execute("""CREATE TABLE IF NOT EXISTS aiwack_autopilot_settings(
           id INTEGER PRIMARY KEY CHECK(id=1), enabled INTEGER NOT NULL DEFAULT 0
           CHECK(enabled IN (0,1)), interval_seconds INTEGER NOT NULL DEFAULT 300
           CHECK(interval_seconds BETWEEN 60 AND 3600),
           next_due INTEGER NOT NULL DEFAULT 0 CHECK(next_due>=0))""")
        con.execute("""CREATE TABLE IF NOT EXISTS aiwack_autopilot_runs(
           id INTEGER PRIMARY KEY AUTOINCREMENT, planned_at INTEGER NOT NULL,
           state TEXT NOT NULL CHECK(state IN ('running','success','failed')),
           proposal_created INTEGER NOT NULL DEFAULT 0,
           schedule_created INTEGER NOT NULL DEFAULT 0,
           event_created INTEGER NOT NULL DEFAULT 0,
           error_kind TEXT NOT NULL DEFAULT '',
           started_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
           finished_at TEXT)""")
        con.execute("INSERT OR IGNORE INTO aiwack_autopilot_settings(id) VALUES(1)")


def settings(store):
    initialize(store)
    with store._connect() as con:
        state=con.execute("SELECT enabled,interval_seconds,next_due FROM aiwack_autopilot_settings WHERE id=1").fetchone()
        count=con.execute("SELECT COUNT(*) FROM aiwack_autopilot_runs").fetchone()[0]
    return {'enabled':bool(state[0]),'interval_seconds':int(state[1]),
            'next_due':int(state[2]),'runs':int(count)}


def configure(store, enabled: bool, *, interval_minutes: int=5, now=None):
    store.require_permission('company:manage')
    if type(enabled) is not bool or type(interval_minutes) is not int or not 1<=interval_minutes<=60:
        raise ValueError('자동 운영 간격은 1~60분이며 사용 여부는 참/거짓이어야 합니다.')
    stamp=int(time.time()) if now is None else now
    if type(stamp) is not int or stamp<0:
        raise ValueError('잘못된 운영 시각입니다.')
    initialize(store)
    with store._connect() as con:
        con.execute('BEGIN IMMEDIATE')
        con.execute("UPDATE aiwack_autopilot_settings SET enabled=?,interval_seconds=?,next_due=? WHERE id=1",
                    (int(enabled),interval_minutes*60,stamp if enabled else 0))
    return settings(store)


def run_once(store, *, now=None):
    store.require_permission('company:manage')
    stamp=int(time.time()) if now is None else now
    if type(stamp) is not int or stamp<0:
        raise ValueError('자동 운영 시각이 올바르지 않습니다.')
    initialize(store)
    with store._connect() as con:
        con.execute('BEGIN IMMEDIATE')
        enabled, interval, due=con.execute(
            'SELECT enabled,interval_seconds,next_due FROM aiwack_autopilot_settings WHERE id=1').fetchone()
        if not enabled:
            return {'executed':False,'reason':'disabled'}
        if stopped(con):
            return {'executed':False,'reason':'emergency_stop'}
        if due>stamp:
            return {'executed':False,'reason':'not_due'}
        con.execute("UPDATE aiwack_autopilot_settings SET next_due=? WHERE id=1",(stamp+interval,))
        run_id=int(con.execute("INSERT INTO aiwack_autopilot_runs(planned_at,state) VALUES(?,'running')",
            (stamp,)).lastrowid)
    counts={'proposal_created':0,'schedule_created':0,'event_created':0}
    try:
        if _paused(store): raise InterruptedError('소유자가 실행을 중지했습니다.')
        counts['proposal_created']=len(store.scan_autonomous_task_proposals(limit=10)['created_ids'])
        if _paused(store): raise InterruptedError('소유자가 실행을 중지했습니다.')
        counts['schedule_created']=len(store.run_due_recurring_schedules(now=stamp))
        if _paused(store): raise InterruptedError('소유자가 실행을 중지했습니다.')
        counts['event_created']=len(store.dispatch_local_events(limit=10))
    except Exception as exc:
        _finish(store,run_id,'failed',counts,type(exc).__name__)
        raise
    _finish(store,run_id,'success',counts,'')
    return {'executed':True,'id':run_id,**counts,'model_called':False,
            'owner_approval_required':True,'external_actions':False}


def _paused(store):
    with store._connect() as con:
        row=con.execute('SELECT enabled FROM aiwack_autopilot_settings WHERE id=1').fetchone()
        return stopped(con) or not row or not row[0]


def _finish(store,run_id,state,counts,error):
    with store._connect() as con:
        con.execute("""UPDATE aiwack_autopilot_runs SET state=?,
            proposal_created=?,schedule_created=?,event_created=?,
            error_kind=?,finished_at=CURRENT_TIMESTAMP
            WHERE id=? AND state='running'""",
            (state,counts['proposal_created'],counts['schedule_created'],
             counts['event_created'],error[:60],run_id))


def history(store,limit=30):
    initialize(store)
    if type(limit) is not int or not 1<=limit<=100:
        raise ValueError('운영 기록 조회는 1~100건만 가능합니다.')
    with store._connect() as con:
        return [dict(zip(('id','planned_at','state','proposal_created','schedule_created',
                          'event_created','error_kind'),x))
                for x in con.execute("""SELECT id,planned_at,state,proposal_created,
                   schedule_created,event_created,error_kind
                   FROM aiwack_autopilot_runs ORDER BY id DESC LIMIT ?""",(limit,))]
