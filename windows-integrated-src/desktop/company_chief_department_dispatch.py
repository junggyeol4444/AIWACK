"""총괄 실제 GGUF의 부서별 내부 업무 제안을 관리자 결정 후 실제 업무로 배분.

실제 모델 생성 제안만 대상. 기존 직원/모델/부서/업무 원본을 SQLite 한
트랜잭션에서 재확인하고 새로운 todo 및 부서별 직원 배정을 저장한다.
모델 실행, 외부 결제/게시, 고객 접촉, 승인 자동화는 수행하지 않는다.
"""
from __future__ import annotations

from desktop.company_chief_department_discovery import initialize
from desktop.stage87_90_management import stopped


def decide(store, proposal_id: int, decision: str, owner_note: str) -> dict:
    store.require_permission("company:manage")
    store.require_permission("agents:manage")
    if type(proposal_id) is not int or proposal_id<=0:
        raise ValueError("총괄 실제 GGUF 제안 번호 오류")
    if decision not in ("approved","rejected"):
        raise ValueError("제안 결정은 개별 승인/반려만 가능합니다.")
    if type(owner_note) is not str or not 5<=len(owner_note.strip())<=200:
        raise ValueError("관리자 결정 사유를 5~200자로 입력하세요.")
    note=owner_note.strip()
    with store._connect() as con:
        con.execute("BEGIN IMMEDIATE")
        initialize(con)
        if stopped(con):
            raise PermissionError("비상 정지 중 신규 업무 승인 금지")
        source=con.execute("""SELECT p.department_id,p.evidence_task_id,
            p.title,p.description,p.risk,p.discovery_id,
            c.evidence_json,c.chief_employee_id,o.model_call_id
            FROM aiwack_chief_department_proposals p
            JOIN aiwack_chief_department_discoveries c
                ON c.id=p.discovery_id
            JOIN aiwack_chief_department_discovery_outcomes o
                ON o.discovery_id=c.id AND o.status='success'
            WHERE p.id=?""",(proposal_id,)).fetchone()
        if source is None:
            raise ValueError("실제 총괄 모델에 의해 생성된 업무 제안이 아닙니다.")
        if con.execute("""SELECT 1 FROM aiwack_chief_department_proposal_decisions
            WHERE proposal_id=?""",(proposal_id,)).fetchone():
            raise ValueError("이미 승인/반려가 기록된 제안입니다.")
        dept_id, evidence_task, title, description, risk, discovery_id, \
            evidence_json, chief_employee, call_id = source
        import hashlib
        from desktop.company_chief_department_discovery import _digest
        digest=con.execute("""SELECT evidence_sha256 FROM
            aiwack_chief_department_discoveries WHERE id=?""",(discovery_id,)).fetchone()
        if not digest or _digest(evidence_json)!=digest[0]:
            raise PermissionError("실제 총괄 입력 증빙 무결성 오류")
        model=con.execute("""SELECT employee_id,status FROM ai_model_call_history
            WHERE id=?""",(call_id,)).fetchone()
        if not model or model[1]!="success" or int(model[0])!=int(chief_employee):
            raise PermissionError("총괄 GGUF 실제 호출 원본 감사 불일치")
        task_id=None
        employee_id=None
        if decision=="approved":
            if not con.execute("SELECT 1 FROM company_departments WHERE id=?",
                               (dept_id,)).fetchone():
                raise PermissionError("모델 제안 부서가 더 이상 존재하지 않습니다.")
            if evidence_task is not None:
                known=con.execute("SELECT status FROM company_tasks WHERE id=?",
                                  (evidence_task,)).fetchone()
                if known is None:
                    raise PermissionError("총괄 AI가 참고한 원본 업무가 삭제됐습니다.")
                import json
                previous=json.loads(evidence_json)
                expected=next((t["status"] for t in previous["tasks"]
                               if t["id"]==evidence_task),None)
                if expected!=known[0]:
                    raise PermissionError("업무 상태가 변경되어 원본 총괄 제안을 재검토해야 합니다.")
            # Select the least-loaded *actual model-bound* staff of this department.
            # The CEO/head cannot silently be assigned as an operational worker.
            worker=con.execute("""SELECT e.id,e.display_name,COUNT(a.task_id) AS open_jobs
                FROM ai_employee_profiles e
                JOIN ai_reporting_lines l ON l.employee_id=e.id AND l.tier='staff'
                JOIN ai_employee_model_assignments m ON m.employee_id=e.id
                LEFT JOIN company_task_assignments a ON a.employee_id=e.id
                LEFT JOIN company_tasks t ON t.id=a.task_id AND
                    t.status NOT IN ('done','cancelled')
                WHERE e.department_id=? AND e.lifecycle='draft'
                GROUP BY e.id,e.display_name
                ORDER BY SUM(CASE WHEN t.id IS NOT NULL THEN 1 ELSE 0 END),e.id
                LIMIT 1""",(dept_id,)).fetchone()
            if worker is None:
                raise PermissionError("실제 GGUF 모델이 배정된 해당 부서 직원이 없습니다.")
            employee_id=int(worker[0])
            # Keep source proposal unmodified and preserve traceable owner approval.
            detail=(description[:730] + "\n총괄 실제 GGUF 제안 #"+
                    str(proposal_id)+" / 근거 업무 #"+
                    (str(evidence_task) if evidence_task is not None else "없음")+
                    "\n미검증 위험: "+risk[:180])[:1000]
            task_id=int(con.execute("""INSERT INTO company_tasks(title,description)
                VALUES(?,?)""",(title,detail)).lastrowid)
            con.execute("""INSERT INTO company_task_status_events
                (task_id,old_status,new_status) VALUES(?,NULL,'todo')""",
                (task_id,))
            con.execute("""INSERT INTO company_task_routing(task_id,department_id)
                VALUES(?,?)""",(task_id,dept_id))
            con.execute("""INSERT INTO company_task_assignments
                (task_id,employee_id,reason) VALUES(?,?,?)""",
                (task_id,employee_id,
                 "총괄 실제 GGUF 제안 후 소유자 개별 승인; 부서와 모델 연결 확인"))
            con.execute("""INSERT INTO company_task_assignment_events
                (task_id,employee_id,action,detail)
                VALUES(?,?,'auto_assigned',?)""",
                (task_id,employee_id,
                 "소유자 승인 제안 #"+str(proposal_id)+" 부서 직원 배분"))
        con.execute("""INSERT INTO aiwack_chief_department_proposal_decisions
            (proposal_id,decision,owner_note,task_id,employee_id)
            VALUES(?,?,?,?,?)""",
            (proposal_id,decision,note,task_id,employee_id))
    return {"proposal_id":proposal_id,"decision":decision,
            "created_task_id":task_id,"assigned_employee_id":employee_id,
            "actual_chief_model_call_id":int(call_id),
            "task_status":"todo" if task_id is not None else None,
            "employee_model_executed":False,
            "owner_instruction_approval_required_for_gguf_execution":True,
            "external_actions_executed":False}


