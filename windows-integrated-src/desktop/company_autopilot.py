"""Owner-enabled, auditable LOCAL recurring company operations (no LLM or purchases).

Tick processing is an explicitly opted-in, bounded local Windows EXE activity.
Persisted SQLite due-time claim prevents two concurrent EXE sessions from
generating the same proposals, scheduled tasks, or local event tasks.
"""
from __future__ import annotations
import time
import threading
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
        con.execute("""CREATE TABLE IF NOT EXISTS aiwack_autopilot_model_policy(
           id INTEGER PRIMARY KEY CHECK(id=1),
           enabled INTEGER NOT NULL DEFAULT 0 CHECK(enabled IN (0,1)))""")
        con.execute("INSERT OR IGNORE INTO aiwack_autopilot_model_policy(id) VALUES(1)")
        con.execute("""CREATE TABLE IF NOT EXISTS aiwack_autopilot_model_runs(
           id INTEGER PRIMARY KEY AUTOINCREMENT,
           task_id INTEGER NOT NULL REFERENCES company_tasks(id),
           state TEXT NOT NULL CHECK(state IN ('running','success','failed')),
           error_kind TEXT NOT NULL DEFAULT '',
           created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
           finished_at TEXT)""")


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
        if not enabled:
            con.execute("UPDATE aiwack_autopilot_model_policy SET enabled=0 WHERE id=1")
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



def configure_approved_models(store, enabled: bool) -> bool:
    """A SECOND explicit owner consent is mandatory before real model calls."""
    store.require_permission('company:manage')
    if type(enabled) is not bool:
        raise ValueError('실제 AI 승인 업무 자동 실행 선택이 잘못되었습니다.')
    initialize(store)
    with store._connect() as con:
        con.execute('BEGIN IMMEDIATE')
        state=con.execute('SELECT enabled FROM aiwack_autopilot_settings WHERE id=1').fetchone()
        if enabled and (not state or not state[0] or stopped(con)):
            raise PermissionError('자동 운영 활성화 및 비상정지 해제가 필요합니다.')
        con.execute('UPDATE aiwack_autopilot_model_policy SET enabled=? WHERE id=1',(int(enabled),))
    return enabled


def approved_models_enabled(store) -> bool:
    initialize(store)
    with store._connect() as con:
        state=con.execute("""SELECT a.enabled,b.enabled FROM aiwack_autopilot_settings a
            CROSS JOIN aiwack_autopilot_model_policy b WHERE a.id=1 AND b.id=1""").fetchone()
        return bool(state and state[0] and state[1] and not stopped(con))


def run_one_approved_model(store, task_ids: tuple[int, ...], *, cancel=None) -> dict:
    """One already owner-approved staff inference + real chief review per tick.

    Never auto-approves an unapproved order or retries a previous failed call.
    """
    from desktop import company_operations as ops
    if (type(task_ids) is not tuple or len(task_ids)!=1
            or type(task_ids[0]) is not int or task_ids[0]<=0):
        raise ValueError('관리자가 승인한 정확한 업무 번호 하나가 필요합니다.')
    if not approved_models_enabled(store):
        raise PermissionError('별도 승인된 AI 자동 실행 정책이 비활성화됐습니다.')
    tid=task_ids[0]
    with store._connect() as con:
        con.execute('BEGIN IMMEDIATE')
        audit_id=int(con.execute("""INSERT INTO aiwack_autopilot_model_runs(task_id,state)
                               VALUES(?,'running')""",(tid,)).lastrowid)
    # Another EXE window may revoke the owner's separate model permission.
    # Poll persisted policy so the running GGUF subprocess also receives
    # cancellation, not only future ticks.
    signal=cancel if cancel is not None else threading.Event()
    watcher_stop=threading.Event()
    def observe_policy():
        while not watcher_stop.wait(0.5):
            try:
                allowed=approved_models_enabled(store)
            except Exception:
                allowed=False
            if not allowed:
                signal.set()
                break
    watcher=threading.Thread(target=observe_policy,name='AIWACK-owner-model-policy',daemon=True)
    watcher.start()
    try:
        if signal.is_set():
            raise InterruptedError('승인된 직원 자동 실행이 취소됐습니다.')
        result=ops.execute_approved_chief_queue(
            store,limit=1,expected_task_ids=task_ids,cancel=signal)
        if signal.is_set() or not approved_models_enabled(store):
            raise InterruptedError('소유자가 실제 AI 자동 실행 정책을 해제했습니다.')
        if result['completed_cycles']!=1 or result['auto_approved']:
            raise RuntimeError('승인 업무의 실제 직원·총괄 검토 기록이 불완전합니다.')
    except Exception as exc:
        with store._connect() as con:
            con.execute("""UPDATE aiwack_autopilot_model_runs
                SET state='failed',error_kind=?,finished_at=CURRENT_TIMESTAMP
                WHERE id=? AND state='running'""",(type(exc).__name__[:60],audit_id))
        raise
    finally:
        watcher_stop.set()
        watcher.join(timeout=2)
    with store._connect() as con:
        con.execute("""UPDATE aiwack_autopilot_model_runs
            SET state='success',finished_at=CURRENT_TIMESTAMP
            WHERE id=? AND state='running'""",(audit_id,))
    return {**result,'autopilot_model_audit_id':audit_id,
            'automatic_result_approval':False}


def approved_model_history(store, limit: int=30) -> list[dict]:
    initialize(store)
    if type(limit) is not int or not 1<=limit<=100:
        raise ValueError('실제 AI 자동 실행 감사 조회 제한 초과')
    with store._connect() as con:
        return [dict(zip(('id','task_id','state','error_kind'),row))
            for row in con.execute("""SELECT id,task_id,state,error_kind
               FROM aiwack_autopilot_model_runs ORDER BY id DESC LIMIT ?""",(limit,))]


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
