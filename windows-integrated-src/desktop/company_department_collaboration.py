"""실제 총괄 AI의 부서별 계획 → 소유자 승인 → 순차 실제 직원 업무."""
from __future__ import annotations
import threading
from desktop.stage87_90_management import stopped


def _id(value):
    if type(value) is not int or value < 1:
        raise ValueError('업무/계획 번호가 올바르지 않습니다.')
    return value


def initialize(store):
    store.require_permission('company:manage')
    with store._connect() as con:
        con.execute("""CREATE TABLE IF NOT EXISTS aiwack_department_plans(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_task_id INTEGER NOT NULL REFERENCES company_tasks(id),
            source_fingerprint TEXT NOT NULL,
            chief_employee_id INTEGER NOT NULL REFERENCES ai_employee_profiles(id),
            state TEXT NOT NULL DEFAULT 'draft' CHECK(state IN ('draft','approved','rejected')),
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            approved_at TEXT)""")
        con.execute("""CREATE TABLE IF NOT EXISTS aiwack_department_plan_steps(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            plan_id INTEGER NOT NULL REFERENCES aiwack_department_plans(id),
            ordinal INTEGER NOT NULL CHECK(ordinal BETWEEN 1 AND 5),
            department_id INTEGER NOT NULL REFERENCES company_departments(id),
            title TEXT NOT NULL, instruction TEXT NOT NULL,
            task_id INTEGER UNIQUE REFERENCES company_tasks(id),
            worker_employee_id INTEGER REFERENCES ai_employee_profiles(id),
            UNIQUE(plan_id,ordinal))""")
        con.execute("""CREATE UNIQUE INDEX IF NOT EXISTS aiwack_department_active_source
            ON aiwack_department_plans(source_task_id)
            WHERE state IN ('draft','approved')""")


def parse_steps(raw, departments):
    if type(raw) is not str or not 1 <= len(raw.strip()) <= 4000 or '\x00' in raw:
        raise ValueError('총괄 AI 응답은 1~4000자여야 합니다.')
    names={str(d['name']).strip():int(d['id']) for d in departments}
    steps=[]
    for line in raw.splitlines():
        line=line.strip()
        if not line or line.startswith(chr(96)*3):
            continue
        if line.startswith('|') and line.endswith('|'):
            line=line[1:-1]
        parts=[p.strip() for p in line.split('|')]
        if len(parts)!=3:
            raise ValueError('각 단계는 부서명|업무 제목|직원 지시 3칸이어야 합니다.')
        dept,title,instruction=parts
        if dept not in names:
            raise ValueError('등록되지 않은 부서입니다: '+dept[:60])
        if not 1<=len(title)<=65 or not 1<=len(instruction)<=500 or '\x00' in title or '\x00' in instruction:
            raise ValueError('업무 제목은 1~65자, 지시는 1~500자여야 합니다.')
        steps.append((names[dept],title,instruction))
    if not 2<=len(steps)<=5 or len({x[0] for x in steps})<2:
        raise ValueError('서로 다른 부서 2곳 이상으로 구성한 2~5단계가 필요합니다.')
    return steps


