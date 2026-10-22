"""소유자 승인 다부서 협업의 실제 직원/총괄 모델 실행 단계.

원본 SQLite 승인 지시, 업무 의존성, 직원 모델 배정, 비상정지,
실제 모델 실행 감사와 소유자 검수 흐름을 그대로 사용한다.
"""
from __future__ import annotations

import hashlib


def next_step(store, plan_id: int) -> dict:
    """실제 SQLite 기록으로 다음 실행 가능한 단계와 차단 원인을 확인한다."""
    from desktop import company_department_collaboration as chain
    store.require_permission('company:manage')
    plan=chain.read_plan(store,plan_id)
    if plan['state']!='approved':
        return {'ready':False,'reason':'소유자 승인 전 협업 계획입니다.',
                'task_id':None,'employee_id':None,'finished':False}
    for step in plan['steps']:
        task_id,employee_id=step['task_id'],step['employee_id']
        if task_id is None or employee_id is None:
            return {'ready':False,'reason':'실제 업무 또는 직원 연결이 없습니다.',
                    'task_id':task_id,'employee_id':employee_id,'finished':False}
        if step['task_status']=='done':
            # A manual status toggle is NOT evidence that the owner reviewed
            # a real staff result. Do not let it unlock the next department.
            with store._connect() as con:
                reviewed = verified_collaboration_result(
                    con, plan_id, task_id, employee_id)
            if not reviewed:
                return {'ready':False,
                        'reason':f"{step['ordinal']}단계 완료 표시는 있으나 실제 직원 실행·소유자 승인 결과물이 없습니다.",
                        'task_id':task_id,'employee_id':employee_id,'finished':False}
            continue
        if step['task_status']!='todo':
            # Explain the exact existing owner recovery path. No automatic
            # rerun, chief acceptance, or task completion is performed here.
            if step['task_status']=='in_progress':
                artifacts=store.list_task_artifacts(task_id)
                if len(artifacts)==1:
                    report=store.find_chief_task_report(artifacts[0]['id'])
                    if report is None:
                        reason='저장된 직원 결과물이 있습니다. 총괄 AI 검토 복구를 관리자에게 요청하세요.'
                    elif report['owner_decision']=='rejected':
                        reason='총괄 AI 검토가 소유자에 의해 반려됐습니다. 후속 업무 실행이 차단됩니다.'
                    elif report['owner_decision']=='pending':
                        reason='총괄 AI 보고서가 아직 소유자 수락 전입니다. 검수 후 진행하세요.'
                    elif artifacts[0]['review_status']!='approved':
                        reason='총괄 AI 보고서는 수락됐지만 직원 결과물의 소유자 승인이 필요합니다.'
                    else:
                        reason='실제 직원·총괄 검수가 끝났습니다. 관리자 업무 완료 처리가 필요합니다.'
                else:
                    reason='진행 중 또는 중단된 업무입니다. 관리자 실행 감사·복구 확인이 필요합니다.'
            else:
                reason=f"{step['ordinal']}단계 상태: {step['task_status']}"
            return {'ready':False,'reason':reason,
                    'task_id':task_id,'employee_id':employee_id,'finished':False}
        if store.list_task_runs(task_id) or store.list_task_artifacts(task_id):
            return {'ready':False,'reason':'기존 실행 기록이 있습니다. 소유자 검수 또는 복구가 필요합니다.',
                    'task_id':task_id,'employee_id':employee_id,'finished':False}
        deps=store.task_dependency_readiness(task_id)
        if not deps['ready']:
            return {'ready':False,'reason':f"선행 업무 미완료: {deps['pending_ids']}",
                    'task_id':task_id,'employee_id':employee_id,'finished':False}
        order=store.read_chief_task_order(task_id)
        route=store.read_task_routing(task_id)
        if (order is None or route['employee_id']!=employee_id
                or int(order['worker_employee_id'])!=employee_id):
            return {'ready':False,'reason':'승인 총괄 지시 또는 담당 직원이 변경되었습니다.',
                    'task_id':task_id,'employee_id':employee_id,'finished':False}
        if store.read_employee_model(employee_id) is None:
            return {'ready':False,'reason':'담당 직원 로컬 모델이 연결되지 않았습니다.',
                    'task_id':task_id,'employee_id':employee_id,'finished':False}
        return {'ready':True,'reason':'소유자 확인 후 실제 직원·총괄 모델 호출 가능',
                'task_id':task_id,'employee_id':employee_id,'ordinal':step['ordinal'],
                'department':step['department'],'title':step['title'],'finished':False}
    return {'ready':False,'reason':'승인된 협업 단계 모두 완료',
            'task_id':None,'employee_id':None,'finished':True}


