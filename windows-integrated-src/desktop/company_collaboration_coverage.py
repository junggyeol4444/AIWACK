"""Evidence-only T05/T14/T19 participation coverage for the existing native GUI.

Count DISTINCT employees, never treat task count, draft profiles, model binding,
or a mocked finance record as proof of 31 live collaborating agents.
"""
from __future__ import annotations


def snapshot(store) -> dict:
    store.require_permission('company:manage')
    from desktop.company_department_collaboration import initialize
    initialize(store)
    with store._connect() as con:
        total_employees = int(con.execute(
            'SELECT COUNT(*) FROM ai_employee_profiles').fetchone()[0])
        bound_employees = int(con.execute(
            'SELECT COUNT(DISTINCT employee_id) FROM ai_employee_model_assignments').fetchone()[0])
        plans=con.execute('''SELECT id,chief_employee_id FROM aiwack_department_plans
            WHERE state='approved' ORDER BY id''').fetchall()
        steps=con.execute('''SELECT p.id,s.ordinal,s.department_id,s.task_id,
            s.worker_employee_id,t.status
            FROM aiwack_department_plans p
            JOIN aiwack_department_plan_steps s ON s.plan_id=p.id
            LEFT JOIN company_tasks t ON t.id=s.task_id
            WHERE p.state='approved' ORDER BY p.id,s.ordinal''').fetchall()
        # 감사와 승인 결과를 같은 지시/직원/모델 호출에 결속한다.
        # 단순 성공 업무 건수 또는 다른 총괄의 보고서로 참여자를 부풀리지 않는다.
        evidence=con.execute('''SELECT s.plan_id,s.task_id,s.worker_employee_id,
            r.id,r.status,a.id,a.review_status,c.id,c.owner_decision,c.chief_employee_id,
            h.status,o.chief_employee_id
            FROM aiwack_department_plan_steps s
            JOIN aiwack_department_plans p ON p.id=s.plan_id AND p.state='approved'
            JOIN company_task_runs r ON r.task_id=s.task_id
                AND r.employee_id=s.worker_employee_id
            JOIN ai_model_call_history h ON h.id=r.model_call_id
                AND h.employee_id=r.employee_id
            LEFT JOIN company_task_artifacts a ON a.run_id=r.id AND a.task_id=r.task_id
            LEFT JOIN company_chief_task_dispatches d ON d.run_id=r.id
            LEFT JOIN company_chief_task_orders o ON o.id=d.order_id
                AND o.task_id=r.task_id AND o.worker_employee_id=r.employee_id
                AND o.chief_employee_id=p.chief_employee_id
            LEFT JOIN company_chief_task_reports c ON c.artifact_id=a.id
                AND c.order_id=o.id AND c.chief_employee_id=p.chief_employee_id
            ORDER BY s.plan_id,s.ordinal,r.id''').fetchall()
    by_step={}
    successful_staff=set()
    accepted_staff=set()
    verified_staff_roles=set()
    accepted_chiefs=set()
    for plan_id,task_id,worker_id,run_id,run_status,artifact_id,review_status,report_id,decision,report_chief,model_status,order_chief in evidence:
        if run_status != 'success' or model_status != 'success' or order_chief is None:
            continue
        key=(int(plan_id),int(task_id),int(worker_id))
        successful_staff.add(int(worker_id))
        by_step.setdefault(key,{'worker_success':False,'owner_accepted':False})['worker_success']=True
        if (artifact_id is not None and review_status=='approved'
                and report_id is not None and decision=='accepted'
                and order_chief is not None
                and int(report_chief)==dict(plans)[int(plan_id)]):
            accepted_staff.add(int(worker_id))
            # 동일 AI가 다른 계획의 총괄도 맡았다는 이유로 이 계획의 직원 증거를 삭제하지 않는다.
            if int(worker_id) != int(dict(plans)[int(plan_id)]):
                verified_staff_roles.add(int(worker_id))
            by_step[key]['owner_accepted']=True
    per_plan=[]
    accepted_departments=set()
    for pid,chief in plans:
        pid=int(pid)
        selected=[row for row in steps if int(row[0])==pid]
        approved_steps=0
        plan_staff=set()
        for _,ordinal,dept,task,worker,status in selected:
            if task is None or worker is None:
                continue
            key=(pid,int(task),int(worker))
            if by_step.get(key,{}).get('owner_accepted'):
                approved_steps+=1
                plan_staff.add(int(worker))
                accepted_departments.add(int(dept))
                accepted_chiefs.add(int(chief))
        per_plan.append(dict(plan_id=pid,steps=len(selected),
                             verified_steps=approved_steps,
                             distinct_verified_workers=len(plan_staff),
                             fully_reviewed=bool(selected) and approved_steps==len(selected)))
    participants=accepted_staff|accepted_chiefs
    # An accepted chief report is evidence of a review, not a claim that the
    # employee and chief ran concurrently or that a real external sale occurred.
    return dict(employee_profiles=total_employees,model_bound_employees=bound_employees,
                approved_plans=len(plans),approved_plan_steps=len(steps),
                observed_successful_workers=len(successful_staff),
                verified_owner_accepted_workers=len(accepted_staff),
                verified_chief_reviewers=len(accepted_chiefs),
                distinct_verified_participants=len(participants),
                distinct_verified_departments=len(accepted_departments),
                full_31_participation_verified=(total_employees>=31 and len(participants)>=31),
                plans=per_plan,real_sales_verified=False,
                source='SQLite worker/model audits, approved order dispatches, owner reviews, accepted chief reports')


def text_report(store) -> str:
    data=snapshot(store)
    lines=['[부서 협업 실제 참여 감사 — 업무 건수와 직원 수 분리]',
        f"등록 직원 {data['employee_profiles']}명 / 모델 연결 {data['model_bound_employees']}명",
        f"승인 협업 계획 {data['approved_plans']}개 / 단계 {data['approved_plan_steps']}건",
        f"성공 실행 직원(중복 제외) {data['observed_successful_workers']}명",
        f"직원 결과물+소유자 승인+총괄 수락 직원 {data['verified_owner_accepted_workers']}명",
        f"수락된 총괄 검토자 {data['verified_chief_reviewers']}명",
        f"실제 승인 근거가 연결된 서로 다른 AI 참여자 {data['distinct_verified_participants']}명",
        f"검증된 부서 {data['distinct_verified_departments']}곳",
        '31명 전원 협업 최종 실증: '+('증거 충족(실 GGUF/Windows 별도 검증 필요)' if data['full_31_participation_verified'] else '미완료')]
    for plan in data['plans'][-15:]:
        lines.append(f"계획 #{plan['plan_id']}: 승인 실증 {plan['verified_steps']}/{plan['steps']}단계, "
                     f"서로 다른 직원 {plan['distinct_verified_workers']}명")
    lines.append('주의: SQLite 감사는 실제 Windows EXE·GGUF·24시간 운영 및 실매출 최종 증명이 아닙니다.')
    return '\n'.join(lines)
