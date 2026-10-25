"""30업무 영속 GGUF 대기열과 실제 호출·직원 결과물 읽기 전용 대조.
실행 성공은 관리자 승인과 다르다. 재호출/잠금 해제/승인/외부 전송 없음.
"""
from __future__ import annotations
from desktop import company_autopilot, company_owner_model_queue

def snapshot(store, limit=100):
    store.require_permission("company:manage")
    if type(limit) is not int or not 1 <= limit <= 500:
        raise ValueError("실제 GGUF 감사 조회 범위는 1~500건입니다.")
    company_autopilot.initialize(store)
    with store._connect() as con:
        company_owner_model_queue.initialize(con)
        rows = con.execute("""SELECT q.id,q.task_id,q.state,t.status,
                    (SELECT COUNT(*) FROM aiwack_owner_model_queue_events e WHERE e.queue_id=q.id),
                    (SELECT COUNT(*) FROM aiwack_autopilot_model_runs m WHERE m.task_id=q.task_id),
                    (SELECT COUNT(*) FROM aiwack_autopilot_model_runs m
                       WHERE m.task_id=q.task_id AND m.state='running'),
                    (SELECT COUNT(*) FROM aiwack_autopilot_model_leases l WHERE l.task_id=q.task_id),
                    (SELECT COUNT(*) FROM company_task_runs r WHERE r.task_id=q.task_id),
                    (SELECT COUNT(*) FROM company_task_artifacts a WHERE a.task_id=q.task_id),
                    (SELECT COUNT(*) FROM company_task_artifacts a
                       WHERE a.task_id=q.task_id AND a.review_status='approved')
                    FROM aiwack_owner_model_queue q
                    JOIN company_tasks t ON t.id=q.task_id
                    ORDER BY q.id DESC LIMIT ?""", (limit,)).fetchall()
        results = []
        for (qid,tid,state,task_state,events,attempts,active,leases,
             worker_runs,artifacts,approved) in rows:
            issues = []
            if state=="pending" and attempts:
                issues.append("대기 중 기존 GGUF 호출 기록 존재")
            if state=="running" and active==0:
                issues.append("실행 중 대기열에 활성 GGUF 호출 기록 없음")
            if state in ("failed","cancelled") and active:
                issues.append("종료 대기열에 활성 모델 기록 존재")
            if attempts>1:
                issues.append("동일 업무 모델 호출 감사 복수 존재")
            if state=="succeeded" and worker_runs==0:
                issues.append("성공 대기열에 직원 실행 원본 없음")
            if leases and state!="running":
                issues.append("비실행 대기열에 모델 잠금 존재")
            if state=="succeeded" and not approved:
                issues.append("실행 후 관리자 결과물 승인 대기")
            results.append({"queue_id":int(qid),"task_id":int(tid),
                "queue_state":state,"task_state":task_state,
                "queue_audit_events":int(events),"model_call_records":int(attempts),
                "active_model_call_records":int(active),"model_leases":int(leases),
                "worker_run_records":int(worker_runs),"employee_artifacts":int(artifacts),
                "owner_approved_artifacts":int(approved),
                "requires_owner_review":bool(issues) or state=="succeeded",
                "issues":issues,"model_called_during_this_inspection":False})
    return {"rows":results,"rows_in_page":len(results),
            "page_limited":len(results)==limit,"audit_only":True,
            "model_retried":False,"owner_approval_per_step_required":True,
            "external_actions":False}