def propose(store, source_task_id, *, cancel: threading.Event | None=None):
    from desktop import company_operations as ops
    from desktop.chief_runtime import invoke_chief_model
    store.require_permission('company:manage')
    store.require_permission('agents:manage')
    _id(source_task_id)
    ops.assert_running_allowed(store)
    if cancel is not None and cancel.is_set():
        raise InterruptedError('협업 제안 시작 전에 취소되었습니다.')
    initialize(store)
    source=store.read_task(source_task_id)
    if source['status']!='todo':
        raise ValueError('할 일 상태의 기준 업무만 협업 초안을 만들 수 있습니다.')
    chief=store.read_chief_profile()
    if not chief or chief['lifecycle']!='draft' or chief['model_id'] is None:
        raise ValueError('로컬 모델이 연결된 활성 총괄 AI가 필요합니다.')
    departments=store.list_departments()
    if len(departments)<2:
        raise ValueError('협업 가능한 부서 두 곳 이상이 필요합니다.')
    with store._connect() as con:
        if con.execute("""SELECT 1 FROM aiwack_department_plans
            WHERE source_task_id=? AND state IN ('draft','approved')""",(source_task_id,)).fetchone():
            raise ValueError('기존 협업 초안 또는 승인 계획이 있습니다.')
    fingerprint=store._chief_task_fingerprint(str(source['title']),str(source['description']))
    prompt=(
        '당신은 로컬 회사 총괄 AI입니다. 기준 업무를 2~5개 부서가 연속 수행할 '
        '구체적 작업 계획으로 분해하세요. 서로 다른 부서 2곳 이상 필수. '
        '각 줄은 부서명|업무 제목|직원 지시 세 칸만 출력하고 번호/설명/표는 쓰지 마세요. '
        '등록된 부서 이름만 그대로 사용하고 업무 제목 65자 이내, 지시 500자 이내. '
        '외부 거래·계약·결제·게시·도구 실행을 지시하지 마세요. '
        '소유자 확인·승인 전에는 어떤 직원도 실행하지 않습니다.\n'
        f"기준 업무: {str(source['title'])[:120]}\n"
        f"설명: {str(source['description'])[:450]}\n"
        '부서: '+', '.join(str(d['name']) for d in departments)[:650]
    )
    response=invoke_chief_model(store,prompt,timeout=90,cancel=cancel)
    steps=parse_steps(response,departments)
    if cancel is not None and cancel.is_set():
        raise InterruptedError('취소된 총괄 AI 초안은 저장하지 않습니다.')
    ops.assert_running_allowed(store)
    with store._connect() as con:
        con.execute('BEGIN IMMEDIATE')
        if stopped(con):
            raise PermissionError('비상 정지로 협업 초안 저장을 거부합니다.')
        fresh=store._task_row(con,source_task_id)
        if fresh[4]!='todo' or store._chief_task_fingerprint(str(fresh[2]),str(fresh[3]))!=fingerprint:
            raise ValueError('모델 응답 중 기준 업무가 변경되었습니다.')
        if con.execute("""SELECT 1 FROM aiwack_department_plans
            WHERE source_task_id=? AND state IN ('draft','approved')""",(source_task_id,)).fetchone():
            raise ValueError('다른 Windows 창에서 같은 업무의 협업 초안을 저장했습니다.')
        row=con.execute("""SELECT e.id,e.lifecycle,m.model_id FROM ai_reporting_lines r
            JOIN ai_employee_profiles e ON e.id=r.employee_id
            LEFT JOIN ai_employee_model_assignments m ON m.employee_id=e.id
            WHERE r.tier='ceo'""").fetchone()
        if not row or row[0]!=chief['employee_id'] or row[1]!='draft' or row[2] is None:
            raise ValueError('총괄 AI가 변경되어 초안을 저장할 수 없습니다.')
        pid=int(con.execute("""INSERT INTO aiwack_department_plans(
            source_task_id,source_fingerprint,chief_employee_id) VALUES(?,?,?)""",
            (source_task_id,fingerprint,chief['employee_id'])).lastrowid)
        for index,(department,title,instruction) in enumerate(steps,1):
            con.execute("""INSERT INTO aiwack_department_plan_steps(
                plan_id,ordinal,department_id,title,instruction) VALUES(?,?,?,?,?)""",
                (pid,index,department,title,instruction))
    return read_plan(store,pid)


