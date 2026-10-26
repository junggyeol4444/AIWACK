"""관리자 승인된 실제 15부서/31AI·30업무 계획의 일괄 영속 대기열 등록.

Approved original chief orders and assigned local GGUF models already exist.
This module grants no new chief authority: one explicit owner click records
the entire *already approved* campaign/department plan in the original
owner-model queue. Existing auto/long-running runners then respect original
task dependencies, genuine GGUF calls and owner final review. No automatic
approval, payment, publish, retries, or task completion.

Registration is atomic: all step/task/model/order/dependency evidence is
inspected inside one BEGIN IMMEDIATE and all rows inserted in one transaction.
A failed precondition registers NONE of the planned tasks.
"""
from __future__ import annotations

import hashlib
import json

from desktop.stage87_90_management import stopped

_SCOPES={"wide":30,"department":5}


def _valid(scope,plan_id):
    if scope not in _SCOPES:
        raise ValueError("계획 종류는 wide 또는 department 입니다.")
    if type(plan_id) is not int or plan_id<=0:
        raise ValueError("기존 계획 번호는 양의 정수여야 합니다.")
    return scope,plan_id


def _note(value):
    if type(value) is not str or not 5<=len(value.strip())<=200:
        raise ValueError("전사 실행 등록 관리자 사유 5~200자")
    return value.strip()


def _raw(value):
    return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(",",":"))


