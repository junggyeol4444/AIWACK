"""30업무·15부서 관리자 승인/지연 통합 받은편지함.

A read-only snapshot of *existing* SQLite records. Does not mark work
complete, accept chief/department-head model output, run a GGUF subprocess,
send customer data or approve finance. The actual owner must use the
individual pre-existing approval controls after opening a specific item.

Data comes from real artifact/real model audit or ordinary owner pending
states; no synthetic AI verdict or fabricated revenue.
"""
from __future__ import annotations

import hashlib
from datetime import datetime


def _has(con,name):
    return bool(con.execute("""SELECT 1 FROM sqlite_master
        WHERE type='table' AND name=?""",(name,)).fetchone())


def _digest_ok(body,sha):
    return isinstance(body,str) and isinstance(sha,str) and \
        hashlib.sha256(body.encode("utf-8")).hexdigest()==sha


def _add(items,kind,task_id,source_id,status,reason,proof=None):
    items.append({
        "kind":kind,"task_id":int(task_id) if task_id is not None else None,
        "source_id":int(source_id),"status":status,"next_owner_action":reason,
        "source_proof":proof or {},
        "owner_approval_executed_by_scan":False,
        "model_executed_by_scan":False})


def snapshot(store,limit=100):
    store.require_permission("company:manage")
    if type(limit) is not int or not 10<=limit<=500:
        raise ValueError("전사 승인·차단함 조회 10~500건")
    pending=[]
    ignored_unverified=[]
    with store._connect() as con:
        # Actual employee artifacts: owner must review the original. Filter
        # stale/manual records out of the successful real GGUF set.
        if _has(con,"company_task_artifacts"):
            rows=con.execute("""SELECT a.id,a.task_id,a.body,a.sha256,
                r.status,r.employee_id,r.model_call_id,h.status,h.employee_id
                FROM company_task_artifacts a
                JOIN company_task_runs r ON r.id=a.run_id AND r.task_id=a.task_id
                JOIN ai_model_call_history h ON h.id=r.model_call_id
                WHERE a.review_status='pending'
                ORDER BY a.id LIMIT ?""",(limit,)).fetchall()
            for aid,task,body,digest,run_status,employee,call_id,model_status,model_employee in rows:
                if (run_status=="success" and model_status=="success"
                        and employee==model_employee and _digest_ok(body,digest)):
                    _add(pending,"employee_artifact_review",task,aid,"pending",
                         "직원 실제 GGUF 결과물 검수·승인/반려",
                         {"real_staff_model_call_id":int(call_id),
                          "result_sha256":digest})
                else:
                    ignored_unverified.append({"kind":"employee_artifact",
                        "source_id":int(aid),"reason":"모델 호출 또는 결과 원본 불일치"})
        # Chief reports must be genuine audited model calls. The owner may
        # accept/reject only using the existing separate chief review UI.
        if _has(con,"company_chief_task_reports"):
            rows=con.execute("""SELECT c.id,a.task_id,c.body,c.sha256,
                c.chief_model_call_id,c.chief_employee_id,h.employee_id,h.status
                FROM company_chief_task_reports c
                JOIN company_task_artifacts a ON a.id=c.artifact_id
                LEFT JOIN ai_model_call_history h ON h.id=c.chief_model_call_id
                WHERE c.owner_decision='pending'
                ORDER BY c.id LIMIT ?""",(limit,)).fetchall()
            for rid,task,body,digest,call,chief,actual,call_status in rows:
                if (call is not None and actual==chief
                        and call_status=="success" and _digest_ok(body,digest)):
                    _add(pending,"chief_report_review",task,rid,"pending",
                         "총괄 실제 GGUF 보고서 관리자 수락·반려",
                         {"real_chief_model_call_id":int(call),
                          "chief_report_sha256":digest})
                else:
                    ignored_unverified.append({"kind":"chief_report",
                        "source_id":int(rid),"reason":"실제 총괄 모델 호출 증빙 미확인"})
        # Chief-discovered work has a distinct head-model acceptance step.
        if _has(con,"aiwack_department_head_reviews"):
            rows=con.execute("""SELECT h.id,h.task_id,h.model_call_id,h.head_employee_id,
                h.output_json,h.output_sha256,m.employee_id,m.status,
                d.id
                FROM aiwack_department_head_reviews h
                LEFT JOIN ai_model_call_history m ON m.id=h.model_call_id
                LEFT JOIN aiwack_department_head_decisions d ON d.review_id=h.id
                WHERE h.state='success' AND d.id IS NULL
                ORDER BY h.id LIMIT ?""",(limit,)).fetchall()
            for rid,task,call,head,body,digest,employee,status,decision in rows:
                if (call is not None and head==employee and status=="success"
                        and _digest_ok(body,digest)):
                    _add(pending,"department_head_forward",task,rid,"pending",
                         "부서장 실제 GGUF 의견 확인 후 총괄 전달 승인/재작업",
                         {"real_head_model_call_id":int(call),
                          "head_result_sha256":digest})
                else:
                    ignored_unverified.append({"kind":"department_head_review",
                        "source_id":int(rid),"reason":"부서장 실제 모델 원본 불일치"})
        if _has(con,"aiwack_peer_consultations"):
            rows=con.execute("""SELECT p.id,p.task_id,p.model_call_id,
                p.consultant_employee_id,p.output_text,p.output_sha256,
                m.employee_id,m.status,d.id
                FROM aiwack_peer_consultations p
                LEFT JOIN ai_model_call_history m ON m.id=p.model_call_id
                LEFT JOIN aiwack_peer_consultation_reviews d
                  ON d.consultation_id=p.id
                WHERE p.state='success' AND d.id IS NULL
                ORDER BY p.id LIMIT ?""",(limit,)).fetchall()
            for rid,task,call,consultant,body,digest,actual,state,_ in rows:
                if (call is not None and actual==consultant and state=="success"
                        and _digest_ok(body,digest)):
                    _add(pending,"peer_review",task,rid,"pending",
                         "다른 부서 직원 실제 GGUF 의견 승인 또는 반려",
                         {"real_peer_model_call_id":int(call),
                          "peer_sha256":digest})
                else:
                    ignored_unverified.append({"kind":"peer_consultation",
                        "source_id":int(rid),"reason":"직원 실제 모델 원본 불일치"})
        # A pending upstream completed-task approval is a blocker, not a
        # ready candidate. Never turn an observed 'done' into an approval.
        if _has(con,"company_task_dependencies"):
            rows=con.execute("""SELECT d.task_id,d.prerequisite_id,t.status
                FROM company_task_dependencies d
                JOIN company_tasks t ON t.id=d.prerequisite_id
                JOIN company_tasks dst ON dst.id=d.task_id AND dst.status='todo'
                WHERE t.status!='done'
                ORDER BY d.task_id,d.prerequisite_id LIMIT ?""",(limit,)).fetchall()
            for task,pre,status in rows:
                _add(pending,"upstream_incomplete",task,pre,"blocked",
                     "선행 업무의 실제 결과물·총괄 검수·관리자 완료 처리가 필요",
                     {"upstream_task_status":status})
        # Pending model attempts/leases after crashes must NOT become tasks
        # to auto-retry. Surface them separately for owner inspection.
        if _has(con,"aiwack_long_operating_attempts"):
            rows=con.execute("""SELECT id,started_at FROM aiwack_long_operating_attempts
                WHERE state='running' ORDER BY id LIMIT ?""",(limit,)).fetchall()
            for attempt,created in rows:
                _add(pending,"long_running_owner_inspection",None,attempt,"running",
                     "Windows 실제 GGUF 프로세스 및 자식 모델 잠금 관리자 직접 확인",
                     {"created_at":created})
        if _has(con,"aiwack_owner_operating_rounds"):
            rows=con.execute("""SELECT id,started_at FROM aiwack_owner_operating_rounds
                WHERE state='running' ORDER BY id LIMIT ?""",(limit,)).fetchall()
            for rid,started in rows:
                _add(pending,"operating_round_owner_inspection",None,rid,"running",
                     "기존 실제 모델 회차 미종료/잠금 확인; 자동 재호출 금지",
                     {"started_at":started})
        if _has(con,"aiwack_head_chief_batches"):
            rows=con.execute("""SELECT id,created_at FROM aiwack_head_chief_batches
                WHERE state='running' ORDER BY id LIMIT ?""",(limit,)).fetchall()
            for rid,created in rows:
                _add(pending,"head_chief_owner_inspection",None,rid,"running",
                     "기존 총괄 GGUF 실행 미종료 확인; 새 회차 자동 재사용 금지",
                     {"started_at":created})
    # Highest priority: unresolved model processes, owner review, then
    # dependency blockers. No automatic action is taken in this function.
    priority={"running":0,"pending":1,"blocked":2}
    pending.sort(key=lambda row:(priority.get(row["status"],3),
                                row["kind"],row["source_id"]))
    result=pending[:limit]
    by_kind={}
    for item in pending:by_kind[item["kind"]]=by_kind.get(item["kind"],0)+1
    return {
        "items":result,"by_kind":by_kind,
        "total_observed_with_limits":len(pending),
        "returned_count":len(result),"limit":limit,
        "individual_queries_capped":True,
        "unverified_source_count":len(ignored_unverified),
        "unverified_sources":ignored_unverified[:min(30,limit)],
        "owner_review_never_automatic":True,
        "GGUF_model_invoked":False,
        "new_tasks_or_billing_created":False,
        "verified_company_revenue":None,
        "advice":"각 항목의 기존 담당 관리자 화면에서만 승인·반려·종결하세요."
    }
