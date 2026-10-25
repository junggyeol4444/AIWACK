"""Audited employee execution evidence -> owner appraisal and improvement tasks.

These are measured SQLite events, not LLM-estimated quality or sales.
No model switch, staff transfer, or automatic performance ranking.
"""
from __future__ import annotations

import hashlib
import json

from desktop.stage87_90_management import stopped


def _positive(value):
    if type(value) is not int or value <= 0:
        raise ValueError("직원/검토 번호는 양의 정수여야 합니다.")
    return value


def _note(value):
    if not isinstance(value, str) or not 5 <= len(value.strip()) <= 200:
        raise ValueError("관리자 평가 사유는 5~200자여야 합니다.")
    return value.strip()


def _seal(value):
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return raw, hashlib.sha256(raw.encode("utf-8")).hexdigest()


def initialize(con):
    con.execute("""CREATE TABLE IF NOT EXISTS aiwack_employee_evidence_reviews (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        employee_id INTEGER NOT NULL REFERENCES ai_employee_profiles(id),
        evidence_json TEXT NOT NULL,
        evidence_sha256 TEXT NOT NULL CHECK(length(evidence_sha256)=64),
        owner_note TEXT NOT NULL CHECK(length(owner_note) BETWEEN 5 AND 200),
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(employee_id,evidence_sha256)
    )""")
    con.execute("""CREATE TABLE IF NOT EXISTS aiwack_employee_evidence_decisions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        review_id INTEGER NOT NULL UNIQUE
            REFERENCES aiwack_employee_evidence_reviews(id),
        decision TEXT NOT NULL CHECK(decision IN
            ('improvement_task','observed','rejected')),
        owner_note TEXT NOT NULL CHECK(length(owner_note) BETWEEN 5 AND 200),
        task_id INTEGER UNIQUE REFERENCES company_tasks(id),
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        CHECK((decision='improvement_task' AND task_id IS NOT NULL)
           OR (decision!='improvement_task' AND task_id IS NULL))
    )""")
    for table in ("aiwack_employee_evidence_reviews", "aiwack_employee_evidence_decisions"):
        for action in ("UPDATE", "DELETE"):
            con.execute(f"""CREATE TRIGGER IF NOT EXISTS {table}_immutable_{action.lower()}
                BEFORE {action} ON {table} BEGIN
                SELECT RAISE(ABORT,'직원 실적 원본 감사 수정/삭제 금지'); END""")


def _employee(con, employee_id):
    row = con.execute("""SELECT e.id,e.display_name,e.department_id,
        COALESCE(d.name,'미배정'),e.lifecycle
        FROM ai_employee_profiles e
        LEFT JOIN company_departments d ON d.id=e.department_id
        WHERE e.id=?""", (employee_id,)).fetchone()
    if row is None:
        raise ValueError("기존 직원 AI가 없습니다.")
    runs = con.execute("""SELECT COUNT(*),
        COALESCE(SUM(CASE WHEN status='success' THEN 1 ELSE 0 END),0),
        COALESCE(SUM(CASE WHEN status IN ('failure','timeout','interrupted')
            THEN 1 ELSE 0 END),0),
        COALESCE(SUM(CASE WHEN status='cancelled' THEN 1 ELSE 0 END),0),
        COALESCE(SUM(CASE WHEN status='running' THEN 1 ELSE 0 END),0)
        FROM company_task_runs WHERE employee_id=?""", (employee_id,)).fetchone()
    approved = con.execute("""SELECT COUNT(*) FROM company_task_artifacts a
        JOIN company_task_runs r ON r.id=a.run_id
        WHERE r.employee_id=? AND a.review_status='approved'""",
        (employee_id,)).fetchone()[0]
    model = con.execute("""SELECT COUNT(*),
        COALESCE(SUM(CASE WHEN status='success' THEN 1 ELSE 0 END),0)
        FROM ai_model_call_history WHERE employee_id=?""",
        (employee_id,)).fetchone()
    return {
        "employee_id": int(row[0]), "employee_name": str(row[1]),
        "department_id": row[2], "department_name": str(row[3]),
        "lifecycle": str(row[4]), "actual_attempts": int(runs[0]),
        "successful_runs": int(runs[1]), "failed_runs": int(runs[2]),
        "cancelled_runs": int(runs[3]), "running_runs": int(runs[4]),
        "owner_approved_artifacts": int(approved),
        "audited_model_calls": int(model[0]),
        "successful_model_calls": int(model[1]),
        "independent_model_binary_verified": False,
        "quality_or_revenue_inferred": False,
    }


def snapshot(store, employee_id):
    store.require_permission("company:manage")
    _positive(employee_id)
    with store._connect() as con:
        evidence = _employee(con, employee_id)
    return {**evidence, "evidence_sha256": _seal(evidence)[1]}


