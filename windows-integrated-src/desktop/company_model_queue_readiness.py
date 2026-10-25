"""기존 승인된 실제 GGUF 영속 대기열의 선행 업무·협업 증빙 준비 상태.

읽기/선택만 수행한다. 미완료 선행 업무나 관리자 검수 대기는 건너뛰되
대기열·모델 호출 기록을 삭제하거나 자동으로 완료/승인하지 않는다.
"""
from __future__ import annotations


def _ready_in_tx(con, task_id: int) -> dict:
    """현재 SQLite 스냅샷에서 실행 가능 여부를 보수적으로 판정."""
    if type(task_id) is not int or task_id <= 0:
        raise ValueError("승인된 업무 번호가 올바르지 않습니다.")
    task = con.execute("SELECT status FROM company_tasks WHERE id=?", (task_id,)).fetchone()
    if task is None:
        return {"ready": False, "reason": "기존 업무가 없습니다."}
    if task[0] != "todo":
        return {"ready": False, "reason": "업무 상태가 미실행(todo)이 아닙니다."}
    order = con.execute(
        "SELECT worker_employee_id FROM company_chief_task_orders WHERE task_id=?",
        (task_id,)).fetchone()
    if not order:
        return {"ready": False, "reason": "관리자가 승인한 총괄 지시가 없습니다."}
    worker = con.execute("""SELECT e.id,e.lifecycle,m.model_id
        FROM company_task_assignments a
        JOIN ai_employee_profiles e ON e.id=a.employee_id
        LEFT JOIN ai_employee_model_assignments m ON m.employee_id=e.id
        WHERE a.task_id=?""", (task_id,)).fetchone()
    if not worker or worker[1] != "draft" or worker[2] is None or worker[0] != order[0]:
        return {"ready": False, "reason": "승인 지시와 실제 모델 연결 직원 배정이 일치하지 않습니다."}
    if con.execute("SELECT 1 FROM company_task_runs WHERE task_id=? LIMIT 1", (task_id,)).fetchone():
        return {"ready": False, "reason": "직원 실행 감사가 이미 있습니다. 자동 재실행 금지."}
    if con.execute("""SELECT 1 FROM company_task_runs
        WHERE employee_id=? AND status='running' LIMIT 1""", (worker[0],)).fetchone():
        return {"ready": False, "reason": "담당 직원의 다른 실제 모델 업무가 실행 중입니다."}
    active = con.execute("SELECT COUNT(*) FROM company_task_runs WHERE status='running'").fetchone()[0]
    if active >= 2:
        return {"ready": False, "reason": "기존 실제 직원 모델 동시 실행 한도(2건) 도달."}
    if con.execute("SELECT 1 FROM company_task_artifacts WHERE task_id=? LIMIT 1", (task_id,)).fetchone():
        return {"ready": False, "reason": "기존 직원 결과물이 있어 자동 재실행 금지."}
    if con.execute("SELECT 1 FROM aiwack_autopilot_model_runs WHERE task_id=? LIMIT 1",
                   (task_id,)).fetchone():
        return {"ready": False, "reason": "과거 자동 GGUF 호출 감사가 있어 재시도 금지."}
    if con.execute("SELECT 1 FROM aiwack_autopilot_model_leases WHERE task_id=?",
                   (task_id,)).fetchone():
        return {"ready": False, "reason": "다른 Windows 창의 실제 모델 잠금이 남아 있습니다."}
    waiting = [int(r[0]) for r in con.execute("""SELECT d.prerequisite_id
        FROM company_task_dependencies d JOIN company_tasks t ON t.id=d.prerequisite_id
        WHERE d.task_id=? AND t.status!='done' ORDER BY d.prerequisite_id""",
        (task_id,)).fetchall()]
    if waiting:
        return {"ready": False, "reason": "관리자 완료 대기 선행 업무: " + ",".join(map(str, waiting)),
                "pending_prerequisites": waiting}
    # 부서/회사 전체 협업은 'done' 표시만으로 실행을 허용하지 않는다.
    # 기존 직원·총괄 실제 모델 원본 및 관리자 인계 증빙 검사를 그대로 사용.
    try:
        from desktop.company_department_progress import assert_collaboration_prerequisites
        from desktop.company_wide_campaign import assert_handoff_ready
        assert_collaboration_prerequisites(con, task_id)
        assert_handoff_ready(con, task_id)
    except (ValueError, PermissionError, RuntimeError) as exc:
        return {"ready": False, "reason": "협업 인계 원본 검토 필요: " + str(exc)[:240]}
    return {"ready": True, "reason": "관리자 승인·선행 업무·협업 인계 준비 확인",
            "employee_id": int(worker[0]), "pending_prerequisites": []}


def _first_ready_in_tx(con):
    """FIFO를 유지하되 검수 대기 항목 때문에 다른 독립 업무가 굶지 않도록 선택."""
    cursor = con.execute("""SELECT id,task_id FROM aiwack_owner_model_queue
        WHERE state='pending' ORDER BY id""")
    for queue_id, task_id in cursor:
        readiness = _ready_in_tx(con, int(task_id))
        if readiness["ready"]:
            return {"id": int(queue_id), "task_id": int(task_id), **readiness}
    return None


def inspect(store, limit: int = 100) -> list[dict]:
    """관리자 조회 전용. 실제 GGUF·결제·외부 네트워크를 실행하지 않는다."""
    store.require_permission("company:manage")
    if type(limit) is not int or not 1 <= limit <= 500:
        raise ValueError("대기열 준비 상태 조회는 1~500건입니다.")
    from desktop import company_autopilot, company_owner_model_queue
    company_autopilot.initialize(store)
    with store._connect() as con:
        company_owner_model_queue.initialize(con)
        rows = con.execute("""SELECT id,task_id,state,created_at
            FROM aiwack_owner_model_queue ORDER BY id DESC LIMIT ?""", (limit,)).fetchall()
        result = []
        for queue_id, task_id, state, created_at in rows:
            readiness = (_ready_in_tx(con, int(task_id)) if state == "pending"
                         else {"ready": False, "reason": "현재 대기 상태가 아닙니다."})
            result.append({"queue_id": int(queue_id), "task_id": int(task_id),
                           "state": state, "created_at": created_at, **readiness,
                           "model_invoked_by_read": False, "owner_final_approval_required": True})
    return result
