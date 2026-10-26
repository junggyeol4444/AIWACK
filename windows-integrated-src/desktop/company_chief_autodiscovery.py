"""Windows AIWACK 자율 운영: 실제 총괄 GGUF의 주기적 업무 발견.

기존 회사 자율 운영 + 실제 모델 허용과 별개의 "총괄 신규업무 자동 발견"
소유자 명시 허용이 모두 필요하다. 한 번 설정한 뒤 GUI가 실행되는 동안
업무 초안 발견을 재개하지만 모든 작업은 불활성 초안이며 개별 관리자
승인 없이는 직원 실행, 계약, 외부 거래, 발송을 하지 않는다.
"""
from __future__ import annotations

import threading
import time

from desktop.stage87_90_management import stopped


def initialize(con):
    con.execute("""CREATE TABLE IF NOT EXISTS aiwack_chief_autodiscovery_policy(
        id INTEGER PRIMARY KEY CHECK(id=1),
        enabled INTEGER NOT NULL DEFAULT 0 CHECK(enabled IN (0,1)),
        interval_seconds INTEGER NOT NULL DEFAULT 3600
            CHECK(interval_seconds BETWEEN 900 AND 86400),
        next_due_epoch INTEGER NOT NULL DEFAULT 0 CHECK(next_due_epoch>=0))""")
    con.execute("""INSERT OR IGNORE INTO aiwack_chief_autodiscovery_policy(id)
        VALUES(1)""")
    con.execute("""CREATE TABLE IF NOT EXISTS aiwack_chief_autodiscovery_runs(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        due_epoch INTEGER NOT NULL,
        state TEXT NOT NULL DEFAULT 'running'
            CHECK(state IN ('running','success','failed','cancelled')),
        discovery_id INTEGER REFERENCES aiwack_chief_department_discoveries(id),
        proposals_created INTEGER NOT NULL DEFAULT 0
            CHECK(proposals_created BETWEEN 0 AND 5),
        error_kind TEXT NOT NULL DEFAULT '',
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        finished_at TEXT)""")
    con.execute("""CREATE TABLE IF NOT EXISTS aiwack_chief_autodiscovery_events(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        run_id INTEGER NOT NULL REFERENCES aiwack_chief_autodiscovery_runs(id),
        event_kind TEXT NOT NULL CHECK(event_kind IN ('claimed','finished','failed','cancelled','owner_closed')),
        detail TEXT NOT NULL DEFAULT '',
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(run_id,event_kind))""")
    for op in ("UPDATE", "DELETE"):
        con.execute("""CREATE TRIGGER IF NOT EXISTS aiwack_chief_auto_events_immutable_%s
            BEFORE %s ON aiwack_chief_autodiscovery_events
            BEGIN SELECT RAISE(ABORT,'총괄 자율 발견 원본 감사 변경·삭제 금지'); END"""
            % (op.lower(), op))


def _existing_authorizations(con):
    record=con.execute("""SELECT a.enabled,m.enabled FROM aiwack_autopilot_settings a
        CROSS JOIN aiwack_autopilot_model_policy m WHERE a.id=1 AND m.id=1""").fetchone()
    return bool(record and record[0] and record[1] and not stopped(con))


def _policy_on(con):
    enabled=con.execute("""SELECT enabled FROM aiwack_chief_autodiscovery_policy
        WHERE id=1""").fetchone()
    return bool(enabled and enabled[0] and _existing_authorizations(con))


def configure(store, enabled, *, interval_minutes=60):
    store.require_permission("company:manage")
    store.require_permission("agents:manage")
    if type(enabled) is not bool:
        raise ValueError("총괄 자동 업무 발견 정책 형식 오류")
    if type(interval_minutes) is not int or not 15<=interval_minutes<=1440:
        raise ValueError("총괄 GGUF 자율 발견 간격은 15~1440분입니다.")
    from desktop import company_autopilot
    company_autopilot.initialize(store)
    now=int(time.time())
    with store._connect() as con:
        con.execute("BEGIN IMMEDIATE")
        initialize(con)
        if enabled and not _existing_authorizations(con):
            raise PermissionError("기존 자율 운영 및 실제 모델 실행 이중 동의를 먼저 활성화하세요.")
        pending=con.execute("""SELECT COUNT(*) FROM aiwack_chief_autodiscovery_runs
            WHERE state='running'""").fetchone()[0]
        if enabled and pending:
            raise PermissionError("종료 확인되지 않은 실제 총괄 모델 발견 회차가 있어 재활성화 금지")
        con.execute("""UPDATE aiwack_chief_autodiscovery_policy
            SET enabled=?, interval_seconds=?,next_due_epoch=?
            WHERE id=1""",(int(enabled),interval_minutes*60,
                          now if enabled else 0))
    return status(store)


