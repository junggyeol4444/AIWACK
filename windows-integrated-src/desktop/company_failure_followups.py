"""실제 실패한 직원 모델 업무를 분석·보완 작업으로 연결한다. 관리자 승인 전 실행 금지."""
from __future__ import annotations
from desktop.stage87_90_management import stopped

def initialize(con):
    con.execute("""CREATE TABLE IF NOT EXISTS aiwack_failed_work_followups(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        source_run_id INTEGER NOT NULL UNIQUE REFERENCES company_task_runs(id),
        task_id INTEGER NOT NULL REFERENCES company_tasks(id),
        employee_id INTEGER NOT NULL REFERENCES ai_employee_profiles(id),
        failure_status TEXT NOT NULL,
        state TEXT NOT NULL DEFAULT 'pending' CHECK(state IN ('pending','approved','rejected')),
        followup_task_id INTEGER UNIQUE REFERENCES company_tasks(id),
        owner_note TEXT NOT NULL DEFAULT '',
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, decided_at TEXT)""")
    con.execute("""CREATE TRIGGER IF NOT EXISTS aiwack_failed_followup_no_delete
        BEFORE DELETE ON aiwack_failed_work_followups BEGIN
        SELECT RAISE(ABORT,'실제 실패 후속 감사 삭제 금지'); END""")

def scan(store,limit:int=31):
    store.require_permission('company:manage')
    if type(limit) is not int or not 1<=limit<=31:
        raise ValueError('한 번에 1~31건만 검사')
    with store._connect() as con:
        con.execute('BEGIN IMMEDIATE')
        initialize(con)
        if stopped(con):
            return {'created':[],'blocked':'emergency_stop'}
        runs=con.execute("""SELECT r.id,r.task_id,r.employee_id,r.status FROM company_task_runs r
            JOIN company_tasks t ON t.id=r.task_id
            WHERE r.status IN ('failure','timeout','interrupted')
            AND NOT EXISTS (SELECT 1 FROM aiwack_failed_work_followups f WHERE f.source_run_id=r.id)
            ORDER BY r.id LIMIT ?""",(limit,)).fetchall()
        ids=[]
        for run,task,staff,status in runs:
            ids.append(int(con.execute("""INSERT INTO aiwack_failed_work_followups
                (source_run_id,task_id,employee_id,failure_status) VALUES(?,?,?,?)""",
                (run,task,staff,status)).lastrowid))
    return {'created':ids,'owner_approval_required':True,'model_called':False,'external_action':False}

def decide(store,proposal_id:int,decision:str,note:str):
    store.require_permission('company:manage')
    if type(proposal_id) is not int or proposal_id<=0:
        raise ValueError('개선 제안 ID 오류')
    if decision not in ('approved','rejected'):
        raise ValueError('소유자 승인/반려만 지원')
    if not isinstance(note,str) or not 5<=len(note.strip())<=200:
        raise ValueError('검수 사유는 5~200자')
    with store._connect() as con:
        con.execute('BEGIN IMMEDIATE')
        initialize(con)
        if stopped(con):
            raise PermissionError('비상정지 중 후속 업무 생성 금지')
        row=con.execute("""SELECT f.task_id,f.employee_id,f.source_run_id,f.failure_status,t.title,f.state
            FROM aiwack_failed_work_followups f
            JOIN company_tasks t ON t.id=f.task_id WHERE f.id=?""",(proposal_id,)).fetchone()
        if not row:
            raise ValueError('없는 개선 제안')
        task,staff,run,status,title,prior=row
        if prior!='pending':
            raise ValueError('이미 결정된 개선 제안')
        followup=None
        if decision=='approved':
            description=(f'실제 실패 실행 #{run} / 업무 #{task} / 직원 #{staff} / 상태 {status}. '
                        '원인 분석·수정·재검수 필수. 기존 업무 자동 재실행 금지. '
                        '관리자 사유: '+note.strip())[:1000]
            followup=int(con.execute("""INSERT INTO company_tasks(title,description,status)
                VALUES(?,?,'todo')""",(('실패 개선: '+title)[:120],description)).lastrowid)
            con.execute("""INSERT INTO company_task_status_events(task_id,old_status,new_status)
                VALUES(?,NULL,'todo')""",(followup,))
        con.execute("""UPDATE aiwack_failed_work_followups SET state=?,followup_task_id=?,
            owner_note=?,decided_at=CURRENT_TIMESTAMP WHERE id=? AND state='pending'""",
            (decision,followup,note.strip(),proposal_id))
    return {'id':proposal_id,'decision':decision,'new_task_id':followup,
            'model_autorun':False,'owner_approval_required':True}

def pending(store,limit:int=40):
    store.require_permission('company:manage')
    if type(limit) is not int or not 1<=limit<=100:
        raise ValueError('조회 한도 오류')
    with store._connect() as con:
        initialize(con)
        rows=con.execute("""SELECT id,source_run_id,task_id,employee_id,failure_status,
            state,followup_task_id FROM aiwack_failed_work_followups ORDER BY id DESC LIMIT ?""",
            (limit,)).fetchall()
    return [dict(id=i,run_id=r,task_id=t,employee_id=e,reason=q,state=s,followup_task_id=f)
            for i,r,t,e,q,s,f in rows]
