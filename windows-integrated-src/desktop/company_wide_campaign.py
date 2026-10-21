"""기존 15부서·31 AI: 실제 총괄 모델 5회 초안 → 관리자가 승인한 30개 직원 업무.

각 부서장/담당 직원의 실제 모델은 기존 승인 업무 실행 경로로 실행된다.
수기 승인·총괄 검수·의존성·비상정지·권한은 우회하지 않는다.
"""
from __future__ import annotations

import hashlib
import sqlite3
import threading
from desktop.company_operations import BLUEPRINT_DEPARTMENTS, assert_running_allowed
from desktop.employee_model_runtime import invoke_employee_model
from desktop.stage87_90_management import stopped


def initialize(con):
    con.execute('''CREATE TABLE IF NOT EXISTS aiwack_wide_campaigns (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        source_task_id INTEGER NOT NULL REFERENCES company_tasks(id),
        source_fingerprint TEXT NOT NULL,
        chief_employee_id INTEGER NOT NULL REFERENCES ai_employee_profiles(id),
        state TEXT NOT NULL DEFAULT 'draft' CHECK(state IN ('draft','approved','rejected')),
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        approved_at TEXT)''')
    con.execute('''CREATE UNIQUE INDEX IF NOT EXISTS aiwack_wide_active_source
        ON aiwack_wide_campaigns(source_task_id) WHERE state IN ('draft','approved')''')
    con.execute('''CREATE TABLE IF NOT EXISTS aiwack_wide_campaign_steps (
        campaign_id INTEGER NOT NULL REFERENCES aiwack_wide_campaigns(id),
        ordinal INTEGER NOT NULL CHECK(ordinal BETWEEN 1 AND 30),
        department_id INTEGER NOT NULL REFERENCES company_departments(id),
        employee_id INTEGER NOT NULL REFERENCES ai_employee_profiles(id),
        role TEXT NOT NULL CHECK(role IN ('department_head','staff')),
        title TEXT NOT NULL, instruction TEXT NOT NULL,
        chief_model_call_id INTEGER NOT NULL REFERENCES ai_model_call_history(id),
        task_id INTEGER UNIQUE REFERENCES company_tasks(id),
        PRIMARY KEY(campaign_id,ordinal),
        UNIQUE(campaign_id,employee_id))''')
    for action in ('UPDATE','DELETE'):
        con.execute(f'''CREATE TRIGGER IF NOT EXISTS aiwack_wide_campaign_step_no_{action.lower()}
            BEFORE {action} ON aiwack_wide_campaign_steps
            WHEN {"OLD.task_id IS NOT NULL" if action == 'UPDATE' else '1'}
            BEGIN SELECT RAISE(ABORT,'승인 후 회사 전체 협업 증빙을 수정·삭제할 수 없습니다'); END''')


def _source(store, con, source_task_id):
    row=store._task_row(con,source_task_id)
    if row[4]!='todo':
        raise ValueError('할 일 상태 기준 업무만 회사 전체 협업으로 확장할 수 있습니다.')
    return store._chief_task_fingerprint(str(row[2]),str(row[3])),row


def _staff_roster(con):
    chief=con.execute('''SELECT e.id,m.model_id FROM ai_reporting_lines r
       JOIN ai_employee_profiles e ON e.id=r.employee_id
       LEFT JOIN ai_employee_model_assignments m ON m.employee_id=e.id
       WHERE r.tier='ceo' AND e.lifecycle='draft' ''').fetchall()
    if len(chief)!=1 or chief[0][1] is None:
        raise ValueError('실제 로컬 모델이 연결된 활성 총괄 AI 한 명이 필요합니다.')
    groups=[]; used={int(chief[0][0])}
    for name,_ in BLUEPRINT_DEPARTMENTS:
        dept=con.execute('SELECT id FROM company_departments WHERE name=?',(name,)).fetchone()
        if not dept:
            raise ValueError('원본 15개 부서 중 누락된 부서: '+name)
        rows=con.execute('''SELECT e.id,r.tier FROM ai_reporting_lines r
            JOIN ai_employee_profiles e ON e.id=r.employee_id
            JOIN ai_employee_model_assignments m ON m.employee_id=e.id
            WHERE e.department_id=? AND e.lifecycle='draft'
                AND r.tier IN ('department_head','staff') ORDER BY r.tier''',(dept[0],)).fetchall()
        if len(rows)!=2 or {r[1] for r in rows}!={'department_head','staff'}:
            raise ValueError('해당 부서의 부서장·직원 각각 한 명과 실제 로컬 모델 배정 필요: '+name)
        members={role:int(employee) for employee,role in rows}
        if any(e in used for e in members.values()):
            raise ValueError('같은 직원이 서로 다른 부서에 중복 지정됐습니다.')
        used.update(members.values())
        groups.append((int(dept[0]),name,members['department_head'],members['staff']))
    if len(used)!=31:
        raise ValueError('총괄 1명과 15개 부서별 부서장·직원 총 31명 필요')
    return int(chief[0][0]),int(chief[0][1]),groups


