"""Owner-inspected interrupted autopilot runs -> durable, non-executing recovery work.

Only an existing explicit inspection audit can be escalated. Never infer a
dead process from age; never release leases, retry GGUF, or replay payments.
"""
from __future__ import annotations

import hashlib
import json

from desktop.stage87_90_management import stopped


def _note(value):
    if not isinstance(value, str) or not 5 <= len(value.strip()) <= 200:
        raise ValueError("관리자 확인 사유는 5~200자여야 합니다.")
    return value.strip()


def _positive(value):
    if type(value) is not int or value <= 0:
        raise ValueError("원본 감사 번호는 양의 정수여야 합니다.")
    return value


def _seal(value):
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return raw, hashlib.sha256(raw.encode("utf-8")).hexdigest()


def initialize(con):
    con.execute("""CREATE TABLE IF NOT EXISTS aiwack_recovery_work_orders (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        recovery_audit_id INTEGER NOT NULL UNIQUE
            REFERENCES aiwack_autopilot_recovery_audit(id),
        run_kind TEXT NOT NULL CHECK(run_kind IN ('tick','model')),
        run_id INTEGER NOT NULL CHECK(run_id>0),
        source_task_id INTEGER REFERENCES company_tasks(id),
        evidence_json TEXT NOT NULL,
        evidence_sha256 TEXT NOT NULL CHECK(length(evidence_sha256)=64),
        owner_note TEXT NOT NULL CHECK(length(owner_note) BETWEEN 5 AND 200),
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    )""")
    con.execute("""CREATE TABLE IF NOT EXISTS aiwack_recovery_work_decisions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        work_order_id INTEGER NOT NULL UNIQUE
            REFERENCES aiwack_recovery_work_orders(id),
        decision TEXT NOT NULL CHECK(decision IN ('followup_task','rejected')),
        owner_note TEXT NOT NULL CHECK(length(owner_note) BETWEEN 5 AND 200),
        followup_task_id INTEGER UNIQUE REFERENCES company_tasks(id),
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        CHECK((decision='followup_task' AND followup_task_id IS NOT NULL)
           OR (decision='rejected' AND followup_task_id IS NULL))
    )""")
    for table in ("aiwack_recovery_work_orders", "aiwack_recovery_work_decisions"):
        for action in ("UPDATE", "DELETE"):
            con.execute(f"""CREATE TRIGGER IF NOT EXISTS {table}_immutable_{action.lower()}
                BEFORE {action} ON {table} BEGIN
                SELECT RAISE(ABORT,'중단 복구 원본 감사 수정/삭제 금지'); END""")


def _source(con, audit_id):
    row = con.execute("""SELECT a.id,a.run_kind,a.run_id,a.elapsed_seconds,
            a.operator_note,a.created_at,
            CASE WHEN a.run_kind='model' THEN m.task_id ELSE NULL END,
            CASE WHEN a.run_kind='model' THEN m.state ELSE t.state END
        FROM aiwack_autopilot_recovery_audit a
        LEFT JOIN aiwack_autopilot_model_runs m
            ON a.run_kind='model' AND m.id=a.run_id
        LEFT JOIN aiwack_autopilot_runs t
            ON a.run_kind='tick' AND t.id=a.run_id
        WHERE a.id=? AND a.owner_confirmed=1""", (audit_id,)).fetchone()
    if not row:
        raise ValueError("소유자가 직접 확인한 기존 복구 감사가 없습니다.")
    if row[7] != "failed":
        raise ValueError("중단 실행의 기존 감사 상태가 변경되어 후속 등록 불가")
    return {
        "recovery_audit_id": int(row[0]), "run_kind": str(row[1]),
        "run_id": int(row[2]), "elapsed_seconds": int(row[3]),
        "operator_note": str(row[4]), "inspection_created_at": str(row[5]),
        "source_task_id": int(row[6]) if row[6] is not None else None,
        "recorded_run_state": str(row[7]),
        "process_exit_independently_verified": False,
        "external_side_effects_replayed": False,
    }


def eligible(store, limit=50):
    store.require_permission("company:manage")
    if type(limit) is not int or not 1 <= limit <= 100:
        raise ValueError("복구 감사 조회는 1~100건입니다.")
    from desktop import company_autopilot, company_continuity
    company_autopilot.initialize(store)
    with store._connect() as con:
        company_continuity.initialize(con)
        initialize(con)
        ids = [int(r[0]) for r in con.execute("""SELECT a.id
            FROM aiwack_autopilot_recovery_audit a
            LEFT JOIN aiwack_recovery_work_orders w ON w.recovery_audit_id=a.id
            WHERE w.id IS NULL ORDER BY a.id DESC LIMIT ?""", (limit,)).fetchall()]
        result = []
        for audit_id in ids:
            try:
                result.append(_source(con, audit_id))
            except ValueError:
                continue
    return result


