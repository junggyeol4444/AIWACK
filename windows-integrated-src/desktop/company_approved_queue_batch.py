"""승인된 여러 실제 GGUF 업무를 원본 SQLite 대기열에서 연속 실행한다.

개별 업무는 기존 관리자 승인으로 대기열에 등록되어 있어야 한다.
별도 소유자 배치 실행 클릭·자동 운영 동의·실모델 동의가 필요하다.
직원/총괄 실제 모델 엔진만 호출하며 결과물·지출·발송을 승인하지 않는다.
실패, 모델 중지, 프로세스 소유권 불명확 시 자동 재시도하지 않는다.
"""
from __future__ import annotations

import hashlib
import json
import threading

from desktop.stage87_90_management import stopped

MAX_BATCH_TASKS = 30


def _positive(value):
    if type(value) is not int or value < 1:
        raise ValueError("양의 정수 번호가 필요합니다.")
    return value


def _reason(value):
    if not isinstance(value, str) or not 5 <= len(value.strip()) <= 200:
        raise ValueError("관리자 배치 실행 사유는 5~200자여야 합니다.")
    return value.strip()


def initialize(con):
    con.execute("""CREATE TABLE IF NOT EXISTS aiwack_approved_model_batches(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        owner_note TEXT NOT NULL CHECK(length(owner_note) BETWEEN 5 AND 200),
        max_jobs INTEGER NOT NULL CHECK(max_jobs BETWEEN 1 AND 30),
        state TEXT NOT NULL DEFAULT 'running'
            CHECK(state IN ('running','finished','stopped','failed')),
        executed_count INTEGER NOT NULL DEFAULT 0,
        last_queue_id INTEGER,
        exit_reason TEXT NOT NULL DEFAULT '',
        started_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        ended_at TEXT)""")
    con.execute("""CREATE TABLE IF NOT EXISTS aiwack_approved_model_batch_events(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        batch_id INTEGER NOT NULL REFERENCES aiwack_approved_model_batches(id),
        sequence INTEGER NOT NULL,
        kind TEXT NOT NULL CHECK(kind IN
            ('opened','executed','finished','stopped','failed')),
        queue_id INTEGER,
        task_id INTEGER,
        detail TEXT NOT NULL,
        previous_hash TEXT NOT NULL,
        event_hash TEXT NOT NULL,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(batch_id,sequence))""")
    for op in ("UPDATE", "DELETE"):
        con.execute("""CREATE TRIGGER IF NOT EXISTS aiwack_approved_batch_events_no_%s
            BEFORE %s ON aiwack_approved_model_batch_events
            BEGIN SELECT RAISE(ABORT, '승인 GGUF 연속 실행 감사 수정/삭제 금지'); END"""
            % (op.lower(), op))


def _record(con, batch_id, kind, *, queue_id=None, task_id=None, detail=""):
    previous = con.execute("""SELECT sequence,event_hash
        FROM aiwack_approved_model_batch_events WHERE batch_id=?
        ORDER BY sequence DESC LIMIT 1""", (batch_id,)).fetchone()
    sequence = int(previous[0]) + 1 if previous else 1
    previous_hash = previous[1] if previous else "0" * 64
    canonical = json.dumps([batch_id, sequence, kind, queue_id, task_id,
                            detail, previous_hash], ensure_ascii=False,
                           separators=(",", ":"))
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    con.execute("""INSERT INTO aiwack_approved_model_batch_events
        (batch_id,sequence,kind,queue_id,task_id,detail,previous_hash,event_hash)
        VALUES(?,?,?,?,?,?,?,?)""",
        (batch_id, sequence, kind, queue_id, task_id, detail, previous_hash, digest))


def _finish(store, batch_id, state, reason, executed_count, *, queue_id=None,
            task_id=None):
    with store._connect() as con:
        con.execute("BEGIN IMMEDIATE")
        if con.execute("""UPDATE aiwack_approved_model_batches
            SET state=?, exit_reason=?, executed_count=?,
                last_queue_id=COALESCE(?,last_queue_id),
                ended_at=CURRENT_TIMESTAMP
            WHERE id=? AND state='running'""",
            (state, reason, executed_count, queue_id, batch_id)).rowcount != 1:
            raise RuntimeError("연속 실행 상태 소유권이 변경됐습니다. 자동 재호출하지 않습니다.")
        _record(con, batch_id, state, queue_id=queue_id, task_id=task_id,
                detail=reason)