def _parse_group(raw,expected):
    if type(raw) is not str or not 10<=len(raw)<=3500:
        raise ValueError('총괄 모델의 3개 부서 작업 제안이 누락됐습니다.')
    mapping={name:(dept,manager,worker) for dept,name,manager,worker in expected}
    plans={}
    for line in raw.strip().splitlines():
        line=line.strip().strip('|').strip()
        if not line or line.startswith('```'):
            continue
        parts=[x.strip() for x in line.split('|')]
        if len(parts)!=3 or parts[0] not in mapping or parts[0] in plans:
            raise ValueError('총괄은 지정한 부서마다 부서명|업무 제목|지시 정확히 한 줄씩 작성해야 합니다.')
        _,title,instruction=parts
        if not 1<=len(title)<=65 or not 1<=len(instruction)<=330 or '\x00' in line:
            raise ValueError('총괄의 부서 지시 길이·내용 오류')
        plans[parts[0]]=(title,instruction)
    if set(plans)!=set(mapping):
        raise ValueError('총괄이 필수 3개 부서 중 일부를 누락했습니다.')
    return plans


def propose(store,source_task_id:int,*,cancel:threading.Event|None=None):
    """Five REAL chief calls; create 30 drafts only after all five succeed."""
    store.require_permission('company:manage');store.require_permission('agents:manage')
    if type(source_task_id) is not int or source_task_id<=0:
        raise ValueError('기준 업무 번호 오류')
    assert_running_allowed(store)
    with store._connect() as con:
        initialize(con)
        fingerprint,task=_source(store,con,source_task_id)
        chief,chief_model,groups=_staff_roster(con)
        if con.execute('''SELECT 1 FROM aiwack_wide_campaigns
            WHERE source_task_id=? AND state IN ('draft','approved')''',(source_task_id,)).fetchone():
            raise ValueError('이미 진행 중인 회사 전체 협업이 있습니다.')
    steps=[]
    for start in range(0,15,3):
        if cancel is not None and cancel.is_set():
            raise InterruptedError('총괄 일괄 협업 초안 취소')
        assert_running_allowed(store)
        part=groups[start:start+3]
        prompt=('당신은 기존 Windows 로컬 회사의 총괄 AI입니다. 실제 작업을 수행할 3개 부서를 위한 '
                '명확한 텍스트 작업 지시를 각 부서별로 한 줄 작성하세요. 입력된 부서 이름을 그대로 사용하고 '
                '부서명|작업 제목|작업 지시 형태의 3줄만 출력하세요. 다른 부서/외부 결제/계약/게시 지시 금지. '
                '관리자 승인 전에는 실행되지 않습니다.\n'
                f'원본 업무: {str(task[2])[:120]} / {str(task[3])[:400]}\n'
                '담당 부서: '+', '.join(name for _,name,_,_ in part))
        raw,call_id=invoke_employee_model(store,chief,prompt,timeout=90,cancel=cancel,
                                          required_tier='ceo',include_call_id=True)
        if cancel is not None and cancel.is_set():
            raise InterruptedError('총괄 모델 호출 후 관리자 취소로 초안을 폐기합니다.')
        parsed=_parse_group(raw,part)
        for dept,name,manager,staff in part:
            title,instruction=parsed[name]
            steps.append((dept,manager,'department_head',f'{name} 부서장 검토: {title}',
                          ('부서장 분석·계획: '+instruction)[:500],int(call_id)))
            steps.append((dept,staff,'staff',f'{name} 담당 실행: {title}',
                          ('부서장 승인된 선행 업무를 확인하고 실제 결과물을 작성: '+instruction)[:500],int(call_id)))
    if cancel is not None and cancel.is_set():raise InterruptedError('취소된 계획 저장 불가')
    store.require_permission('company:manage');store.require_permission('agents:manage')
    with store._connect() as con:
        con.execute('BEGIN IMMEDIATE');initialize(con)
        if stopped(con):raise PermissionError('비상정지로 회사 전체 협업 초안 거부')
        fp,_=_source(store,con,source_task_id)
        current,model,current_groups=_staff_roster(con)
        if fp!=fingerprint or current!=chief or model!=chief_model or current_groups!=groups:
            raise ValueError('모델 실행 중 회사 조직/기준 업무가 변경됐습니다.')
        if con.execute('''SELECT 1 FROM aiwack_wide_campaigns WHERE source_task_id=?
             AND state IN ('draft','approved')''',(source_task_id,)).fetchone():
            raise ValueError('다른 Windows 창에 이미 승인 대기 계획이 있습니다.')
        ids={int(x[0]) for x in con.execute('''SELECT id FROM ai_model_call_history
            WHERE employee_id=? AND model_id=? AND status='success' AND output_chars>0''',
            (chief,chief_model))}
        if not all(call in ids for *_,call in steps):
            raise ValueError('동일 총괄 AI의 성공한 실제 로컬 모델 호출 감사가 필요합니다.')
        cid=int(con.execute('''INSERT INTO aiwack_wide_campaigns
            (source_task_id,source_fingerprint,chief_employee_id) VALUES(?,?,?)''',
            (source_task_id,fingerprint,chief)).lastrowid)
        for ordinal,(dept,employee,role,title,instruction,call) in enumerate(steps,1):
            con.execute('''INSERT INTO aiwack_wide_campaign_steps
                (campaign_id,ordinal,department_id,employee_id,role,title,instruction,chief_model_call_id)
                VALUES(?,?,?,?,?,?,?,?)''',(cid,ordinal,dept,employee,role,title,instruction,call))
    return read(store,cid)


