"""Stages 81-83: descriptive local company counts, offline alerts, DRAFT recommendations.

No model execution, actual sales trends, hiring, spending, or automatic task creation.
All financial figures are synthetic assumptions from Stage79 only.
"""
from __future__ import annotations
import sqlite3
from desktop.local_commerce_common import digest,key,note,ident,triggers
from desktop.local_budget_scenarios import calculate as budget_calculate

RULES={
 'BLOCKED_TASK':('검토 필요: 차단된 로컬 업무', '담당자와 차단 원인을 확인하고 관리자 승인 후 별도 업무를 수동 계획하세요.'),
 'FAILED_QUEUE':('검토 필요: 실패 상태의 로컬 대기열','재실행 전에 실패 이력과 외부 부작용 가능성을 관리자에게 확인받으세요.'),
 'HYPOTHETICAL_BUDGET_OVERRUN':('검토 필요: 가정 지출이 가정 예산 초과','실제 매출·지출 증빙이 아니므로 예산 가정과 기록을 확인하세요.'),
 'VERIFIED_REVENUE_MISSING':('실제 매출·정산 증빙 없음','실제 결제/정산 증빙을 확인할 수 있을 때까지 매출 하락 판정을 보류하세요.'),
}

def initialize(con):
    con.execute('''CREATE TABLE IF NOT EXISTS local_diagnostic_improvement_drafts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        proposal_key TEXT NOT NULL UNIQUE,
        diagnostic_key TEXT NOT NULL,
        diagnostic_digest TEXT NOT NULL,
        title TEXT NOT NULL,
        proposed_action TEXT NOT NULL,
        owner_note TEXT NOT NULL,
        previous_digest TEXT NOT NULL,
        digest TEXT NOT NULL,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    )''')
    triggers(con,('local_diagnostic_improvement_drafts',))

def performance(con):
    """Counts describe local records, NOT quality/scoring or live performance."""
    from desktop.performance_reviews import task_summary
    departments=[]
    for did,name in con.execute('SELECT id,name FROM company_departments ORDER BY id'):
        totals=dict(con.execute('SELECT lifecycle,COUNT(*) FROM ai_employee_profiles WHERE department_id=? GROUP BY lifecycle',(did,)))
        status=dict(con.execute('''SELECT t.status,COUNT(*) FROM company_tasks t
              JOIN company_task_assignments a ON a.task_id=t.id
              JOIN ai_employee_profiles e ON e.id=a.employee_id
              WHERE e.department_id=? GROUP BY t.status''',(did,)))
        departments.append({'id':did,'name':name,'employee_draft_count':totals.get('draft',0),
                            'employee_inactive_count':totals.get('inactive',0),
                            'assigned_task_status_counts':status,'quality_verified':False})
    employees=[]
    for emp_id,label,lifecycle in con.execute('SELECT id,display_name,lifecycle FROM ai_employee_profiles ORDER BY id'):
        task_status=dict(con.execute('''SELECT t.status,COUNT(*) FROM company_tasks t
             JOIN company_task_assignments a ON a.task_id=t.id
             WHERE a.employee_id=? GROUP BY t.status''',(emp_id,)))
        employees.append({'id':emp_id,'label':label,'lifecycle':lifecycle,'assigned_task_status_counts':task_status,'model_performance_verified':False})
    businesses=[]
    for bid,name,state,budget in con.execute('SELECT id,name,state,budget_krw FROM managed_businesses ORDER BY id'):
        states=dict(con.execute('SELECT state,COUNT(*) FROM managed_business_projects WHERE business_id=? GROUP BY state',(bid,)))
        businesses.append({'id':bid,'name':name,'state':state,'declared_budget_krw':budget,
                           'project_state_counts':states,'real_profit_verified':False})
    return {'departments':departments,'employees':employees,'businesses':businesses,
            'tasks':task_summary(con),'assumed_budget':budget_calculate(con),
            'actual_sales_data_available':False,'actual_staff_quality_verified':False,
            'real_customer_performance_verified':False,'read_only_descriptive':True}