def execute_next_step(store, plan_id: int, expected_task_id: int,
                      expected_employee_id: int, *, cancel=None) -> dict:
    """확인한 단계 한 건만 직원→총괄 모델 실행; 결과물은 소유자 검수 대기."""
    from desktop import company_operations as ops
    store.require_permission('company:manage')
    store.require_permission('agents:manage')
    for value in (plan_id,expected_task_id,expected_employee_id):
        if type(value) is not int or value<=0:
            raise ValueError('협업 계획·업무·직원 번호는 양의 정수여야 합니다.')
    ops.assert_running_allowed(store)
    if cancel is not None and cancel.is_set():
        raise InterruptedError('직원 모델 실행이 시작 전에 취소되었습니다.')
    state=next_step(store,plan_id)
    if (not state['ready'] or state['task_id']!=expected_task_id
            or state['employee_id']!=expected_employee_id):
        raise ValueError('확인한 협업 단계가 변경됐거나 선행 업무가 미완료입니다.')
    # 기존 업무 엔진이 BEGIN IMMEDIATE로 동시 실행/의존성/승인 재검증.
    result=ops.execute_approved_chief_cycle(store,expected_task_id,cancel=cancel)
    return {**result,'collaboration_plan_id':plan_id,
            'collaboration_ordinal':state['ordinal']}


def report(store, plan_id: int) -> str:
    """기존 업무·모델 감사와 연결한 읽기 전용 단계 진행 현황."""
    from desktop import company_department_collaboration as chain
    plan=chain.read_plan(store,plan_id)
    state=next_step(store,plan_id)
    lines=[chain.report_text(plan), '다음 단계: '+state['reason']]
    for step in plan['steps']:
        task_id=step['task_id']
        if task_id is None:
            continue
        runs=store.list_task_runs(task_id,limit=20)
        artifacts=store.list_task_artifacts(task_id)
        lines.append(f"{step['ordinal']}단계 / 업무 #{task_id} / 직원 #{step['employee_id']}"
                     f" / 상태 {step['task_status']} / 실제 실행 {len(runs)}건"
                     f" / 실제 결과물 {len(artifacts)}건"
                     f" / 검수 대기 {sum(a['review_status']=='pending' for a in artifacts)}건"
                     f" / 총괄 검토 {sum(store.find_chief_task_report(a['id']) is not None for a in artifacts)}건")
    return '\n'.join(lines)


