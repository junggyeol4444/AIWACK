"""실제 부서·직원·업무·모델 실행 이력 기반 업무량 평가와 관리자 후속업무.

관측 업무량은 능력/품질 평가나 자동 인사 변경 근거가 아니다.
"""
from __future__ import annotations
import hashlib
import json
from desktop.stage87_90_management import stopped


def _canonical(value):
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True,
                     separators=(",", ":"))
    return raw, hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _note(value):
    if not isinstance(value, str) or not 5 <= len(value.strip()) <= 200:
        raise ValueError("관리자 사유는 5~200자입니다.")
    return value.strip()


def initialize(con):
    con.execute("""CREATE TABLE IF NOT EXISTS aiwack_department_workload_reviews(
       id INTEGER PRIMARY KEY AUTOINCREMENT,
       department_id INTEGER NOT NULL REFERENCES company_departments(id),
       evidence_json TEXT NOT NULL,
       evidence_sha256 TEXT NOT NULL CHECK(length(evidence_sha256)=64),
       proposal_note TEXT NOT NULL CHECK(length(proposal_note) BETWEEN 5 AND 200),
       created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
       UNIQUE(department_id,evidence_sha256))""")
    con.execute("""CREATE TABLE IF NOT EXISTS aiwack_department_workload_decisions(
       id INTEGER PRIMARY KEY AUTOINCREMENT,
       proposal_id INTEGER NOT NULL UNIQUE REFERENCES aiwack_department_workload_reviews(id),
       decision TEXT NOT NULL CHECK(decision IN ('review_task','rejected')),
       owner_note TEXT NOT NULL CHECK(length(owner_note) BETWEEN 5 AND 200),
       task_id INTEGER UNIQUE REFERENCES company_tasks(id),
       decided_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
       CHECK((decision='review_task' AND task_id IS NOT NULL)
          OR (decision='rejected' AND task_id IS NULL)))""")
    for table in ("aiwack_department_workload_reviews",
                  "aiwack_department_workload_decisions"):
        for op in ("UPDATE", "DELETE"):
            con.execute(f"""CREATE TRIGGER IF NOT EXISTS {table}_immutable_{op.lower()}
              BEFORE {op} ON {table}
              BEGIN SELECT RAISE(ABORT,'부서 업무량 원본 감사 변경 금지'); END""")


def _read(con):
    departments = con.execute("""SELECT id,name FROM company_departments ORDER BY id""").fetchall()
    employees = con.execute("""SELECT department_id,COUNT(*)
        FROM ai_employee_profiles WHERE lifecycle='draft' AND department_id IS NOT NULL
        GROUP BY department_id""").fetchall()
    assigned = con.execute("""SELECT e.department_id,COUNT(*)
        FROM company_task_assignments a
        JOIN company_tasks t ON t.id=a.task_id
        JOIN ai_employee_profiles e ON e.id=a.employee_id
        WHERE t.status IN ('todo','in_progress','blocked')
        GROUP BY e.department_id""").fetchall()
    running = con.execute("""SELECT e.department_id,COUNT(*)
        FROM company_task_runs r
        JOIN ai_employee_profiles e ON e.id=r.employee_id
        WHERE r.status='running' GROUP BY e.department_id""").fetchall()
    failures = con.execute("""SELECT e.department_id,COUNT(*)
        FROM company_task_runs r
        JOIN ai_employee_profiles e ON e.id=r.employee_id
        WHERE r.status IN ('failure','timeout','interrupted')
        GROUP BY e.department_id""").fetchall()
    reviews = con.execute("""SELECT e.department_id,COUNT(*)
        FROM company_task_artifacts a
        JOIN company_task_runs r ON r.id=a.run_id
        JOIN ai_employee_profiles e ON e.id=r.employee_id
        WHERE a.review_status='pending' GROUP BY e.department_id""").fetchall()
    groups = [dict(x) for x in (employees, assigned, running, failures, reviews)]
    result = []
    for dept_id, name in departments:
        count, open_work, active, failed, pending = [
            int(g.get(dept_id, 0)) for g in groups]
        # 명시적인 검토 후보 기준일 뿐, 인력 부족 확정이나 AI 판단이 아님.
        review_candidate = open_work >= max(3, count * 3) or pending >= 3
        result.append({
            "department_id": int(dept_id), "name": str(name),
            "active_employee_profiles": count, "open_assigned_tasks": open_work,
            "running_model_attempts": active, "historical_failed_attempts": failed,
            "pending_artifact_reviews": pending,
            "rule_based_review_candidate": bool(review_candidate),
        })
    unassigned = con.execute("""SELECT COUNT(*) FROM company_tasks t
        LEFT JOIN company_task_assignments a ON a.task_id=t.id
        WHERE t.status IN ('todo','in_progress','blocked') AND a.task_id IS NULL""").fetchone()[0]
    return {"departments": result, "department_count": len(result),
            "active_employee_profiles": sum(x["active_employee_profiles"] for x in result),
            "open_unassigned_tasks": int(unassigned),
            "model_quality_or_productivity_verified": False,
            "automatic_staff_transfer": False, "external_revenue_verified": False}


def snapshot(store):
    store.require_permission("company:manage")
    with store._connect() as con:
        data = _read(con)
    _, sha = _canonical(data)
    return {**data, "snapshot_sha256": sha}