def read(store,campaign_id:int):
    store.require_permission('company:manage')
    if type(campaign_id) is not int or campaign_id<=0:raise ValueError('회사 전체 협업 번호 오류')
    with store._connect() as con:
        initialize(con)
        row=con.execute('''SELECT id,source_task_id,state,chief_employee_id
            FROM aiwack_wide_campaigns WHERE id=?''',(campaign_id,)).fetchone()
        if not row:raise ValueError('회사 전체 협업 계획 없음')
        steps=con.execute('''SELECT s.ordinal,d.name,s.employee_id,s.role,s.title,s.task_id,
            t.status,s.chief_model_call_id FROM aiwack_wide_campaign_steps s
            JOIN company_departments d ON d.id=s.department_id
            LEFT JOIN company_tasks t ON t.id=s.task_id
            WHERE s.campaign_id=? ORDER BY s.ordinal''',(campaign_id,)).fetchall()
    return {'id':int(row[0]),'source_task_id':int(row[1]),'state':row[2],
            'chief_employee_id':int(row[3]),'distinct_departments':len({s[1] for s in steps}),
            'distinct_worker_roles':len({s[2] for s in steps}),
            'steps':[dict(zip(('ordinal','department','employee_id','role','title','task_id',
                              'task_status','chief_model_call_id'),x)) for x in steps]}


