"""15부서·30업무 기존 승인 계획을 관리자 GGUF 영속 대기열에 안전하게 연결.

실제 30업무 원본/총괄 모델 호출/관리자 완료를 검사하고, 매번 다음
정확히 한 업무만 관리자의 별도 클릭으로 등록한다. 일괄 자동 승인 없음.
"""
from __future__ import annotations


def preview(store, campaign_id: int) -> dict:
    store.require_permission("company:manage")
    if type(campaign_id) is not int or campaign_id <= 0:
        raise ValueError("15부서·30업무 계획 번호는 양의 정수여야 합니다.")
    from desktop.company_campaign_resume_gate import snapshot
    from desktop import company_autopilot, company_owner_model_queue
    from desktop.company_model_queue_readiness import _ready_in_tx
    progress = snapshot(store, campaign_id, require_genuine_provenance=True)
    task_id = progress.get("next_task_id")
    queue = None
    readiness = None
    if type(task_id) is int and task_id > 0:
        company_autopilot.initialize(store)
        with store._connect() as con:
            company_owner_model_queue.initialize(con)
            row = con.execute("""SELECT id,state FROM aiwack_owner_model_queue
                WHERE task_id=?""", (task_id,)).fetchone()
            if row:
                queue = {"queue_id": int(row[0]), "state": row[1]}
            readiness = _ready_in_tx(con, task_id)
    can_enqueue = (progress.get("state") == "ready" and queue is None
                   and readiness is not None and readiness["ready"])
    return {"campaign_id": campaign_id, "state": progress.get("state"),
            "next_ordinal": progress.get("next_ordinal"),
            "next_task_id": task_id, "verified_completed_tasks":
                progress.get("verified_completed_tasks", 0),
            "verified_genuine_prefix_tasks":
                progress.get("verified_genuine_prefix_tasks", 0),
            "reason": progress.get("reason"), "queue": queue,
            "readiness": readiness, "can_enqueue": bool(can_enqueue),
            "owner_approval_required_each_step": True,
            "model_called": False, "automatically_retried": False}


def enqueue_next(store, campaign_id: int, owner_note: str) -> dict:
    """관리자가 현재 30업무의 다음 한 단계만 명시적으로 등록."""
    store.require_permission("company:manage")
    store.require_permission("agents:manage")
    if not isinstance(owner_note, str) or not 5 <= len(owner_note.strip()) <= 200:
        raise ValueError("관리자 등록 사유는 5~200자여야 합니다.")
    current = preview(store, campaign_id)
    if not current["can_enqueue"]:
        raise PermissionError("다음 협업 단계는 등록할 수 없습니다: "
                              + str(current["reason"])[:200] + " / "
                              + str(current["readiness"])[:200])
    from desktop.company_campaign_resume_gate import require_next
    from desktop.company_owner_model_queue import enqueue
    # 실행/승인 단계에서 기존 업무/협업 증빙을 다시 검사한다.
    require_next(store, campaign_id, current["next_task_id"],
                 require_genuine_provenance=True)
    saved = enqueue(store, current["next_task_id"], owner_note)
    return {**saved, "campaign_id": campaign_id,
            "ordinal": current["next_ordinal"],
            "owner_approval_required_each_step": True,
            "owner_result_review_required": True,
            "model_called": False, "external_actions": False}
