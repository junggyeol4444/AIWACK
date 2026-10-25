"""Owner-enabled, auditable LOCAL recurring company operations (no LLM or purchases).

Tick processing is an explicitly opted-in, bounded local Windows EXE activity.
Persisted SQLite due-time claim prevents two concurrent EXE sessions from
generating the same proposals, scheduled tasks, or local event tasks.
"""
from __future__ import annotations
import time
import threading
from uuid import uuid4
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
        con.execute("""CREATE TABLE IF NOT EXISTS aiwack_autopilot_model_leases(
           task_id INTEGER PRIMARY KEY REFERENCES company_tasks(id),
           run_id INTEGER NOT NULL UNIQUE REFERENCES aiwack_autopilot_model_runs(id),
           owner_token TEXT NOT NULL CHECK(length(owner_token)=32),
           started_epoch INTEGER NOT NULL CHECK(started_epoch>0),
           created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)""")


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
        if _paused(store): raise InterruptedError('소유자가 실행을 중지했습니다.')
        failure_followups_created=len(store.scan_failed_employee_work(limit=31)['created'])
    except Exception as exc:
        _finish(store,run_id,'failed',counts,type(exc).__name__)
        raise
    _finish(store,run_id,'success',counts,'')
    return {'executed':True,'id':run_id,**counts,
            'failed_staff_followup_proposals':failure_followups_created,'model_called':False,
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


def _policy_active_read_only(store) -> bool:
    # No schema DDL in the 0.5-second cancellation watcher.
    with store._connect() as con:
        state=con.execute("""SELECT a.enabled,b.enabled FROM aiwack_autopilot_settings a
            CROSS JOIN aiwack_autopilot_model_policy b WHERE a.id=1 AND b.id=1""").fetchone()
        return bool(state and state[0] and state[1] and not stopped(con))


def approved_models_enabled(store) -> bool:
    initialize(store)
    return _policy_active_read_only(store)


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
    owner_token=uuid4().hex
    with store._connect() as con:
        con.execute('BEGIN IMMEDIATE')
        state=con.execute("""SELECT m.enabled,p.enabled FROM aiwack_autopilot_settings m
            CROSS JOIN aiwack_autopilot_model_policy p WHERE m.id=1 AND p.id=1""").fetchone()
        if state is None or not state[0] or not state[1] or stopped(con):
            raise PermissionError('실제 AI 작업 시작 전 소유자 자동 실행 허용이 해제됐습니다.')
        # Historical failures/successes remain immutable evidence. Automatic
        # model execution never retries the same task, including after crashes.
        previous=con.execute("""SELECT id,state FROM aiwack_autopilot_model_runs
            WHERE task_id=? ORDER BY id DESC LIMIT 1""",(tid,)).fetchone()
        if previous is not None:
            raise PermissionError(
                f'업무 #{tid} 자동 모델 시도 #{previous[0]}({previous[1]}) 존재. '
                '자동 중복 호출 금지; 기존 감사와 결과물을 관리자가 직접 검토하세요.')
        if con.execute("""SELECT 1 FROM aiwack_autopilot_model_leases
            WHERE task_id=?""",(tid,)).fetchone():
            raise PermissionError(f'업무 #{tid}는 다른 Windows 창이 실행 중입니다.')
        audit_id=int(con.execute("""INSERT INTO aiwack_autopilot_model_runs(task_id,state)
            VALUES(?,'running')""",(tid,)).lastrowid)
        con.execute("""INSERT INTO aiwack_autopilot_model_leases
            (task_id,run_id,owner_token,started_epoch) VALUES(?,?,?,?)""",
            (tid,audit_id,owner_token,int(time.time())))
    # Another EXE window may revoke the owner's separate model permission.
    # Poll persisted policy so the running GGUF subprocess also receives
    # cancellation, not only future ticks.
    signal=cancel if cancel is not None else threading.Event()
    watcher_stop=threading.Event()
    def observe_policy():
        while not watcher_stop.wait(0.5):
            try:
                allowed=_policy_active_read_only(store)
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
        with store._connect() as con:
            con.execute('BEGIN IMMEDIATE')
            if con.execute("""UPDATE aiwack_autopilot_model_runs
                SET state='success',finished_at=CURRENT_TIMESTAMP
                WHERE id=? AND state='running'""",(audit_id,)).rowcount!=1:
                raise RuntimeError('실행 중 감사가 변경돼 모델 성공을 기록하지 못했습니다.')
    except Exception as exc:
        with store._connect() as con:
            con.execute("""UPDATE aiwack_autopilot_model_runs
                SET state='failed',error_kind=?,finished_at=CURRENT_TIMESTAMP
                WHERE id=? AND state='running'""",(type(exc).__name__[:60],audit_id))
        raise
    finally:
        watcher_stop.set()
        watcher.join(timeout=2)
        # A failed call is never auto-retried; keep its audit row. Release
        # ONLY the lease owned by this run. Crashes retain the lease for review.
        with store._connect() as con:
            con.execute('BEGIN IMMEDIATE')
            con.execute("""DELETE FROM aiwack_autopilot_model_leases
                WHERE task_id=? AND run_id=? AND owner_token=?""",
                (tid,audit_id,owner_token))
    return {**result,'autopilot_model_audit_id':audit_id,
            'automatic_result_approval':False}


def running_model_leases(store, limit: int=100) -> list[dict]:
    """Persisted model claims across Windows EXE windows; never assume stale means stopped."""
    initialize(store)
    if type(limit) is not int or not 1<=limit<=100:
        raise ValueError('자동 모델 잠금 조회는 1~100건입니다.')
    with store._connect() as con:
        rows=con.execute("""SELECT l.task_id,l.run_id,l.started_epoch,r.state
            FROM aiwack_autopilot_model_leases l
            JOIN aiwack_autopilot_model_runs r ON r.id=l.run_id
            ORDER BY l.started_epoch,l.task_id LIMIT ?""",(limit,)).fetchall()
    return [{'task_id':int(task),'run_id':int(run),'started_epoch':int(epoch),
             'audit_state':state,'actual_process_running_verified':False}
            for task,run,epoch,state in rows]


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


def operational_diagnostics(store, *, now=None) -> dict:
    """Read-only evidence of local ticks, not a synthetic 24h uptime claim.

    A stale running row requires owner review, never an automatic retry.
    """
    store.require_permission('company:manage')
    stamp=int(time.time()) if now is None else now
    if type(stamp) is not int or stamp < 0:
        raise ValueError('운영 진단 시각이 올바르지 않습니다.')
    with store._connect() as con:
        exists=con.execute("SELECT 1 FROM sqlite_master WHERE type='table' "
                           "AND name='aiwack_autopilot_settings'").fetchone()
        if not exists:
            return dict(enabled=False,model_policy_enabled=False,
                emergency_stop=bool(stopped(con)),next_due_epoch=0,
                interval_seconds=300,tick_overdue=False,
                unfinished_tick_records=0,unfinished_model_records=0,
                observed_success_ticks_last_24h=0,observed_failed_ticks_last_24h=0,
                last_recorded_tick_epoch=None,last_recorded_tick_state=None,
                verified_continuous_24h=False,external_business_verified=False)
        enabled,interval,due=con.execute('''SELECT enabled,interval_seconds,next_due
            FROM aiwack_autopilot_settings WHERE id=1''').fetchone()
        running=con.execute("SELECT COUNT(*) FROM aiwack_autopilot_runs WHERE state='running'").fetchone()[0]
        succeeded=con.execute('''SELECT COUNT(*) FROM aiwack_autopilot_runs
            WHERE state='success' AND planned_at>=? AND planned_at<=?''',
            (max(0,stamp-86400),stamp)).fetchone()[0]
        failures=con.execute('''SELECT COUNT(*) FROM aiwack_autopilot_runs
            WHERE state='failed' AND planned_at>=? AND planned_at<=?''',
            (max(0,stamp-86400),stamp)).fetchone()[0]
        last=con.execute('''SELECT planned_at,state FROM aiwack_autopilot_runs
            WHERE planned_at<=? ORDER BY id DESC LIMIT 1''',(stamp,)).fetchone()
        model_running=con.execute("SELECT COUNT(*) FROM aiwack_autopilot_model_runs WHERE state='running'").fetchone()[0]
        policy=con.execute('SELECT enabled FROM aiwack_autopilot_model_policy WHERE id=1').fetchone()
        emergency=bool(stopped(con))
    overdue=bool(enabled and not emergency and due and stamp>due+interval)
    return dict(enabled=bool(enabled),model_policy_enabled=bool(policy and policy[0]),
                emergency_stop=emergency,next_due_epoch=int(due),
                interval_seconds=int(interval),tick_overdue=overdue,
                unfinished_tick_records=int(running),unfinished_model_records=int(model_running),
                observed_success_ticks_last_24h=int(succeeded),
                observed_failed_ticks_last_24h=int(failures),
                last_recorded_tick_epoch=None if last is None else int(last[0]),
                last_recorded_tick_state=None if last is None else str(last[1]),
                verified_continuous_24h=False,external_business_verified=False)