def read_plan(store, plan_id):
    store.require_permission('company:manage')
    _id(plan_id)
    initialize(store)
    with store._connect() as con:
        row=con.execute("""SELECT p.id,p.source_task_id,p.state,p.created_at,p.approved_at,t.title
            FROM aiwack_department_plans p JOIN company_tasks t ON t.id=p.source_task_id
            WHERE p.id=?""",(plan_id,)).fetchone()
        if row is None:
            raise ValueError('협업 계획을 찾을 수 없습니다.')
        steps=con.execute("""SELECT s.ordinal,d.name,s.title,s.instruction,
            s.task_id,s.worker_employee_id,t.status FROM aiwack_department_plan_steps s
            JOIN company_departments d ON d.id=s.department_id
            LEFT JOIN company_tasks t ON t.id=s.task_id
            WHERE s.plan_id=? ORDER BY s.ordinal""",(plan_id,)).fetchall()
    return {'id':int(row[0]),'source_task_id':int(row[1]),'state':row[2],
            'created_at':row[3],'approved_at':row[4],'source_title':row[5],
            'steps':[dict(zip(('ordinal','department','title','instruction',
                'task_id','employee_id','task_status'),r)) for r in steps]}


def list_plans(store,limit=30):
    store.require_permission('company:manage')
    initialize(store)
    if type(limit) is not int or not 1<=limit<=100:
        raise ValueError('협업 계획은 1~100건 조회 가능합니다.')
    with store._connect() as con:
        ids=[int(r[0]) for r in con.execute(
            'SELECT id FROM aiwack_department_plans ORDER BY id DESC LIMIT ?',(limit,))]
    return [read_plan(store,i) for i in ids]


def approve(store,plan_id):
    """원자적 생성: 실제 직원·모델 검증, 승인 총괄 지시, 선행 업무 연결."""
    store.require_permission('company:manage')
    store.require_permission('agents:manage')
    _id(plan_id)
    initialize(store)
    with store._connect() as con:
        con.execute('BEGIN IMMEDIATE')
        if stopped(con):
            raise PermissionError('비상 정지 상태에서는 승인 불가합니다.')
        plan=con.execute("""SELECT source_task_id,source_fingerprint,chief_employee_id,state
            FROM aiwack_department_plans WHERE id=?""",(plan_id,)).fetchone()
        if not plan or plan[3]!='draft':
            raise ValueError('승인 가능한 협업 초안이 없습니다.')
        source_id,fingerprint,chief_id,_=plan
        source=store._task_row(con,source_id)
        if source[4]!='todo' or store._chief_task_fingerprint(str(source[2]),str(source[3]))!=fingerprint:
            raise ValueError('기준 업무가 변경돼 협업 초안을 다시 확인해야 합니다.')
        chief=con.execute("""SELECT e.id,e.lifecycle,m.model_id FROM ai_reporting_lines r
            JOIN ai_employee_profiles e ON e.id=r.employee_id
            LEFT JOIN ai_employee_model_assignments m ON m.employee_id=e.id
            WHERE r.tier='ceo'""").fetchone()
        if not chief or chief[0]!=chief_id or chief[1]!='draft' or chief[2] is None:
            raise ValueError('총괄 AI 또는 총괄 로컬 모델이 변경됐습니다.')
        steps=con.execute("""SELECT ordinal,department_id,title,instruction
            FROM aiwack_department_plan_steps WHERE plan_id=? ORDER BY ordinal""",(plan_id,)).fetchall()
        if not 2<=len(steps)<=5 or len({s[1] for s in steps})<2:
            raise ValueError('부서 협업 단계가 올바르지 않습니다.')
        assigned=[]
        for ordinal,department,title,instruction in steps:
            staff=con.execute("""SELECT e.id FROM ai_employee_profiles e
                JOIN ai_employee_model_assignments m ON m.employee_id=e.id
                LEFT JOIN ai_reporting_lines r ON r.employee_id=e.id
                WHERE e.lifecycle='draft' AND e.department_id=?
                  AND (r.tier IS NULL OR r.tier='staff')
                ORDER BY (SELECT COUNT(*) FROM company_task_assignments a
                  JOIN company_tasks t ON t.id=a.task_id WHERE a.employee_id=e.id
                  AND t.status NOT IN ('done','cancelled')),e.id LIMIT 1""",
                (department,)).fetchone()
            if staff is None:
                raise ValueError(f'협업 {ordinal}단계 부서에 실제 로컬 모델 연결 직원이 없습니다.')
            assigned.append(int(staff[0]))
        previous=None
        for (ordinal,department,title,instruction),worker in zip(steps,assigned):
            department_row=con.execute('SELECT name FROM company_departments WHERE id=?',
                                       (department,)).fetchone()
            if not department_row:
                raise ValueError('협업 부서가 삭제되었습니다.')
            task_title=f'{department_row[0]} | {title}'
            task_desc=(f'소유자 승인 협업 계획 #{plan_id} / 기준 업무 #{source_id} / '
                       f'{ordinal}/{len(steps)}단계\n{instruction}')
            if len(task_title)>120 or len(task_desc)>1500:
                raise ValueError('협업 업무 제목 또는 설명이 저장 한도를 넘었습니다.')
            tid=int(con.execute('INSERT INTO company_tasks(title,description) VALUES(?,?)',
                                (task_title,task_desc)).lastrowid)
            con.execute("""INSERT INTO company_task_status_events(task_id,old_status,new_status)
                VALUES(?,NULL,'todo')""",(tid,))
            con.execute('INSERT INTO company_task_routing(task_id,department_id) VALUES(?,?)',
                        (tid,department))
            con.execute("""INSERT INTO company_task_assignments(task_id,employee_id,reason)
                VALUES(?,?,?)""",(tid,worker,'소유자 승인 부서 협업 계획'))
            con.execute("""INSERT INTO company_task_assignment_events(
                task_id,employee_id,action,detail) VALUES(?,?,'auto_assigned',?)""",
                (tid,worker,f'소유자 승인 협업 계획 #{plan_id} 부서 직원 배정'))
            con.execute("""INSERT INTO company_chief_task_orders(
                task_id,chief_employee_id,worker_employee_id,instruction,task_fingerprint)
                VALUES(?,?,?,?,?)""",(tid,chief_id,worker,instruction,
                store._chief_task_fingerprint(task_title,task_desc)))
            if previous is not None:
                con.execute("""INSERT INTO company_task_dependencies(task_id,prerequisite_id)
                    VALUES(?,?)""",(tid,previous))
                con.execute("""INSERT INTO company_task_dependency_events(
                    task_id,prerequisite_id,action) VALUES(?,?,'added')""",(tid,previous))
            con.execute("""UPDATE aiwack_department_plan_steps
                SET task_id=?,worker_employee_id=? WHERE plan_id=? AND ordinal=?""",
                (tid,worker,plan_id,ordinal))
            previous=tid
        con.execute("""UPDATE aiwack_department_plans
            SET state='approved',approved_at=CURRENT_TIMESTAMP
            WHERE id=? AND state='draft'""",(plan_id,))
    return read_plan(store,plan_id)