def diagnostics(con):
    """Deterministic read-only local indicators; real sales decline is UNDETERMINED."""
    data=performance(con)
    out=[]
    for taskid in (r[0] for r in con.execute("SELECT id FROM company_tasks WHERE status='blocked' ORDER BY id")):
        out.append({'key':f'BLOCKED_TASK:{taskid}','kind':'BLOCKED_TASK','source_id':taskid,'severity':'REVIEW_LOCAL','verified_external_problem':False})
    for qid in (r[0] for r in con.execute("SELECT id FROM local_task_queue WHERE state='failed' ORDER BY id")):
        out.append({'key':f'FAILED_QUEUE:{qid}','kind':'FAILED_QUEUE','source_id':qid,'severity':'REVIEW_LOCAL','verified_external_problem':False})
    for business in data['assumed_budget']['businesses']:
        if business['assumed_expenses_krw']>business['budget_krw']:
            out.append({'key':f'HYPOTHETICAL_BUDGET_OVERRUN:{business["business_id"]}',
                        'kind':'HYPOTHETICAL_BUDGET_OVERRUN','source_id':business['business_id'],
                        'severity':'ASSUMPTION_ONLY','verified_external_problem':False})
    out.append({'key':'VERIFIED_REVENUE_MISSING:0','kind':'VERIFIED_REVENUE_MISSING',
                'source_id':0,'severity':'NO_EVIDENCE','verified_external_problem':False})
    return {'indicators':out,'live_revenue_decline':'NOT_EVALUABLE_NO_VERIFIED_SALES',
            'real_operational_problem_detected':False,'simulated_budget_only':True,
            'autonomous_improvement_executed':False}

def history(con):
    con.row_factory=sqlite3.Row
    prev='';result=[]
    for row in con.execute('SELECT * FROM local_diagnostic_improvement_drafts ORDER BY id'):
        e=dict(row)
        expected=digest([e['proposal_key'],e['diagnostic_key'],e['diagnostic_digest'],e['title'],e['proposed_action'],e['owner_note'],prev])
        if expected!=e['digest'] or e['previous_digest']!=prev:
            raise ValueError('improvement draft audit hash chain mismatch')
        key(e['proposal_key']);note(e['owner_note']);
        if e['diagnostic_key'].split(':',1)[0] not in RULES:raise ValueError('unknown diagnostic type')
        result.append({**e,'not_an_executed_task':True,'owner_approval_not_given':True})
        prev=e['digest']
    return result

def propose(con,diagnostic_key,proposal_key,owner_note):
    key(proposal_key);note(owner_note)
    found={x['key']:x for x in diagnostics(con)['indicators']}
    if diagnostic_key not in found:raise ValueError('diagnostic no longer present; no task generated')
    diagnostic=found[diagnostic_key]
    fingerprint=digest(diagnostic)
    title,action=RULES[diagnostic['kind']]
    existing=history(con)
    for e in existing:
        if e['proposal_key']==proposal_key:
            if (e['diagnostic_key'],e['diagnostic_digest'],e['owner_note']) != (diagnostic_key,fingerprint,owner_note):
                raise ValueError('improvement draft key conflict')
            return {**e,'duplicate':True}
    prev=existing[-1]['digest'] if existing else ''
    hashed=digest([proposal_key,diagnostic_key,fingerprint,title,action,owner_note,prev])
    cur=con.execute('''INSERT INTO local_diagnostic_improvement_drafts
       (proposal_key,diagnostic_key,diagnostic_digest,title,proposed_action,owner_note,previous_digest,digest)
       VALUES(?,?,?,?,?,?,?,?)''',(proposal_key,diagnostic_key,fingerprint,title,action,owner_note,prev,hashed))
    return {**[x for x in history(con) if x['id']==cur.lastrowid][0],'duplicate':False}