def verified_collaboration_result(con, plan_id: int, task_id: int,
                                  employee_id: int) -> bool:
    """Enforce the full worker/chief evidence at the SQLite shared boundary.

    An accepted status and foreign keys alone do not protect the text against
    later modification. Validate the original worker and chief digests and
    require the SAME run, model, approved order and dispatch on every check.
    """
    row = con.execute("""SELECT a.body,a.sha256,c.body,c.sha256,
            r.model_id,h.model_id,r.output_chars,h.output_chars,
            r.task_id,a.task_id,o.task_id,r.employee_id,h.employee_id,
            o.worker_employee_id,o.chief_employee_id,p.chief_employee_id,
            c.chief_employee_id,d.run_id,r.id,c.artifact_id,a.id,
            d.order_id,c.order_id,o.id
        FROM aiwack_department_plans p
        JOIN aiwack_department_plan_steps s ON s.plan_id=p.id
        JOIN company_task_runs r ON r.task_id=s.task_id
            AND r.employee_id=s.worker_employee_id AND r.status='success'
        JOIN ai_model_call_history h ON h.id=r.model_call_id
            AND h.employee_id=r.employee_id AND h.status='success'
        JOIN company_task_artifacts a ON a.run_id=r.id
            AND a.task_id=r.task_id AND a.review_status='approved'
        JOIN company_chief_task_dispatches d ON d.run_id=r.id
        JOIN company_chief_task_orders o ON o.id=d.order_id
            AND o.task_id=r.task_id AND o.worker_employee_id=r.employee_id
            AND o.chief_employee_id=p.chief_employee_id
        JOIN company_chief_task_reports c ON c.artifact_id=a.id
            AND c.order_id=o.id AND c.chief_employee_id=p.chief_employee_id
            AND c.owner_decision='accepted'
        WHERE p.id=? AND p.state='approved' AND s.task_id=?
            AND s.worker_employee_id=? LIMIT 1""",
        (plan_id,task_id,employee_id)).fetchone()
    if row is None:
        return False
    (worker_body,worker_hash,chief_body,chief_hash,run_model,call_model,
     run_chars,call_chars,*links)=row
    return bool(
        hashlib.sha256(str(worker_body).encode('utf8')).hexdigest()==worker_hash
        and hashlib.sha256(str(chief_body).encode('utf8')).hexdigest()==chief_hash
        and int(run_model)==int(call_model)
        and int(run_chars)>0 and int(call_chars)>0
        and links[0]==links[1]==links[2]==task_id
        and links[3]==links[4]==links[5]==employee_id
        and links[6]==links[7]==links[8]
        and links[9]==links[10] and links[11]==links[12]
        and links[13]==links[14]==links[15])


def assert_collaboration_completion(con, task_id: int) -> None:
    """관리자 업무 완료를 실제 승인된 직원/총괄 증빙에 결속한다.

    SQLite BEGIN IMMEDIATE 트랜잭션 안에서만 호출. 일반 업무에는 영향 없음.
    """
    assert_wide_completion(con, task_id)
    if not con.execute("""SELECT 1 FROM sqlite_master WHERE type='table'
                          AND name='aiwack_department_plan_steps'""").fetchone():
        return
    step=con.execute("""SELECT p.state,s.plan_id,s.worker_employee_id
        FROM aiwack_department_plan_steps s
        JOIN aiwack_department_plans p ON p.id=s.plan_id
        WHERE s.task_id=?""",(task_id,)).fetchone()
    if step is None:
        return
    if step[0]!='approved':
        raise ValueError('소유자 승인 전 부서 협업 업무를 완료할 수 없습니다.')
    if not verified_collaboration_result(con, int(step[1]), task_id, int(step[2])):
        raise ValueError('부서 협업 완료에는 실제 직원 성공·결과물 승인·총괄 보고서 소유자 수락이 모두 필요합니다.')


def assert_collaboration_prerequisites(con, task_id: int) -> None:
    """실제 LocalStore.begin_task_execution의 BEGIN IMMEDIATE 안에서 모든 실행 경로 검증.

    GUI만 막으면 기존 '선택 업무 실행', 자동 대기열, 병렬 실행 경로로
    선행 업무를 건너뛸 수 있으므로 공통 SQLite 경계에서 확인한다.
    """
    assert_wide_prerequisites(con, task_id)
    if not con.execute("""SELECT 1 FROM sqlite_master WHERE type='table'
                          AND name='aiwack_department_plan_steps'""").fetchone():
        return
    row=con.execute("""SELECT plan_id,ordinal FROM aiwack_department_plan_steps
                       WHERE task_id=?""",(task_id,)).fetchone()
    if row is None:
        return
    plan_id,ordinal=row
    plan=con.execute('SELECT state FROM aiwack_department_plans WHERE id=?',
                     (plan_id,)).fetchone()
    if not plan or plan[0]!='approved':
        raise ValueError('소유자 승인 전 부서 협업 계획입니다.')
    if ordinal==1:
        return
    prior_steps=con.execute("""SELECT task_id,worker_employee_id,ordinal
        FROM aiwack_department_plan_steps WHERE plan_id=? AND ordinal<?
        ORDER BY ordinal""", (plan_id,ordinal)).fetchall()
    if len(prior_steps)!=ordinal-1:
        raise ValueError('선행 부서 단계가 누락되었습니다.')
    for prior_task,prior_worker,prior_ordinal in prior_steps:
        if prior_task is None or prior_worker is None:
            raise ValueError('선행 부서 업무·직원 연결이 없습니다.')
        status=con.execute('SELECT status FROM company_tasks WHERE id=?',
                           (prior_task,)).fetchone()
        if status is None or status[0]!='done':
            raise ValueError('선행 부서 업무가 아직 완료되지 않았습니다.')
        if not verified_collaboration_result(con, plan_id, prior_task, prior_worker):
            raise ValueError('선행 부서의 실제 직원 성공·소유자 승인 결과물·총괄 검토 기록이 필요합니다.')