def capture(store, employee_id, owner_note):
    store.require_permission("company:manage")
    store.require_permission("agents:manage")
    _positive(employee_id)
    note = _note(owner_note)
    with store._connect() as con:
        con.execute("BEGIN IMMEDIATE")
        initialize(con)
        if stopped(con):
            raise PermissionError("비상정지 중 직원 평가 등록 금지")
        evidence = _employee(con, employee_id)
        if evidence["actual_attempts"] == 0 and evidence["audited_model_calls"] == 0:
            raise ValueError("실제 실행/모델 호출 감사가 없는 직원은 실적 평가 불가")
        raw, sha = _seal(evidence)
        existing = con.execute("""SELECT id FROM aiwack_employee_evidence_reviews
            WHERE employee_id=? AND evidence_sha256=?""",
            (employee_id, sha)).fetchone()
        if existing:
            return {"id": int(existing[0]), "duplicate": True, "staff_changed": False}
        review_id = int(con.execute("""INSERT INTO aiwack_employee_evidence_reviews
            (employee_id,evidence_json,evidence_sha256,owner_note)
            VALUES(?,?,?,?)""", (employee_id, raw, sha, note)).lastrowid)
    return {"id": review_id, "duplicate": False,
            "evidence_sha256": sha, "owner_decision_required": True}


def decide(store, review_id, decision, owner_note):
    store.require_permission("company:manage")
    store.require_permission("agents:manage")
    _positive(review_id)
    if decision not in ("improvement_task", "observed", "rejected"):
        raise ValueError("직원 개선 업무/관찰 기록/반려만 허용합니다.")
    note = _note(owner_note)
    with store._connect() as con:
        con.execute("BEGIN IMMEDIATE")
        initialize(con)
        if stopped(con):
            raise PermissionError("비상정지 중 직원 평가 판단 금지")
        row = con.execute("""SELECT employee_id,evidence_json,evidence_sha256
            FROM aiwack_employee_evidence_reviews WHERE id=?""",
            (review_id,)).fetchone()
        if row is None:
            raise ValueError("기존 직원 실적 감사가 없습니다.")
        employee_id, raw, sha = row
        if hashlib.sha256(raw.encode("utf-8")).hexdigest() != sha:
            raise ValueError("직원 실적 근거 SHA256 불일치")
        if con.execute("""SELECT 1 FROM aiwack_employee_evidence_decisions
            WHERE review_id=?""", (review_id,)).fetchone():
            raise ValueError("이미 평가 판단을 확정했습니다.")
        if decision == "improvement_task" and _seal(_employee(con, int(employee_id)))[1] != sha:
            raise ValueError("실제 직원 실행 기록이 변경됐습니다. 새 평가를 등록하세요.")
        task_id = None
        if decision == "improvement_task":
            source = json.loads(raw)
            title = f"직원 실행 성과 개선 검토: {source['employee_name']}"[:120]
            detail = (
                f"직원 #{employee_id}, 평가 #{review_id}, 근거 SHA256 {sha}. "
                f"실제 실행 {source['actual_attempts']}건, 성공 {source['successful_runs']}건, "
                f"실패 {source['failed_runs']}건, 소유자 승인 결과물 "
                f"{source['owner_approved_artifacts']}건. 관리자 판단: {note}. "
                "실제 품질/수익 성과와 별개이며 인사 이동/모델 교체/외부 실행은 별도 승인 필요."
            )[:1500]
            task_id = int(con.execute("""INSERT INTO company_tasks(title,description)
                VALUES(?,?)""", (title, detail)).lastrowid)
            con.execute("""INSERT INTO company_task_status_events
                (task_id,old_status,new_status) VALUES(?,NULL,'todo')""", (task_id,))
        decision_id = int(con.execute("""INSERT INTO aiwack_employee_evidence_decisions
            (review_id,decision,owner_note,task_id)
            VALUES(?,?,?,?)""", (review_id, decision, note, task_id)).lastrowid)
    return {"decision_id": decision_id, "task_id": task_id,
            "employee_reassigned": False, "model_switched": False,
            "model_called": False, "external_action_executed": False}


def history(store, limit=50):
    store.require_permission("company:manage")
    if type(limit) is not int or not 1 <= limit <= 100:
        raise ValueError("직원 평가 감사 조회는 1~100건입니다.")
    with store._connect() as con:
        initialize(con)
        rows = con.execute("""SELECT r.id,r.employee_id,r.evidence_json,
            r.evidence_sha256,r.owner_note,r.created_at,
            d.decision,d.task_id,d.owner_note,d.created_at
            FROM aiwack_employee_evidence_reviews r
            LEFT JOIN aiwack_employee_evidence_decisions d ON d.review_id=r.id
            ORDER BY r.id DESC LIMIT ?""", (limit,)).fetchall()
    result = []
    for row in rows:
        if hashlib.sha256(row[2].encode("utf-8")).hexdigest() != row[3]:
            raise ValueError("직원 평가 감사 SHA256 불일치")
        result.append({
            "id": int(row[0]), "employee_id": int(row[1]),
            "evidence": json.loads(row[2]), "evidence_sha256": row[3],
            "proposal_note": row[4], "created_at": row[5],
            "decision": row[6], "task_id": row[7],
            "decision_note": row[8], "decided_at": row[9],
            "staff_changed": False, "model_called": False,
        })
    return result