def status(store):
    store.require_permission("company:manage")
    from desktop import company_autopilot
    company_autopilot.initialize(store)
    with store._connect() as con:
        initialize(con)
        row=con.execute("""SELECT enabled,interval_seconds,next_due_epoch
            FROM aiwack_chief_autodiscovery_policy WHERE id=1""").fetchone()
        unfinished=con.execute("""SELECT COUNT(*) FROM aiwack_chief_autodiscovery_runs
            WHERE state='running'""").fetchone()[0]
        waiting=con.execute("""SELECT COUNT(*) FROM aiwack_chief_department_proposals p
            LEFT JOIN aiwack_chief_department_proposal_decisions d
                ON d.proposal_id=p.id WHERE d.id IS NULL""").fetchone()[0] if con.execute(
                    "SELECT 1 FROM sqlite_master WHERE type='table' AND name='aiwack_chief_department_proposals'"
                ).fetchone() else 0
        on=_policy_on(con)
    return {"enabled":bool(row[0]),"interval_minutes":int(row[1])//60,
            "next_due_epoch":int(row[2]),
            "existing_autopilot_and_model_consent":on,
            "unfinished_actual_model_runs":int(unfinished),
            "pending_owner_proposals":int(waiting),
            "automatic_owner_approval":False,
            "automatic_employee_execution":False}


def due(store, *, now=None):
    """읽기 전용 폴링용, AI 모델 호출이나 일정 갱신 없음."""
    store.require_permission("company:manage")
    stamp=int(time.time()) if now is None else now
    if type(stamp) is not int or stamp<0:
        raise ValueError("모델 발견 폴링 시각 오류")
    with store._connect() as con:
        if not con.execute("""SELECT 1 FROM sqlite_master WHERE type='table'
             AND name='aiwack_chief_autodiscovery_policy'""").fetchone():
            return False
        row=con.execute("""SELECT enabled,next_due_epoch FROM aiwack_chief_autodiscovery_policy
             WHERE id=1""").fetchone()
        if not row or not row[0] or row[1]>stamp or not _policy_on(con):
            return False
        if con.execute("""SELECT 1 FROM aiwack_chief_autodiscovery_runs
            WHERE state='running' LIMIT 1""").fetchone():
            return False
        if con.execute("""SELECT 1 FROM aiwack_chief_department_proposals p
            LEFT JOIN aiwack_chief_department_proposal_decisions d
                ON d.proposal_id=p.id WHERE d.id IS NULL LIMIT 1""").fetchone() if con.execute(
                    """SELECT 1 FROM sqlite_master WHERE type='table'
                    AND name='aiwack_chief_department_proposals'""").fetchone() else False:
            return False
        return True


def _still_allowed(store):
    with store._connect() as con:
        return _policy_on(con)


def run_due(store, *, cancel=None, now=None):
    """현재 주기에 1회 실제 GGUF 호출을 소유; 스냅샷 중복 시 실패 감사만 남김."""
    store.require_permission("company:manage")
    store.require_permission("agents:manage")
    if cancel is not None and cancel.is_set():
        raise InterruptedError("관리자 모델 실행 취소")
    stamp=int(time.time()) if now is None else now
    if type(stamp) is not int or stamp<0:
        raise ValueError("총괄 모델 실행 시각 오류")
    from desktop import company_autopilot
    company_autopilot.initialize(store)
    with store._connect() as con:
        con.execute("BEGIN IMMEDIATE")
        initialize(con)
        row=con.execute("""SELECT enabled,interval_seconds,next_due_epoch
            FROM aiwack_chief_autodiscovery_policy WHERE id=1""").fetchone()
        if not row or not row[0] or not _policy_on(con):
            return {"executed":False,"reason":"not_enabled"}
        if int(row[2])>stamp:
            return {"executed":False,"reason":"not_due"}
        if con.execute("""SELECT 1 FROM aiwack_chief_autodiscovery_runs
            WHERE state='running' LIMIT 1""").fetchone():
            return {"executed":False,"reason":"unfinished_previous_model"}
        if con.execute("""SELECT 1 FROM sqlite_master WHERE type='table'
            AND name='aiwack_chief_department_proposals'""").fetchone():
            if con.execute("""SELECT 1 FROM aiwack_chief_department_proposals p
                LEFT JOIN aiwack_chief_department_proposal_decisions d
                    ON d.proposal_id=p.id WHERE d.id IS NULL LIMIT 1""").fetchone():
                return {"executed":False,"reason":"awaiting_owner_review"}
        con.execute("""UPDATE aiwack_chief_autodiscovery_policy SET next_due_epoch=?
            WHERE id=1""",(stamp+int(row[1]),))
        run_id=int(con.execute("""INSERT INTO aiwack_chief_autodiscovery_runs(due_epoch)
            VALUES(?)""",(stamp,)).lastrowid)
        con.execute("""INSERT INTO aiwack_chief_autodiscovery_events(run_id,event_kind)
            VALUES(?,'claimed')""",(run_id,))
    signal=cancel if cancel is not None else threading.Event()
    watchdog_stop=threading.Event()
    def policy_watcher():
        while not watchdog_stop.wait(0.5):
            try:
                alive=_still_allowed(store)
            except Exception:
                alive=False
            if not alive:
                signal.set()
                break
    observer=threading.Thread(target=policy_watcher,name="AIWACK-Chief-Autodiscovery-Policy",daemon=True)
    observer.start()
    result=None
    state="failed"
    error=""
    try:
        if signal.is_set() or not _still_allowed(store):
            raise InterruptedError("총괄 자동 발견 정책 취소")
        from desktop.company_chief_department_discovery import discover
        result=discover(store,cancel=signal)
        if signal.is_set() or not _still_allowed(store):
            raise InterruptedError("자동 발견 결과 저장 후 관리자가 정책 해제")
        state="success"
        return {"executed":True,"autodiscovery_run_id":run_id,
                "real_model_call_id":result["model_call_id"],
                "discovery_id":result["discovery_id"],
                "proposed_tasks":result["proposed_tasks"],
                "owner_approval_required":True,"employee_executed":False,
                "external_actions":False}
    except Exception as exc:
        state="cancelled" if isinstance(exc,InterruptedError) else "failed"
        error=type(exc).__name__[:70]
        raise
    finally:
        watchdog_stop.set()
        observer.join(timeout=2)
        # Never turn an incomplete process into a fake successful execution.
        with store._connect() as con:
            con.execute("BEGIN IMMEDIATE")
            if con.execute("""UPDATE aiwack_chief_autodiscovery_runs
                SET state=?,discovery_id=?,proposals_created=?,error_kind=?,
                    finished_at=CURRENT_TIMESTAMP
                WHERE id=? AND state='running'""",(
                    state,result["discovery_id"] if result else None,
                    result["proposed_tasks"] if result else 0,
                    error,run_id)).rowcount == 1:
                con.execute("""INSERT INTO aiwack_chief_autodiscovery_events
                    (run_id,event_kind,detail) VALUES(?,?,?)""",(
                    run_id,"finished" if state=="success" else state,error))


