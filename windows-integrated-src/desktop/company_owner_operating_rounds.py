"""AIWACK 실제 승인 업무를 전사 연속 처리하는 소유자 1회 실행 경계.

자율 회사의 원본 총괄→직원→부서장→총괄 실행 경로를 조립하되
**신규 업무 승인, 부서장 의견 승인, 최종 총괄 보고 승인** 은 생성하지 않는다.
각 기존 하위 단계는 자신의 GGUF 프로세스 소유권·원본 SQLite 감사를 유지.
비정상 종료 후 자동 replay를 차단하고 원본 실행 기록을 보존한다.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
import threading

from desktop.stage87_90_management import stopped


def initialize(con):
    con.execute("""CREATE TABLE IF NOT EXISTS aiwack_owner_operating_rounds(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        note TEXT NOT NULL CHECK(length(note) BETWEEN 5 AND 200),
        max_employee_jobs INTEGER NOT NULL CHECK(max_employee_jobs BETWEEN 1 AND 30),
        max_chief_reviews INTEGER NOT NULL CHECK(max_chief_reviews BETWEEN 1 AND 10),
        state TEXT NOT NULL CHECK(state IN ('running','finished','failed','cancelled')),
        initial_evidence_sha256 TEXT NOT NULL CHECK(length(initial_evidence_sha256)=64),
        staff_batch_id INTEGER,
        chief_batch_id INTEGER,
        staff_completed INTEGER NOT NULL DEFAULT 0,
        chief_completed INTEGER NOT NULL DEFAULT 0,
        exit_reason TEXT NOT NULL DEFAULT '',
        started_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        closed_at TEXT)""")
    con.execute("""CREATE TABLE IF NOT EXISTS aiwack_owner_operating_round_events(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        round_id INTEGER NOT NULL REFERENCES aiwack_owner_operating_rounds(id),
        kind TEXT NOT NULL CHECK(kind IN ('opened','staff_stage',
            'chief_stage','finished','failed','cancelled','owner_closed')),
        detail TEXT NOT NULL DEFAULT '',
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)""")
    for action in ("UPDATE","DELETE"):
        con.execute("""CREATE TRIGGER IF NOT EXISTS aiwack_operating_round_event_no_%s
            BEFORE %s ON aiwack_owner_operating_round_events
            BEGIN SELECT RAISE(ABORT,'AIWACK 전체 운영 원본 감사 변경 금지'); END"""
            % (action.lower(),action))


def _positive(value,limit,label):
    if type(value) is not int or not 1<=value<=limit:
        raise ValueError(label+" 1~"+str(limit)+" 범위")
    return value


def _note(value):
    if type(value) is not str or not 5<=len(value.strip())<=200:
        raise ValueError("전체 운영 회차 관리자 사유 5~200자")
    return value.strip()


def _evidence(con):
    # Record an actual input fingerprint, not a synthetic model/financial
    # success claim. Only existing ready and owner-forwarded IDs are included.
    from desktop.company_owner_model_queue import initialize as init_queue
    from desktop.company_head_chief_handoff_queue import initialize as init_chief
    from desktop.company_model_queue_readiness import _first_ready_in_tx
    from desktop.company_head_chief_handoff_queue import _candidates
    init_queue(con)
    init_chief(con)
    pending=_first_ready_in_tx(con)
    chief=_candidates(con,10)
    data={"first_ready_employee_task":pending["task_id"] if pending else None,
          "chief_forwarded_artifacts":[r["artifact_id"] for r in chief]}
    raw=json.dumps(data,ensure_ascii=False,sort_keys=True,separators=(",",":"))
    return data,hashlib.sha256(raw.encode("utf8")).hexdigest()


def preview(store):
    store.require_permission("company:manage")
    from desktop import company_autopilot
    company_autopilot.initialize(store)
    with store._connect() as con:
        initialize(con)
        evidence,digest=_evidence(con)
        pending=con.execute("""SELECT COUNT(*) FROM aiwack_owner_operating_rounds
            WHERE state='running'""").fetchone()[0]
    return {"actual_ready_snapshot":evidence,"sha256":digest,
            "unfinished_manual_rounds":int(pending),
            "owner_must_explicitly_invoke":True,
            "all_employee_results_final_approved":False,
            "real_revenue_confirmed":False}


def _event(con,round_id,kind,detail=""):
    con.execute("""INSERT INTO aiwack_owner_operating_round_events
        (round_id,kind,detail) VALUES(?,?,?)""",(round_id,kind,detail))


def run(store,*,max_employee_jobs=10,max_chief_reviews=10,
        owner_note,cancel:threading.Event|None=None):
    store.require_permission("company:manage")
    store.require_permission("agents:manage")
    _positive(max_employee_jobs,30,"실제 직원 업무 수")
    _positive(max_chief_reviews,10,"실제 총괄 회수 수")
    note=_note(owner_note)
    if cancel is not None and cancel.is_set():
        raise InterruptedError("전사 모델 호출 전 취소")
    from desktop import company_autopilot
    from desktop import company_approved_queue_batch as batch
    from desktop import company_head_chief_handoff_queue as handoff
    company_autopilot.initialize(store)
    if not company_autopilot.approved_models_enabled(store):
        raise PermissionError("원본 자율 운영 및 실제 모델 사용 소유자 이중 허용 필요")
    with store._connect() as con:
        con.execute("BEGIN IMMEDIATE")
        initialize(con)
        if stopped(con):raise PermissionError("비상정지 중 전사 GGUF 실행 금지")
        if con.execute("""SELECT 1 FROM aiwack_owner_operating_rounds
            WHERE state='running'""").fetchone():
            raise PermissionError("이전 전사 GGUF 회차 미종료. 실제 모델 관리자 확인 필요")
        evidence,digest=_evidence(con)
        if evidence["first_ready_employee_task"] is None and \
           not evidence["chief_forwarded_artifacts"]:
            return {"executed":False,"reason":"no_approved_ready_work",
                    "models_invoked":False}
        round_id=int(con.execute("""INSERT INTO aiwack_owner_operating_rounds
            (note,max_employee_jobs,max_chief_reviews,state,initial_evidence_sha256)
            VALUES(?,?,?,'running',?)""",
            (note,max_employee_jobs,max_chief_reviews,digest)).lastrowid)
        _event(con,round_id,"opened",detail="개별 승인 원본 준비 자료 SHA256 "+digest)
    staff_id=None
    chief_id=None
    staff_count=chief_count=0
    failure=None
    status="finished"
    try:
        if evidence["first_ready_employee_task"] is not None:
            result=batch.run_batch(store,max_jobs=max_employee_jobs,
                                   owner_note=note,cancel=cancel)
            staff_id=result["batch_id"]
            staff_count=result["actually_invoked_jobs"]
            with store._connect() as con:
                con.execute("BEGIN IMMEDIATE")
                con.execute("""UPDATE aiwack_owner_operating_rounds SET
                    staff_batch_id=?,staff_completed=? WHERE id=? AND state='running'""",
                    (staff_id,staff_count,round_id))
                _event(con,round_id,"staff_stage",
                       detail="실제 직원 모델 요청 "+str(staff_count)+"건; 최종 검수 미실행")
        if cancel is not None and cancel.is_set():
            status="cancelled"
        elif evidence["chief_forwarded_artifacts"]:
            # The existing chief queue picks currently eligible IDs,
            # not raw IDs from a possibly stale owner preview.
            response=handoff.run(store,max_chief_reviews,note,cancel=cancel)
            if response.get("executed") is True:
                chief_id=response["batch_id"]
                chief_count=response["chief_reports_created"]
                status="cancelled" if response["state"]=="cancelled" else status
                with store._connect() as con:
                    con.execute("BEGIN IMMEDIATE")
                    con.execute("""UPDATE aiwack_owner_operating_rounds SET
                        chief_batch_id=?,chief_completed=?
                        WHERE id=? AND state='running'""",
                        (chief_id,chief_count,round_id))
                    _event(con,round_id,"chief_stage",
                           detail="실제 총괄 모델 회수 "+str(chief_count)+"건; 최종 관리자 검수 미실행")
    except Exception as error:
        status="failed"
        failure=type(error).__name__[:70]
        raise
    finally:
        with store._connect() as con:
            con.execute("BEGIN IMMEDIATE")
            if con.execute("""UPDATE aiwack_owner_operating_rounds
                SET state=?,staff_batch_id=COALESCE(?,staff_batch_id),
                    chief_batch_id=COALESCE(?,chief_batch_id),
                    staff_completed=?,chief_completed=?,
                    exit_reason=?,closed_at=CURRENT_TIMESTAMP
                WHERE id=? AND state='running'""",
                (status,staff_id,chief_id,staff_count,chief_count,
                 failure or status,round_id)).rowcount:
                _event(con,round_id,status,detail=failure or status)
    return {"executed":True,"round_id":round_id,"state":status,
            "staff_calls_started":staff_count,"chief_reports_saved":chief_count,
            "staff_batch_id":staff_id,"chief_batch_id":chief_id,
            "owner_individual_approval_still_required":True,
            "owner_final_completion_automatic":False,
            "external_transaction_executed":False}


def history(store,limit=30):
    store.require_permission("company:manage")
    if type(limit) is not int or not 1<=limit<=100:
        raise ValueError("전사 운영 이력 1~100회차")
    with store._connect() as con:
        initialize(con)
        rows=con.execute("""SELECT id,state,max_employee_jobs,max_chief_reviews,
            staff_batch_id,chief_batch_id,staff_completed,chief_completed,
            exit_reason,started_at,closed_at FROM aiwack_owner_operating_rounds
            ORDER BY id DESC LIMIT ?""",(limit,)).fetchall()
    keys=("id","state","max_employee_jobs","max_chief_reviews",
          "staff_batch_id","chief_batch_id","staff_completed","chief_completed",
          "exit_reason","started_at","closed_at")
    return [dict(zip(keys,row)) for row in rows]


def close_after_owner_inspection(store,round_id,note,*,owner_confirmed=False):
    """중단 후 원장 종결; 기존 실제 GGUF 재실행/lease 해제 절대 안 함."""
    store.require_permission("company:manage")
    store.require_permission("agents:manage")
    if type(round_id) is not int or round_id<1 or owner_confirmed is not True:
        raise PermissionError("대상 회차 번호/관리자 직접 확인 필요")
    note=_note(note)
    with store._connect() as con:
        con.execute("BEGIN IMMEDIATE")
        initialize(con)
        if not con.execute("""SELECT 1 FROM aiwack_owner_operating_rounds
            WHERE id=? AND state='running'""",(round_id,)).fetchone():
            raise ValueError("미종료 전사 운영 회차 없음")
        for table in ("aiwack_owner_model_queue","aiwack_head_chief_batch_items",
                      "aiwack_autopilot_model_runs","ai_model_call_history"):
            if con.execute("""SELECT 1 FROM sqlite_master WHERE type='table'
                AND name=?""",(table,)).fetchone():
                column="status" if table=="ai_model_call_history" else "state"
                if con.execute("SELECT 1 FROM "+table+" WHERE "+column+
                               "='running' LIMIT 1").fetchone():
                    raise PermissionError("실제 모델/업무 미종료 기록이 있습니다: "+table)
        if con.execute("""SELECT 1 FROM sqlite_master WHERE type='table'
            AND name='aiwack_chief_review_leases'""").fetchone() and con.execute(
            "SELECT 1 FROM aiwack_chief_review_leases LIMIT 1").fetchone():
            raise PermissionError("총괄 실제 GGUF lease 원본 남음")
        con.execute("""UPDATE aiwack_owner_operating_rounds
            SET state='cancelled',exit_reason='owner_inspected_interruption',
                closed_at=CURRENT_TIMESTAMP WHERE id=? AND state='running'""",
            (round_id,))
        _event(con,round_id,"owner_closed",detail=note)
    return {"round_id":round_id,"state":"cancelled",
            "previous_results_preserved":True,"models_reinvoked":False}