def reject(store,plan_id):
    store.require_permission('company:manage')
    _id(plan_id)
    initialize(store)
    with store._connect() as con:
        con.execute('BEGIN IMMEDIATE')
        updated=con.execute("""UPDATE aiwack_department_plans SET state='rejected'
            WHERE id=? AND state='draft'""",(plan_id,)).rowcount
        if updated!=1:
            raise ValueError('기각 가능한 협업 초안이 없습니다.')
    return read_plan(store,plan_id)


def report_text(plan):
    lines=[f"협업 계획 #{plan['id']} / 기준 업무 #{plan['source_task_id']}: {plan['source_title']}",
           f"상태: {plan['state']} / 소유자 승인 전에는 실행되지 않습니다."]
    for s in plan['steps']:
        lines.append(f"{s['ordinal']}단계 [{s['department']}] {s['title']}\n"
                     f"  지시: {s['instruction']}\n"
                     f"  직원 #{s['employee_id'] or '-'} / 업무 #{s['task_id'] or '-'}"
                     f" / 상태 {s['task_status'] or '미승인'}")
    lines.append('앞 단계 결과를 소유자가 승인·완료한 뒤에만 후속 직원 실행 가능. '
                 '외부 결제·게시·거래 없음.')
    return '\n'.join(lines)