def run_batch(store, *, max_jobs, owner_note, cancel=None,
              session_token=None):
    """관리자 승인 대기열의 준비된 실제 업무만 최대 30개 순차 실행.

    단 하나라도 오류가 발생하면 즉시 정지하며 이전 직원 결과의 관리자
    검수/총괄 결과 최종 확정은 수행하지 않는다. 재시작 시 running 배치를
    자동 재사용하지 않으므로 과거 실행/모델 프로세스는 관리자 확인 대상이다.
    """
    store.require_permission("company:manage")
    store.require_permission("agents:manage")
    if type(max_jobs) is not int or not 1 <= max_jobs <= MAX_BATCH_TASKS:
        raise ValueError("한 번의 연속 실행은 1~30개 업무만 허용합니다.")
    note = _reason(owner_note)
    signal = cancel if cancel is not None else threading.Event()
    if signal.is_set():
        raise InterruptedError("관리자가 실행 전에 취소했습니다.")
    from desktop import company_autopilot, company_owner_model_queue
    if not company_autopilot.approved_models_enabled(store):
        raise PermissionError("자율 운영·실제 GGUF 실행 이중 동의가 필요합니다.")
    with store._connect() as con:
        con.execute("BEGIN IMMEDIATE")
        initialize(con)
        company_owner_model_queue.initialize(con)
        if stopped(con):
            raise PermissionError("비상정지 상태에서는 실제 모델을 실행하지 않습니다.")
        old = con.execute("""SELECT id FROM aiwack_approved_model_batches
            WHERE state='running' ORDER BY id LIMIT 1""").fetchone()
        if old:
            raise PermissionError(
                "이전 연속 실행 #%s 미종료 기록 존재. 모델 프로세스 및 잠금을 "
                "관리자가 확인하기 전 새 연속 실행 금지." % old[0])
        batch_id = int(con.execute("""INSERT INTO aiwack_approved_model_batches
            (owner_note,max_jobs) VALUES(?,?)""", (note, max_jobs)).lastrowid)
        _record(con, batch_id, "opened", detail=note)
    count = 0
    exit_reason = "limit_reached"
    try:
        while count < max_jobs:
            if signal.is_set():
                exit_reason = "owner_cancelled"
                break
            if not company_autopilot.approved_models_enabled(store):
                exit_reason = "owner_model_policy_revoked"
                break
            # run_next rechecks emergency stop, approvals, FIFO readiness,
            # model lease and prior-attempt history inside its own transaction.
            result = company_owner_model_queue.run_next(
                store, session_token=session_token, cancel=signal)
            if not result.get("executed", True):
                exit_reason = str(result.get("reason", "no_ready_pending"))[:120]
                break
            queue_id = _positive(result["queue_id"])
            task_id = _positive(result["task_id"])
            with store._connect() as con:
                con.execute("BEGIN IMMEDIATE")
                if con.execute("""UPDATE aiwack_approved_model_batches
                    SET executed_count=executed_count+1,last_queue_id=?
                    WHERE id=? AND state='running'""",
                    (queue_id, batch_id)).rowcount != 1:
                    raise RuntimeError("연속 실행 감사 소유권 변경")
                _record(con, batch_id, "executed", queue_id=queue_id,
                        task_id=task_id, detail="실제 직원/총괄 GGUF 호출 기록; 관리자 검수 대기")
            count += 1
        _finish(store, batch_id,
                "stopped" if exit_reason in
                ("owner_cancelled", "owner_model_policy_revoked") else "finished",
                exit_reason, count)
    except Exception as exc:
        # run_next already marks any claimed job failed. No retries or
        # queue deletion here. Do not log model output or private prompts.
        _finish(store, batch_id, "failed", type(exc).__name__, count)
        raise
    return {"batch_id": batch_id, "state": (
        "stopped" if exit_reason in
        ("owner_cancelled", "owner_model_policy_revoked") else "finished"),
        "actually_invoked_jobs": count, "max_jobs": max_jobs,
        "exit_reason": exit_reason, "individual_owner_review_required": True,
        "auto_approved": False, "automatic_retry": False,
        "external_transactions": False}


