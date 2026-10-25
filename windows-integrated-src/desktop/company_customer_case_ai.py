"""고객지원부의 기존 승인 업무를 실제 직원·총괄 GGUF 실행 경로에 연결."""
from __future__ import annotations
from desktop import company_operations as ops
from desktop.stage87_90_management import stopped

def readiness(store, case_id):
    store.require_permission("company:manage")
    if type(case_id) is not int or case_id < 1:
        raise ValueError("고객 문의 번호 오류")
    case = store.read_customer_case(case_id)
    tid = int(case["task_id"])
    task = store.read_task(tid)
    route = store.read_task_routing(tid)
    department = next((d for d in store.list_departments()
                       if int(d["id"]) == route["department_id"]), None)
    if not department or department["name"] != "고객지원부":
        raise ValueError("기존 고객지원부 연결이 변경됐습니다.")
    worker = route.get("employee_id")
    model = store.read_employee_model(int(worker)) if worker else None
    order = store.read_chief_task_order(tid)
    runs = store.list_task_runs(tid)
    artifacts = store.list_task_artifacts(tid)
    ready = (case["state"] == "open" and task["status"] == "todo"
             and bool(worker) and model is not None and order is not None
             and not runs and not artifacts)
    return {"case_id":case_id, "task_id":tid, "case_state":case["state"],
            "task_state":task["status"], "department":"고객지원부",
            "employee_id":worker, "employee_model_connected":model is not None,
            "chief_order_approved":order is not None,
            "previous_runs":len(runs), "previous_artifacts":len(artifacts),
            "ready":bool(ready), "owner_review_required":True,
            "customer_reply_sent":False, "real_payment_verified":False}

def assign(store, case_id):
    store.require_permission("agents:manage")
    state=readiness(store,case_id)
    if state["case_state"]!="open" or state["task_state"]!="todo":
        raise ValueError("접수된 미실행 고객지원 업무만 배정 가능합니다.")
    with store._connect() as con:
        if stopped(con): raise PermissionError("비상정지 중 직원 배정 금지")
    result=store.auto_assign_task(state["task_id"])
    return {"assignment":result,"readiness":readiness(store,case_id),
            "model_called":False}

def approve(store, case_id, instruction):
    store.require_permission("agents:manage")
    state=readiness(store,case_id)
    if state["case_state"]!="open" or state["task_state"]!="todo":
        raise ValueError("접수된 미실행 문의만 승인할 수 있습니다.")
    if not state["employee_model_connected"] or state["chief_order_approved"]:
        raise ValueError("직원 로컬 모델 배정이 없거나 이미 총괄 지시가 승인됐습니다.")
    if not isinstance(instruction,str) or not 5<=len(instruction.strip())<=600:
        raise ValueError("관리자 총괄 지시는 5~600자여야 합니다.")
    with store._connect() as con:
        if stopped(con): raise PermissionError("비상정지 중 총괄 지시 승인 금지")
    order=store.approve_chief_task_order(state["task_id"],instruction.strip())
    return {"order_id":order,"readiness":readiness(store,case_id),
            "model_called":False}

def execute(store,case_id,*,cancel=None):
    store.require_permission("agents:manage")
    state=readiness(store,case_id)
    if not state["ready"]:
        raise PermissionError("실제 고객지원 직원·모델·총괄 승인 또는 중복 실행 검사 실패")
    if cancel is not None and cancel.is_set():
        raise InterruptedError("고객지원 실제 모델 실행 취소")
    ops.assert_running_allowed(store)
    result=ops.execute_approved_chief_cycle(store,state["task_id"],cancel=cancel)
    return {"case_id":case_id,"task_id":state["task_id"],"work":result,
            "owner_review_required":True,"customer_reply_sent":False,
            "payment_processed":False}