def pending_by_department(store, department_id: int|None=None, limit: int=100) -> dict:
    """Read-only department-level handoff ledger for real model proposals."""
    store.require_permission("company:manage")
    if department_id is not None and (type(department_id) is not int or
                                       department_id<=0):
        raise ValueError("부서 번호 오류")
    if type(limit) is not int or not 1<=limit<=200:
        raise ValueError("부서별 총괄 업무 조회는 1~200개입니다.")
    with store._connect() as con:
        initialize(con)
        rows=con.execute("""SELECT p.id,p.department_id,d.name,p.title,
            COALESCE(v.decision,'pending'),v.task_id,v.employee_id,
            o.model_call_id
            FROM aiwack_chief_department_proposals p
            JOIN company_departments d ON d.id=p.department_id
            JOIN aiwack_chief_department_discovery_outcomes o
                ON o.discovery_id=p.discovery_id AND o.status='success'
            LEFT JOIN aiwack_chief_department_proposal_decisions v
                ON v.proposal_id=p.id
            WHERE (? IS NULL OR p.department_id=?)
            ORDER BY p.id DESC LIMIT ?""",
            (department_id,department_id,limit)).fetchall()
    records=[dict(zip(("proposal_id","department_id","department_name",
                       "title","owner_decision","created_task_id",
                       "assigned_employee_id","real_chief_model_call_id"),row))
             for row in rows]
    return {"records":records,
            "pending_owner_review":sum(r["owner_decision"]=="pending" for r in records),
            "approved_created_task_count":sum(r["owner_decision"]=="approved"
                                              for r in records),
            "autonomous_model_employee_execution":False}