def propose(store, department_id, owner_note):
    store.require_permission("company:manage")
    if type(department_id) is not int or department_id <= 0:
        raise ValueError("부서 번호 오류")
    note = _note(owner_note)
    with store._connect() as con:
        con.execute("BEGIN IMMEDIATE")
        initialize(con)
        if stopped(con):
            raise PermissionError("비상정지 중 업무량 제안 금지")
        data = _read(con)
        item = next((x for x in data["departments"]
                     if x["department_id"] == department_id), None)
        if item is None:
            raise ValueError("존재하지 않는 부서입니다.")
        raw, sha = _canonical(item)
        previous = con.execute("""SELECT id FROM aiwack_department_workload_reviews
             WHERE department_id=? AND evidence_sha256=?""",
             (department_id, sha)).fetchone()
        if previous:
            return {"id": int(previous[0]), "duplicate": True,
                    "staff_changed": False, "model_called": False}
        pid = int(con.execute("""INSERT INTO aiwack_department_workload_reviews
             (department_id,evidence_json,evidence_sha256,proposal_note)
             VALUES(?,?,?,?)""", (department_id, raw, sha, note)).lastrowid)
    return {"id": pid, "duplicate": False, "staff_changed": False,
            "model_called": False, "owner_decision_required": True}


def decide(store, proposal_id, decision, owner_note):
    store.require_permission("company:manage")
    if type(proposal_id) is not int or proposal_id <= 0:
        raise ValueError("업무량 제안 번호 오류")
    if decision not in ("review_task", "rejected"):
        raise ValueError("관리자 검토 업무 생성 또는 반려만 허용합니다.")
    note = _note(owner_note)
    with store._connect() as con:
        con.execute("BEGIN IMMEDIATE")
        initialize(con)
        if stopped(con):
            raise PermissionError("비상정지 중 업무량 판단 금지")
        row = con.execute("""SELECT department_id,evidence_json,evidence_sha256
           FROM aiwack_department_workload_reviews WHERE id=?""",
           (proposal_id,)).fetchone()
        if row is None:
            raise ValueError("업무량 제안을 찾을 수 없습니다.")
        department_id, raw, sha = row
        if hashlib.sha256(raw.encode("utf-8")).hexdigest() != sha:
            raise ValueError("업무량 근거 SHA256 불일치")
        if con.execute("""SELECT 1 FROM aiwack_department_workload_decisions
             WHERE proposal_id=?""", (proposal_id,)).fetchone():
            raise ValueError("이미 결정된 업무량 제안입니다.")
        task_id = None
        if decision == "review_task":
            current = next((x for x in _read(con)["departments"]
                            if x["department_id"] == department_id), None)
            if current is None or _canonical(current)[1] != sha:
                raise ValueError("부서 업무량이 변경됐습니다. 새 제안을 생성하세요.")
            title = f"부서 업무량 관리자 검토: {current['name']}"[:120]
            detail = (f"업무량 제안 #{proposal_id}; 근거 SHA256 {sha}; "
                      f"열린 배정 업무 {current['open_assigned_tasks']}건; "
                      f"직원 {current['active_employee_profiles']}명; "
                      f"검수 대기 {current['pending_artifact_reviews']}건. "
                      f"관리자 판단: {note}. 실제 인력 이동·AI 호출은 별도 승인 필요.")
            task_id = int(con.execute("""INSERT INTO company_tasks(title,description)
                 VALUES(?,?)""", (title, detail[:1000])).lastrowid)
            con.execute("""INSERT INTO company_task_status_events
                 (task_id,old_status,new_status) VALUES(?,NULL,'todo')""",
                 (task_id,))
        did = int(con.execute("""INSERT INTO aiwack_department_workload_decisions
           (proposal_id,decision,owner_note,task_id) VALUES(?,?,?,?)""",
           (proposal_id, decision, note, task_id)).lastrowid)
    return {"decision_id": did, "task_id": task_id, "employee_moved": False,
            "model_called": False, "owner_approval_required_for_execution": True}


def history(store, limit=50):
    store.require_permission("company:manage")
    if type(limit) is not int or not 1 <= limit <= 100:
        raise ValueError("부서 업무량 감사 조회 범위 오류")
    with store._connect() as con:
        initialize(con)
        rows = con.execute("""SELECT p.id,p.department_id,p.evidence_json,
             p.evidence_sha256,p.proposal_note,p.created_at,
             d.decision,d.task_id,d.decided_at
             FROM aiwack_department_workload_reviews p
             LEFT JOIN aiwack_department_workload_decisions d
               ON d.proposal_id=p.id ORDER BY p.id DESC LIMIT ?""",
             (limit,)).fetchall()
    result = []
    for row in rows:
        if hashlib.sha256(row[2].encode("utf-8")).hexdigest() != row[3]:
            raise ValueError("부서 업무량 감사 SHA256 불일치")
        result.append({"id": int(row[0]), "department_id": int(row[1]),
                       "evidence": json.loads(row[2]), "evidence_sha256": row[3],
                       "proposal_note": row[4], "created_at": row[5],
                       "decision": row[6], "task_id": row[7],
                       "decided_at": row[8]})
    return result