def approve(store,campaign_id:int):
    """Owner-clicked single SQLite transaction creates 30 REAL reviewed-order tasks."""
    store.require_permission('company:manage');store.require_permission('agents:manage')
    if type(campaign_id) is not int or campaign_id<=0:raise ValueError('계획 번호 오류')
    with store._connect() as con:
        con.execute('BEGIN IMMEDIATE');initialize(con)
        if stopped(con):raise PermissionError('비상정지로 계획 승인을 차단했습니다.')
        plan=con.execute('''SELECT source_task_id,source_fingerprint,chief_employee_id,state
            FROM aiwack_wide_campaigns WHERE id=?''',(campaign_id,)).fetchone()
        if not plan or plan[3]!='draft':raise ValueError('승인할 수 있는 초안이 없습니다.')
        fingerprint,_=_source(store,con,plan[0]);chief,_,groups=_staff_roster(con)
        if fingerprint!=plan[1] or chief!=plan[2]:raise ValueError('총괄/업무가 변경됐습니다.')
        steps=con.execute('''SELECT ordinal,department_id,employee_id,role,title,instruction
            FROM aiwack_wide_campaign_steps WHERE campaign_id=? ORDER BY ordinal''',
            (campaign_id,)).fetchall()
        expected=[(dept,e,role) for dept,name,manager,staff in groups
                  for e,role in ((manager,'department_head'),(staff,'staff'))]
        if len(steps)!=30 or [(s[1],s[2],s[3]) for s in steps]!=expected:
            raise ValueError('15부서 30역할의 실제 계획이 일치하지 않습니다.')
        prev=None
        for ordinal,dept,employee,role,title,instruction in steps:
            description=f'관리자 승인 회사 전체 협업 #{campaign_id} / {ordinal}/30단계\n{instruction}'
            tid=int(con.execute('INSERT INTO company_tasks(title,description) VALUES(?,?)',
                                (title[:120],description[:1500])).lastrowid)
            con.execute('''INSERT INTO company_task_status_events(task_id,old_status,new_status)
                VALUES(?,NULL,'todo')''',(tid,))
            con.execute('INSERT INTO company_task_routing(task_id,department_id) VALUES(?,?)',(tid,dept))
            con.execute('''INSERT INTO company_task_assignments(task_id,employee_id,reason)
                VALUES(?,?,?)''',(tid,employee,'소유자 승인 회사 전체 협업 계획'))
            con.execute('''INSERT INTO company_task_assignment_events
                (task_id,employee_id,action,detail) VALUES(?,?,'auto_assigned',?)''',
                (tid,employee,f'회사 전체 협업 #{campaign_id} 역할 {role}'))
            con.execute('''INSERT INTO company_chief_task_orders
                (task_id,chief_employee_id,worker_employee_id,instruction,task_fingerprint)
                VALUES(?,?,?,?,?)''',(tid,chief,employee,instruction,
                store._chief_task_fingerprint(title[:120],description[:1500])))
            if prev is not None:
                con.execute('''INSERT INTO company_task_dependencies(task_id,prerequisite_id)
                    VALUES(?,?)''',(tid,prev))
                con.execute('''INSERT INTO company_task_dependency_events
                    (task_id,prerequisite_id,action) VALUES(?,?,'added')''',(tid,prev))
            con.execute('''UPDATE aiwack_wide_campaign_steps SET task_id=?
                WHERE campaign_id=? AND ordinal=? AND task_id IS NULL''',(tid,campaign_id,ordinal))
            prev=tid
        changed=con.execute('''UPDATE aiwack_wide_campaigns
            SET state='approved',approved_at=CURRENT_TIMESTAMP WHERE id=? AND state='draft' ''',
            (campaign_id,))
        if changed.rowcount!=1:raise RuntimeError('기존 계획이 변경됐습니다.')
    return read(store,campaign_id)


def run_next(store,campaign_id:int,*,cancel:threading.Event|None=None):
    """One approved employee model and chief review; owner must review both separately."""
    from desktop.company_operations import execute_approved_chief_cycle
    plan=read(store,campaign_id)
    if plan['state']!='approved':raise ValueError('승인된 계획만 실행할 수 있습니다.')
    pending=[s for s in plan['steps'] if s['task_status']!='done']
    if not pending:return {'completed':True,'remaining':0}
    step=pending[0]
    result=execute_approved_chief_cycle(store,step['task_id'],cancel=cancel)
    return {'step':step['ordinal'],'department':step['department'],
            'employee_id':step['employee_id'],'work':result,
            'remaining':len(pending),'owner_review_required':True}