def history(store, *, limit=50):
    store.require_permission("company:manage")
    if type(limit) is not int or not 1<=limit<=100:
        raise ValueError("총괄 자동 발견 이력 1~100건만 조회 가능합니다.")
    with store._connect() as con:
        initialize(con)
        rows=con.execute("""SELECT r.id,r.due_epoch,r.state,r.discovery_id,
            r.proposals_created,r.error_kind,r.created_at,r.finished_at,
            (SELECT COUNT(*) FROM aiwack_chief_autodiscovery_events e
             WHERE e.run_id=r.id)
            FROM aiwack_chief_autodiscovery_runs r ORDER BY r.id DESC LIMIT ?""",
            (limit,)).fetchall()
    names=("id","due_epoch","state","discovery_id","proposals_created",
           "error_kind","created_at","finished_at","audit_event_count")
    return [dict(zip(names,r)) for r in rows]


def close_interrupted(store, run_id, note, *, owner_confirmed=False):
    """실제 모델 프로세스 수동 확인 후 비정상 종료 실행 회차 감사만 닫는다."""
    store.require_permission("company:manage")
    store.require_permission("agents:manage")
    if type(run_id) is not int or run_id<=0:
        raise ValueError("총괄 모델 중단 회차 번호 오류")
    if type(note) is not str or not 5<=len(note.strip())<=200:
        raise ValueError("중단 총괄 업무 확인 사유 5~200자 입력")
    if owner_confirmed is not True:
        raise PermissionError("실제 모델 종료 관리자 확인 필수")
    with store._connect() as con:
        con.execute("BEGIN IMMEDIATE")
        initialize(con)
        existing=con.execute("""SELECT state FROM aiwack_chief_autodiscovery_runs
            WHERE id=?""",(run_id,)).fetchone()
        if not existing or existing[0]!="running":
            raise ValueError("완료 또는 존재하지 않는 자동 발견 회차")
        # A live GGUF process is not inferred dead merely from timestamp.
        if con.execute("""SELECT 1 FROM ai_model_call_history
            WHERE status='running' LIMIT 1""").fetchone():
            raise PermissionError("실제 모델 실행 중 감사 기록 있음, 종료 금지")
        if con.execute("""SELECT 1 FROM aiwack_autopilot_model_leases LIMIT 1""").fetchone():
            raise PermissionError("직원 AI 실행 잠금이 남아 있습니다.")
        con.execute("""UPDATE aiwack_chief_autodiscovery_runs SET
            state='cancelled',error_kind='owner_inspected_interruption',
            finished_at=CURRENT_TIMESTAMP WHERE id=? AND state='running'""",(run_id,))
        con.execute("""INSERT INTO aiwack_chief_autodiscovery_events
            (run_id,event_kind,detail) VALUES(?,'owner_closed',?)""",
            (run_id,note.strip()))
    return {"run_id":run_id,"state":"cancelled",
            "model_reexecuted":False,"existing_model_audit_preserved":True}