def verified_wide_result(con, campaign_id: int, task_id: int, employee_id: int) -> bool:
    """Only an unaltered, owner-approved worker/chief result unlocks a step.

    This is also the shared task-finalization and dependency boundary. A status
    flag and matching foreign keys alone are insufficient after SQLite text
    tampering. Reuse the stricter campaign evidence check, including both
    content hashes, call-model identity, dispatch, owner review and run IDs.
    """
    from desktop.company_wide_campaign import _verified_step_evidence
    row=con.execute("""SELECT s.ordinal,c.chief_employee_id,s.task_id,s.employee_id,t.status
        FROM aiwack_wide_campaign_steps s
        JOIN company_tasks t ON t.id=s.task_id
        JOIN aiwack_wide_campaigns c ON c.id=s.campaign_id
        WHERE s.campaign_id=? AND s.task_id=? AND s.employee_id=?
          AND c.state='approved' """,
        (campaign_id,task_id,employee_id)).fetchone()
    if row is None or row[4] not in ('done','in_progress'):
        return False
    evidence=_verified_step_evidence(con,campaign_id,int(row[0]),
                                     expected_chief=int(row[1]),require_done=row[4]=='done')
    return bool(evidence and evidence['previous_task_id']==int(row[2]))


def assert_wide_prerequisites(con, task_id: int):
    """Shared BEGIN IMMEDIATE entrypoint, not merely an optional GUI warning."""
    if not con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='aiwack_wide_campaign_steps'").fetchone():
        return
    step=con.execute('SELECT campaign_id,ordinal FROM aiwack_wide_campaign_steps WHERE task_id=?',
                     (task_id,)).fetchone()
    if not step:return
    campaign_id,ordinal=step
    plan=con.execute('SELECT state FROM aiwack_wide_campaigns WHERE id=?',(campaign_id,)).fetchone()
    if not plan or plan[0]!='approved':raise ValueError('관리자 승인 전 31 AI 협업 실행 금지')
    previous=con.execute('''SELECT s.task_id,s.employee_id,t.status
        FROM aiwack_wide_campaign_steps s LEFT JOIN company_tasks t ON t.id=s.task_id
        WHERE s.campaign_id=? AND s.ordinal<? ORDER BY s.ordinal''',(campaign_id,ordinal)).fetchall()
    if len(previous)!=ordinal-1:raise ValueError('31 AI 협업 선행 단계가 누락됐습니다.')
    for prior_task,prior_employee,state in previous:
        if prior_task is None or state!='done' or not verified_wide_result(
                con,campaign_id,int(prior_task),int(prior_employee)):
            raise ValueError('선행 부서 직원·총괄 실행 및 관리자 수락 증거의 무결성이 확인되지 않았습니다.')


def assert_wide_completion(con, task_id: int):
    if not con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='aiwack_wide_campaign_steps'").fetchone():return
    step=con.execute('SELECT campaign_id,employee_id FROM aiwack_wide_campaign_steps WHERE task_id=?',
                     (task_id,)).fetchone()
    if not step:return
    if not verified_wide_result(con,int(step[0]),task_id,int(step[1])):
        raise ValueError('31 AI 협업 완료에는 실제 모델 성공·소유자 결과물 승인·총괄 검수 수락이 필요합니다.')
