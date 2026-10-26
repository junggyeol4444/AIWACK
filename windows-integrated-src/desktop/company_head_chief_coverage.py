"""15부서·31AI의 실제 총괄→직원→부서장→총괄 승인 경로 근거 조회.

읽기 전용 집계. 단계 번호, 인원, 매출, 상품 효과를 추정하지 않는다.
SQLite 원본에 실제 기록된 업무/직원 모델/승인·회수 감사만 보여 준다.
"""
from __future__ import annotations


def report(store, *, limit=100):
    store.require_permission('company:manage')
    if type(limit) is not int or not 1<=limit<=500:
        raise ValueError("전사 업무 원본 조회는 1~500개입니다.")
    with store._connect() as con:
        departments=[{"department_id":int(r[0]),"name":r[1],
                      "model_staff":int(r[2]),"model_heads":int(r[3])}
            for r in con.execute("""SELECT d.id,d.name,
                 (SELECT COUNT(*) FROM ai_employee_profiles e
                  JOIN ai_reporting_lines rl ON rl.employee_id=e.id AND rl.tier='staff'
                  JOIN ai_employee_model_assignments m ON m.employee_id=e.id
                  WHERE e.department_id=d.id AND e.lifecycle='draft'),
                 (SELECT COUNT(*) FROM ai_employee_profiles e
                  JOIN ai_reporting_lines rl ON rl.employee_id=e.id
                     AND rl.tier='department_head'
                  JOIN ai_employee_model_assignments m ON m.employee_id=e.id
                  WHERE e.department_id=d.id AND e.lifecycle='draft')
                 FROM company_departments d ORDER BY d.id""").fetchall()]
        required=[
            "aiwack_chief_department_proposals",
            "aiwack_chief_department_proposal_decisions",
            "aiwack_department_head_reviews",
            "aiwack_department_head_decisions",
        ]
        existing={r[0] for r in con.execute("""SELECT name FROM sqlite_master
             WHERE type='table'""").fetchall()}
        if not set(required).issubset(existing):
            return {"departments":departments,
                    "records":[],"counts":{"real_chief_proposals":0},
                    "source_tables_ready":False,
                    "verified_revenue":None,
                    "owner_final_approval_automatic":False}
        query="""SELECT p.id,p.department_id,p.title,
            COALESCE(d.decision,'pending') AS proposal_decision,d.task_id,d.employee_id,
            t.status,
            EXISTS(SELECT 1 FROM company_task_runs r
                JOIN ai_model_call_history m ON m.id=r.model_call_id
                WHERE r.task_id=d.task_id AND r.status='success'
                  AND m.status='success') AS actual_staff_model_success,
            (SELECT a.id FROM company_task_artifacts a
                JOIN company_task_runs r ON r.id=a.run_id
                WHERE a.task_id=d.task_id AND r.status='success'
                ORDER BY a.id DESC LIMIT 1) AS artifact_id
            FROM aiwack_chief_department_proposals p
            LEFT JOIN aiwack_chief_department_proposal_decisions d
                ON d.proposal_id=p.id
            LEFT JOIN company_tasks t ON t.id=d.task_id
            ORDER BY p.id DESC LIMIT ?"""
        rows=con.execute(query,(limit,)).fetchall()
        details=[]
        for pid,dep,title,choice,tid,employee,status,staff_ok,aid in rows:
            head_state=None
            head_call=None
            head_choice=None
            chief_report=None
            chief_real_call=None
            chief_owner=None
            artifact_owner=None
            if aid is not None:
                head=con.execute("""SELECT h.state,h.model_call_id,
                    (SELECT decision FROM aiwack_department_head_decisions
                     WHERE review_id=h.id)
                    FROM aiwack_department_head_reviews h
                    WHERE h.artifact_id=?""",(aid,)).fetchone()
                if head:
                    head_state,head_call,head_choice=head
                chief=con.execute("""SELECT id,chief_model_call_id,owner_decision
                    FROM company_chief_task_reports WHERE artifact_id=?""",
                    (aid,)).fetchone()
                if chief:
                    chief_report,chief_real_call,chief_owner=chief
                art=con.execute("SELECT review_status FROM company_task_artifacts WHERE id=?",
                                (aid,)).fetchone()
                if art:
                    artifact_owner=art[0]
            details.append({
                "chief_proposal_id":int(pid),"department_id":int(dep),
                "title":str(title),
                "proposal_owner_decision":choice,
                "task_id":tid,"assigned_employee_id":employee,
                "task_status":status,
                "staff_real_model_success":bool(staff_ok),
                "saved_artifact_id":aid,
                "department_head_state":head_state,
                "department_head_real_model_call_id":head_call,
                "department_head_owner_forward_decision":head_choice,
                "chief_report_id":chief_report,
                "chief_real_model_call_id":chief_real_call,
                "chief_owner_decision":chief_owner,
                "artifact_owner_decision":artifact_owner,
                "owner_final_task_done":status=="done",
                "verified_external_revenue":None,
            })
    key=lambda field:sum(bool(row[field]) for row in details)
    return {
        "departments":departments,
        "records":details,
        "counts":{
            "real_chief_proposals":len(details),
            "owner_approved_proposals":sum(r["proposal_owner_decision"]=="approved" for r in details),
            "actual_staff_model_success":key("staff_real_model_success"),
            "actual_head_model_success":sum(r["department_head_state"]=="success" for r in details),
            "head_forwarded_by_owner":sum(r["department_head_owner_forward_decision"]=="forward" for r in details),
            "actual_chief_report_saved":key("chief_report_id"),
            "chief_report_owner_accepted":sum(r["chief_owner_decision"]=="accepted" for r in details),
            "owner_completed_tasks":key("owner_final_task_done"),
        },
        "source_tables_ready":True,
        "records_are_limited":True,
        "verified_revenue":None,
        "owner_final_approval_automatic":False,
        "no_model_invoked_by_report":True,
    }