def history(store, limit=30):
    """실제 SQLite 원장과 변경 불가능한 SHA256 연결 이벤트를 조회한다."""
    store.require_permission("company:manage")
    if type(limit) is not int or not 1 <= limit <= 100:
        raise ValueError("연속 실행 이력 조회는 1~100건입니다.")
    with store._connect() as con:
        initialize(con)
        batches = con.execute("""SELECT id,state,max_jobs,executed_count,
            last_queue_id,exit_reason,started_at,ended_at
            FROM aiwack_approved_model_batches ORDER BY id DESC LIMIT ?""",
            (limit,)).fetchall()
        output = []
        for row in batches:
            batch_id = int(row[0])
            event_rows = con.execute("""SELECT sequence,kind,queue_id,task_id,
                detail,previous_hash,event_hash
                FROM aiwack_approved_model_batch_events
                WHERE batch_id=? ORDER BY sequence""", (batch_id,)).fetchall()
            previous_hash = "0" * 64
            valid = True
            for i, event in enumerate(event_rows, 1):
                seq, kind, queue_id, task_id, detail, prev, digest = event
                data = json.dumps([batch_id, seq, kind, queue_id, task_id,
                                   detail, prev], ensure_ascii=False,
                                  separators=(",", ":"))
                if seq != i or prev != previous_hash or hashlib.sha256(
                        data.encode("utf-8")).hexdigest() != digest:
                    valid = False
                previous_hash = digest
            output.append({"id": batch_id, "state": row[1],
                           "max_jobs": row[2], "actually_invoked_jobs": row[3],
                           "last_queue_id": row[4], "exit_reason": row[5],
                           "started_at": row[6], "ended_at": row[7],
                           "event_count": len(event_rows),
                           "audit_chain_valid": valid and bool(event_rows),
                           "requires_manual_inspection": row[1] == "running",
                           "owner_review_required": True})
    return output



def close_after_owner_inspection(store, batch_id, owner_note, *, owner_confirmed=False):
    """중단 배치의 미완료 모델·직원 실행/잠금 부재를 확인하고 원장만 닫는다."""
    store.require_permission("company:manage")
    store.require_permission("agents:manage")
    _positive(batch_id)
    note = _reason(owner_note)
    if owner_confirmed is not True:
        raise PermissionError("소유자 직접 확인이 필요합니다.")
    from desktop import company_autopilot
    company_autopilot.initialize(store)
    with store._connect() as con:
        con.execute("BEGIN IMMEDIATE")
        initialize(con)
        prior = con.execute("""SELECT state,executed_count FROM
            aiwack_approved_model_batches WHERE id=?""", (batch_id,)).fetchone()
        if not prior or prior[0] != "running":
            raise ValueError("미종료 배치만 관리자 확인 종료할 수 있습니다.")
        if con.execute("SELECT 1 FROM aiwack_autopilot_model_leases LIMIT 1").fetchone():
            raise PermissionError("실제 모델 잠금이 남았습니다. 먼저 종료를 확인하십시오.")
        if con.execute("""SELECT 1 FROM aiwack_autopilot_model_runs
            WHERE state='running' LIMIT 1""").fetchone():
            raise PermissionError("실행 중인 모델 감사 기록이 남아 있습니다.")
        if con.execute("""SELECT 1 FROM company_task_runs
            WHERE status='running' LIMIT 1""").fetchone():
            raise PermissionError("실행 중인 직원 업무가 남아 있습니다.")
        if con.execute("""UPDATE aiwack_approved_model_batches SET state='stopped',
            exit_reason='owner_inspected_interruption',ended_at=CURRENT_TIMESTAMP
            WHERE id=? AND state='running'""", (batch_id,)).rowcount != 1:
            raise RuntimeError("중단 배치 상태가 변경됐습니다.")
        _record(con, batch_id, "stopped", detail="소유자 중단 확인: " + note)
    return {"batch_id": batch_id, "state": "stopped",
            "previous_actual_model_jobs": int(prior[1]),
            "model_invoked_by_cleanup": False, "automatic_retry": False}