def capture(store, audit_id, owner_note):
    store.require_permission("company:manage")
    _positive(audit_id)
    note = _note(owner_note)
    from desktop import company_autopilot, company_continuity
    company_autopilot.initialize(store)
    with store._connect() as con:
        con.execute("BEGIN IMMEDIATE")
        company_continuity.initialize(con)
        initialize(con)
        if stopped(con):
            raise PermissionError("비상정지 중 복구 후속 업무 등록 금지")
        evidence = _source(con, audit_id)
        existing = con.execute("""SELECT id FROM aiwack_recovery_work_orders
            WHERE recovery_audit_id=?""", (audit_id,)).fetchone()
        if existing:
            return {"id": int(existing[0]), "duplicate": True, "model_retried": False}
        raw, sha = _seal(evidence)
        work_id = int(con.execute("""INSERT INTO aiwack_recovery_work_orders
            (recovery_audit_id,run_kind,run_id,source_task_id,
             evidence_json,evidence_sha256,owner_note)
            VALUES(?,?,?,?,?,?,?)""", (
                audit_id, evidence["run_kind"], evidence["run_id"],
                evidence["source_task_id"], raw, sha, note)).lastrowid)
    return {"id": work_id, "duplicate": False, "evidence_sha256": sha,
            "owner_decision_required": True, "model_retried": False}


def decide(store, work_order_id, decision, owner_note):
    store.require_permission("company:manage")
    _positive(work_order_id)
    if decision not in ("followup_task", "rejected"):
        raise ValueError("후속 검토 업무 생성 또는 반려만 허용됩니다.")
    note = _note(owner_note)
    from desktop import company_autopilot, company_continuity
    company_autopilot.initialize(store)
    with store._connect() as con:
        con.execute("BEGIN IMMEDIATE")
        company_continuity.initialize(con)
        initialize(con)
        if stopped(con):
            raise PermissionError("비상정지 중 복구 후속 판단 금지")
        row = con.execute("""SELECT recovery_audit_id,evidence_json,evidence_sha256
            FROM aiwack_recovery_work_orders WHERE id=?""",
            (work_order_id,)).fetchone()
        if row is None:
            raise ValueError("복구 후속 감사 번호가 없습니다.")
        audit_id, raw, sha = row
        if hashlib.sha256(raw.encode("utf-8")).hexdigest() != sha:
            raise ValueError("복구 원본 SHA256 불일치")
        if con.execute("""SELECT 1 FROM aiwack_recovery_work_decisions
            WHERE work_order_id=?""", (work_order_id,)).fetchone():
            raise ValueError("이미 결정한 복구 후속 업무입니다.")
        if _seal(_source(con, int(audit_id)))[1] != sha:
            raise ValueError("기존 중단 감사 원본이 변경됐습니다.")
        evidence = json.loads(raw)
        task_id = None
        if decision == "followup_task":
            title = f"중단 후 재개 전 확인: {evidence['run_kind']} #{evidence['run_id']}"[:120]
            description = (
                f"복구 원본 감사 #{audit_id}, SHA256 {sha}. "
                f"기존 업무 번호 {evidence['source_task_id']}; 관리자 사유: {note}. "
                "외부 도구/금전/고객 전송 중복 여부와 기존 프로세스 종료를 별도 확인하고 "
                "정식 업무 재개 승인을 받아야 합니다. 자동 GGUF 재호출/상태 초기화 없음."
            )[:1500]
            task_id = int(con.execute("""INSERT INTO company_tasks(title,description)
                VALUES(?,?)""", (title, description)).lastrowid)
            con.execute("""INSERT INTO company_task_status_events
                (task_id,old_status,new_status) VALUES(?,NULL,'todo')""", (task_id,))
        decision_id = int(con.execute("""INSERT INTO aiwack_recovery_work_decisions
            (work_order_id,decision,owner_note,followup_task_id)
            VALUES(?,?,?,?)""", (work_order_id, decision, note, task_id)).lastrowid)
    return {"decision_id": decision_id, "followup_task_id": task_id,
            "automatic_resume": False, "model_retried": False,
            "external_action_executed": False}


def history(store, limit=50):
    store.require_permission("company:manage")
    if type(limit) is not int or not 1 <= limit <= 100:
        raise ValueError("복구 후속 감사 조회는 1~100건입니다.")
    from desktop import company_autopilot, company_continuity
    company_autopilot.initialize(store)
    with store._connect() as con:
        company_continuity.initialize(con)
        initialize(con)
        rows = con.execute("""SELECT w.id,w.recovery_audit_id,w.evidence_json,
            w.evidence_sha256,w.owner_note,w.created_at,
            d.decision,d.followup_task_id,d.owner_note,d.created_at
            FROM aiwack_recovery_work_orders w
            LEFT JOIN aiwack_recovery_work_decisions d ON d.work_order_id=w.id
            ORDER BY w.id DESC LIMIT ?""", (limit,)).fetchall()
    result = []
    for row in rows:
        if hashlib.sha256(row[2].encode("utf-8")).hexdigest() != row[3]:
            raise ValueError("복구 후속 원본 SHA256 불일치")
        result.append({
            "id": int(row[0]), "recovery_audit_id": int(row[1]),
            "evidence": json.loads(row[2]), "evidence_sha256": row[3],
            "proposal_note": row[4], "created_at": row[5],
            "decision": row[6], "followup_task_id": row[7],
            "decision_note": row[8], "decided_at": row[9],
            "automatic_resume": False,
        })
    return result