def _sha(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def initialize(con):
    con.execute("""CREATE TABLE IF NOT EXISTS aiwack_bulk_plan_enrollments(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        scope TEXT NOT NULL CHECK(scope IN ('wide','department')),
        plan_id INTEGER NOT NULL CHECK(plan_id>0),
        source_task_id INTEGER NOT NULL REFERENCES company_tasks(id),
        chief_employee_id INTEGER NOT NULL REFERENCES ai_employee_profiles(id),
        fingerprint TEXT NOT NULL CHECK(length(fingerprint)=64),
        manifest_json TEXT NOT NULL,
        manifest_sha256 TEXT NOT NULL CHECK(length(manifest_sha256)=64),
        task_count INTEGER NOT NULL CHECK(task_count BETWEEN 2 AND 30),
        owner_note TEXT NOT NULL CHECK(length(owner_note) BETWEEN 5 AND 200),
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(scope,plan_id)
    )""")
    con.execute("""CREATE TABLE IF NOT EXISTS aiwack_bulk_plan_enrollment_items(
        enrollment_id INTEGER NOT NULL REFERENCES aiwack_bulk_plan_enrollments(id),
        ordinal INTEGER NOT NULL CHECK(ordinal BETWEEN 1 AND 30),
        task_id INTEGER NOT NULL UNIQUE REFERENCES company_tasks(id),
        queue_id INTEGER NOT NULL UNIQUE REFERENCES aiwack_owner_model_queue(id),
        employee_id INTEGER NOT NULL REFERENCES ai_employee_profiles(id),
        model_id INTEGER NOT NULL,
        chief_order_id INTEGER NOT NULL REFERENCES company_chief_task_orders(id),
        prerequisite_task_id INTEGER REFERENCES company_tasks(id),
        PRIMARY KEY(enrollment_id,ordinal)
    )""")
    con.execute("""CREATE TABLE IF NOT EXISTS aiwack_bulk_plan_enrollment_events(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        enrollment_id INTEGER NOT NULL REFERENCES aiwack_bulk_plan_enrollments(id),
        kind TEXT NOT NULL CHECK(kind='owner_enrolled'),
        manifest_sha256 TEXT NOT NULL CHECK(length(manifest_sha256)=64),
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(enrollment_id,kind)
    )""")
    for table in ("aiwack_bulk_plan_enrollments",
                  "aiwack_bulk_plan_enrollment_items",
                  "aiwack_bulk_plan_enrollment_events"):
        for operation in ("UPDATE","DELETE"):
            con.execute("""CREATE TRIGGER IF NOT EXISTS %s_no_%s
                BEFORE %s ON %s
                BEGIN SELECT RAISE(ABORT,'15부서·30업무 등록 원본/관리자 승인 변경 금지'); END"""
                %(table,operation.lower(),operation,table))


def _snapshot(con,store,scope,plan_id):
    _valid(scope,plan_id)
    plan_table=("aiwack_wide_campaigns" if scope=="wide"
                else "aiwack_department_plans")
    plan=con.execute(f"""SELECT source_task_id,source_fingerprint,
        chief_employee_id,state FROM {plan_table} WHERE id=?""",
        (plan_id,)).fetchone()
    if not plan or plan[3]!="approved":
        raise PermissionError("실제 총괄 GGUF 계획은 기존 관리자 최종 승인이 선행되어야 합니다.")
    source,source_fingerprint,chief_id,_=plan
    orig=con.execute("""SELECT title,description FROM company_tasks
        WHERE id=?""",(source,)).fetchone()
    if not orig or store._chief_task_fingerprint(str(orig[0]),str(orig[1]))!=source_fingerprint:
        raise PermissionError("총괄 계획의 원본 기준 업무 제목/설명이 변경됐습니다.")
    chief=con.execute("""SELECT e.lifecycle,m.model_id
        FROM ai_employee_profiles e
        JOIN ai_reporting_lines r ON r.employee_id=e.id AND r.tier='ceo'
        JOIN ai_employee_model_assignments m ON m.employee_id=e.id
        WHERE e.id=?""",(chief_id,)).fetchone()
    if not chief or chief[0]!="draft" or type(chief[1]) is not int:
        raise PermissionError("기존 승인된 총괄 AI 실모델 연결 불일치")
    if scope=="wide":
        steps=con.execute("""SELECT ordinal,department_id,employee_id,
            role,task_id,chief_model_call_id,plan_sha256,title,instruction
            FROM aiwack_wide_campaign_steps WHERE campaign_id=? ORDER BY ordinal""",
            (plan_id,)).fetchall()
        if len(steps)!=30 or len({row[1] for row in steps})!=15 \
                or len({row[2] for row in steps})!=30:
            raise ValueError("15부서 30직원/부서장 실제 총괄 승인 계획이 불완전합니다.")
    else:
        steps=con.execute("""SELECT ordinal,department_id,worker_employee_id,
            'staff',task_id,NULL,NULL,title,instruction
            FROM aiwack_department_plan_steps WHERE plan_id=? ORDER BY ordinal""",
            (plan_id,)).fetchall()
        if not 2<=len(steps)<=5 or len({row[1] for row in steps})<2:
            raise ValueError("기존 승인된 2~5부서 협업 업무가 불완전합니다.")
    from desktop.company_wide_campaign import _step_digest
    members=[]
    seen=set()
    for idx,step in enumerate(steps,1):
        ordinal,dept,employee,role,tid,plan_call,plan_hash,planned_title,instruction=step
        if type(ordinal) is not int or ordinal!=idx or type(tid) is not int or tid<=0:
            raise ValueError("계획 업무 순서/번호 누락 또는 변경")
        if tid in seen:
            raise ValueError("같은 작업이 다른 부서에 중복 배정됨")
        seen.add(tid)
        task=con.execute("""SELECT title,description,status FROM company_tasks
            WHERE id=?""",(tid,)).fetchone()
        if not task or task[2]!="todo":
            raise PermissionError("이미 진행·완료되었거나 수정된 계획 업무를 일괄 재실행할 수 없음")
        assignment=con.execute("""SELECT a.employee_id,e.department_id,
            e.lifecycle,m.model_id,COALESCE(r.tier,'staff')
            FROM company_task_assignments a
            JOIN ai_employee_profiles e ON e.id=a.employee_id
            JOIN ai_employee_model_assignments m ON m.employee_id=e.id
            LEFT JOIN ai_reporting_lines r ON r.employee_id=e.id
            WHERE a.task_id=?""",(tid,)).fetchone()
        if (not assignment or assignment[0]!=employee or assignment[1]!=dept
                or assignment[2]!="draft" or type(assignment[3]) is not int
                or (scope=="wide" and assignment[4]!=role)):
            raise PermissionError("계획의 부서/직원 계층/실제 GGUF 모델 연결 변경")
        route=con.execute("""SELECT department_id FROM company_task_routing
            WHERE task_id=?""",(tid,)).fetchone()
        if not route or route[0]!=dept:
            raise PermissionError("부서 업무 원래 경로가 변경됨")
        order=con.execute("""SELECT id,chief_employee_id,worker_employee_id,
            instruction,task_fingerprint
            FROM company_chief_task_orders WHERE task_id=?""",(tid,)).fetchone()
        if (not order or order[1]!=chief_id or order[2]!=employee
                or order[3]!=instruction
                or order[4]!=store._chief_task_fingerprint(str(task[0]),str(task[1]))):
            raise PermissionError("관리자가 승인한 총괄 실제 업무 지시 원본이 변경됨")
        previous=steps[idx-2][4] if idx>1 else None
        deps=[r[0] for r in con.execute("""SELECT prerequisite_id
            FROM company_task_dependencies WHERE task_id=?
            ORDER BY prerequisite_id""",(tid,)).fetchall()]
        if previous is not None and previous not in deps:
            raise PermissionError("전사 업무 부서간 단계별 선행 의존성 훼손")
        if scope=="wide":
            if (type(plan_call) is not int or not plan_hash or
                    _step_digest(plan_id,ordinal,dept,employee,role,
                                 planned_title,instruction,plan_call)!=plan_hash):
                raise PermissionError("실제 총괄 GGUF 단계 계획 SHA256 원본 불일치")
            model=con.execute("""SELECT employee_id,status,output_chars FROM
                ai_model_call_history WHERE id=?""",(plan_call,)).fetchone()
            if (not model or model[0]!=chief_id or model[1]!="success"
                    or not model[2] or int(model[2])<1):
                raise PermissionError("원본 전사 계획의 실제 총괄 GGUF 성공 호출 없음")
        if con.execute("""SELECT 1 FROM aiwack_owner_model_queue
            WHERE task_id=?""",(tid,)).fetchone():
            raise PermissionError("이전 등록/실행/취소된 계획 업무는 재등록하지 않음")
        if con.execute("""SELECT 1 FROM company_task_runs WHERE task_id=?""",
                       (tid,)).fetchone() or con.execute(
                        """SELECT 1 FROM company_task_artifacts WHERE task_id=?""",
                        (tid,)).fetchone() or con.execute(
                        """SELECT 1 FROM aiwack_autopilot_model_runs WHERE task_id=?""",
                        (tid,)).fetchone():
            raise PermissionError("이전 직원 모델 실행/실패 기록은 자동 재시도 금지")
        members.append({
            "ordinal":idx,"task_id":int(tid),
            "department_id":int(dept),"employee_id":int(employee),
            "employee_model_id":int(assignment[3]),
            "role":role,"chief_order_id":int(order[0]),
            "chief_plan_call_id":plan_call,
            "chief_plan_step_sha256":plan_hash,
            "task_fingerprint":order[4],
            "dependencies":deps,
            "previous_plan_task_id":int(previous) if previous else None
        })
    return {
        "scope":scope,"plan_id":int(plan_id),"source_task_id":int(source),
        "source_fingerprint":source_fingerprint,
        "chief_employee_id":int(chief_id),"chief_model_id":int(chief[1]),
        "steps":members
    }


def preview(store,scope,plan_id):
    store.require_permission("company:manage")
    _valid(scope,plan_id)
    from desktop import company_autopilot,company_owner_model_queue
    company_autopilot.initialize(store)
    with store._connect() as con:
        company_owner_model_queue.initialize(con)
        initialize(con)
        manifest=_snapshot(con,store,scope,plan_id)
        enrolled=con.execute("""SELECT id FROM aiwack_bulk_plan_enrollments
            WHERE scope=? AND plan_id=?""",(scope,plan_id)).fetchone()
    return {"plan":manifest,"manifest_sha256":_sha(_raw(manifest)),
            "already_enrolled":bool(enrolled),
            "all_tasks_execute_after_separate_existing_model_policy":True,
            "no_genuine_model_invoked":True,"no_result_approved":True,
            "no_money_or_customer_actions":True}


def enqueue_all(store,scope,plan_id,owner_note):
    """Atomic one-click owner authorization for existing approved plan steps."""
    store.require_permission("company:manage")
    store.require_permission("agents:manage")
    scope,plan_id=_valid(scope,plan_id)
    note=_note(owner_note)
    from desktop import company_autopilot,company_owner_model_queue
    company_autopilot.initialize(store)
    with store._connect() as con:
        con.execute("BEGIN IMMEDIATE")
        company_owner_model_queue.initialize(con)
        initialize(con)
        if stopped(con):
            raise PermissionError("비상정지 상태에서는 GGUF 계획 등록 금지")
        if con.execute("""SELECT 1 FROM aiwack_bulk_plan_enrollments
            WHERE scope=? AND plan_id=?""",(scope,plan_id)).fetchone():
            raise ValueError("기존 승인 계획의 일괄 등록 감사가 이미 존재합니다")
        manifest=_snapshot(con,store,scope,plan_id)
        raw=_raw(manifest)
        digest=_sha(raw)
        entry_id=int(con.execute("""INSERT INTO aiwack_bulk_plan_enrollments(
            scope,plan_id,source_task_id,chief_employee_id,fingerprint,
            manifest_json,manifest_sha256,task_count,owner_note)
            VALUES(?,?,?,?,?,?,?,?,?)""",
            (scope,plan_id,manifest["source_task_id"],
             manifest["chief_employee_id"],manifest["source_fingerprint"],
             raw,digest,len(manifest["steps"]),note)).lastrowid)
        queue_ids=[]
        for part in manifest["steps"]:
            # This is not a claimed or running job. Original FIFO and
            # shared BEGIN IMMEDIATE gates check dependencies later.
            qid=int(con.execute("""INSERT INTO aiwack_owner_model_queue
                (task_id,owner_note,state) VALUES(?,?,'pending')""",
                (part["task_id"],note)).lastrowid)
            con.execute("""INSERT INTO aiwack_owner_model_queue_events
                (queue_id,event_kind,detail) VALUES(?,'enqueued',?)""",
                (qid,"관리자 승인 "+scope+" 계획 #"+str(plan_id)))
            con.execute("""INSERT INTO aiwack_bulk_plan_enrollment_items
                (enrollment_id,ordinal,task_id,queue_id,employee_id,
                 model_id,chief_order_id,prerequisite_task_id)
                VALUES(?,?,?,?,?,?,?,?)""",
                (entry_id,part["ordinal"],part["task_id"],qid,
                 part["employee_id"],part["employee_model_id"],
                 part["chief_order_id"],part["previous_plan_task_id"]))
            queue_ids.append(qid)
        con.execute("""INSERT INTO aiwack_bulk_plan_enrollment_events
            (enrollment_id,kind,manifest_sha256)
            VALUES(?,'owner_enrolled',?)""",(entry_id,digest))
    return {"enrollment_id":entry_id,"scope":scope,"plan_id":plan_id,
            "registered_tasks":len(queue_ids),"queue_ids":queue_ids,
            "manifest_sha256":digest,"genuine_GGUF_called":False,
            "all_results_require_owner_review":True,
            "dependencies_not_bypassed":True,
            "model_retry_enabled":False,"external_actions":False}


def history(store,limit=30):
    store.require_permission("company:manage")
    if type(limit) is not int or not 1<=limit<=100:
        raise ValueError("전사 GGUF 계획 등록 감사 1~100건")
    with store._connect() as con:
        initialize(con)
        rows=con.execute("""SELECT id,scope,plan_id,task_count,
            manifest_json,manifest_sha256,created_at
            FROM aiwack_bulk_plan_enrollments ORDER BY id DESC LIMIT ?""",
            (limit,)).fetchall()
        result=[]
        for entry_id,scope,plan_id,count,raw,digest,created in rows:
            parts=con.execute("""SELECT ordinal,task_id,queue_id
                FROM aiwack_bulk_plan_enrollment_items
                WHERE enrollment_id=? ORDER BY ordinal""",(entry_id,)).fetchall()
            if _sha(raw)!=digest or len(parts)!=count:
                raise ValueError("기존 관리자 전사 실행 등록 원본 불변 감사 훼손")
            statuses=[]
            for ordinal,task_id,queue_id in parts:
                current=con.execute("""SELECT state FROM aiwack_owner_model_queue
                    WHERE id=? AND task_id=?""",(queue_id,task_id)).fetchone()
                if current is None:
                    raise PermissionError("기존 GGUF 업무 대기열 원본 삭제/변경")
                statuses.append({"ordinal":int(ordinal),"task_id":int(task_id),
                                 "queue_id":int(queue_id),"queue_state":current[0]})
            result.append({
                "enrollment_id":int(entry_id),"scope":scope,"plan_id":int(plan_id),
                "task_count":int(count),"manifest_sha256":digest,
                "created_at":created,"steps":statuses,
                "actual_model_results_not_inferred_from_enrollment":True,
                "requires_individual_owner_review":True})
    return result
