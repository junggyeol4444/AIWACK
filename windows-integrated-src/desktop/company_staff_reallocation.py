"""실제 직원 모델 실패 증빙을 근거로 제안하고 관리자 승인으로만 실제 부서를 이동한다."""
from __future__ import annotations
from desktop.stage87_90_management import stopped

def initialize(con):
    con.execute("""CREATE TABLE IF NOT EXISTS aiwack_staff_transfer_reviews (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      employee_id INTEGER NOT NULL REFERENCES ai_employee_profiles(id),
      from_department INTEGER REFERENCES company_departments(id),
      to_department INTEGER NOT NULL REFERENCES company_departments(id),
      source_run_id INTEGER NOT NULL REFERENCES company_task_runs(id),
      state TEXT NOT NULL DEFAULT 'pending' CHECK(state IN ('pending','accepted','rejected')),
      proposal_note TEXT NOT NULL, decision_note TEXT NOT NULL DEFAULT '',
      assignments_released INTEGER NOT NULL DEFAULT 0,
      created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
      decided_at TEXT, UNIQUE(employee_id,to_department,source_run_id))""")
    con.execute("""CREATE TRIGGER IF NOT EXISTS aiwack_staff_transfer_no_delete
      BEFORE DELETE ON aiwack_staff_transfer_reviews BEGIN
      SELECT RAISE(ABORT,'직원 조직 변경 감사 삭제 금지'); END""")

    con.execute("""CREATE TRIGGER IF NOT EXISTS aiwack_staff_transfer_guard_update
       BEFORE UPDATE ON aiwack_staff_transfer_reviews
       WHEN OLD.state!='pending' OR NEW.state NOT IN ('accepted','rejected')
         OR NEW.id!=OLD.id OR NEW.employee_id!=OLD.employee_id
         OR NEW.from_department IS NOT OLD.from_department
         OR NEW.to_department!=OLD.to_department OR NEW.source_run_id!=OLD.source_run_id
         OR NEW.proposal_note!=OLD.proposal_note OR NEW.created_at!=OLD.created_at
         OR NEW.decided_at IS NULL OR length(NEW.decision_note)<5
         OR length(NEW.decision_note)>200 OR NEW.assignments_released<0
       BEGIN SELECT RAISE(ABORT,'직원 이동 근거 및 확정 기록 수정 금지'); END""")

def _id(value):
    if type(value) is not int or value<=0:
        raise ValueError('직원·부서·실행 번호는 양의 정수입니다.')
    return value

def _note(value):
    if not isinstance(value,str) or not 5<=len(value.strip())<=200:
        raise ValueError('근거 또는 관리자 사유는 5~200자입니다.')
    return value.strip()

def propose(store,employee_id,target_department_id,source_run_id,note):
    store.require_permission('company:manage')
    store.require_permission('agents:manage')
    for v in (employee_id,target_department_id,source_run_id):_id(v)
    note=_note(note)
    with store._connect() as con:
        con.execute('BEGIN IMMEDIATE')
        initialize(con)
        if stopped(con):raise PermissionError('비상정지 중 직원 변경 제안 금지')
        employee=con.execute('SELECT department_id,lifecycle FROM ai_employee_profiles WHERE id=?',
                             (employee_id,)).fetchone()
        if not employee or employee[1]!='draft':raise ValueError('활성 직원만 이동 가능')
        if employee[0]==target_department_id:raise ValueError('이미 선택한 부서에 소속')
        if not con.execute('SELECT 1 FROM company_departments WHERE id=?',(target_department_id,)).fetchone():
            raise ValueError('대상 부서가 없습니다.')
        run=con.execute('''SELECT status FROM company_task_runs
             WHERE id=? AND employee_id=?''',(source_run_id,employee_id)).fetchone()
        if not run or run[0] not in ('failure','timeout','interrupted'):
            raise ValueError('동일 직원의 실제 실패 모델 실행 증빙이 필요합니다.')
        tier=con.execute('SELECT tier FROM ai_reporting_lines WHERE employee_id=?',(employee_id,)).fetchone()
        if tier and tier[0]!='staff':
            raise ValueError('총괄·부서장 AI는 일반 직원 재배치로 이동할 수 없습니다.')
        prior=con.execute('''SELECT id FROM aiwack_staff_transfer_reviews
                 WHERE employee_id=? AND to_department=? AND source_run_id=?''',
                 (employee_id,target_department_id,source_run_id)).fetchone()
        if prior:return {'id':prior[0],'duplicate':True,'executed':False}
        pid=con.execute('''INSERT INTO aiwack_staff_transfer_reviews
            (employee_id,from_department,to_department,source_run_id,proposal_note)
            VALUES(?,?,?,?,?)''',
            (employee_id,employee[0],target_department_id,source_run_id,note)).lastrowid
    return {'id':int(pid),'duplicate':False,'executed':False}

def decide(store,proposal_id,decision,note):
    store.require_permission('company:manage')
    store.require_permission('agents:manage')
    _id(proposal_id)
    note=_note(note)
    if decision not in ('accepted','rejected'):
        raise ValueError('관리자 수락 또는 반려만 지원합니다.')
    with store._connect() as con:
        con.execute('BEGIN IMMEDIATE')
        initialize(con)
        if stopped(con):raise PermissionError('비상정지 중 조직 개편 금지')
        proposal=con.execute('''SELECT employee_id,from_department,to_department,state
            FROM aiwack_staff_transfer_reviews WHERE id=?''',(proposal_id,)).fetchone()
        if not proposal or proposal[3]!='pending':raise ValueError('대기 중인 조직 개편 제안이 아닙니다.')
        employee,old,target,_=proposal
        released=0
        if decision=='accepted':
            current=con.execute('SELECT department_id,lifecycle FROM ai_employee_profiles WHERE id=?',
                                (employee,)).fetchone()
            if not current or current[0]!=old or current[1]!='draft':
                raise ValueError('직원 소속이나 상태가 변경됐으므로 재검토 필요')
            if con.execute("""SELECT 1 FROM company_task_runs
                 WHERE employee_id=? AND status='running' LIMIT 1""",(employee,)).fetchone():
                raise PermissionError('실제 직원 모델 실행 중에는 이동할 수 없습니다.')
            manager=con.execute('''SELECT r.tier,r.manager_id,m.department_id
                 FROM ai_reporting_lines r LEFT JOIN ai_employee_profiles m ON m.id=r.manager_id
                 WHERE r.employee_id=?''',(employee,)).fetchone()
            if manager and (manager[0]!='staff' or (manager[1] is not None and manager[2]!=target)):
                raise ValueError('상급자·부서 보고 관계가 새 부서와 충돌합니다.')
            if con.execute('SELECT 1 FROM ai_reporting_lines WHERE manager_id=? LIMIT 1',
                           (employee,)).fetchone():
                raise ValueError('하위 직원이 있는 관리자는 이동할 수 없습니다.')
            changed=con.execute('''UPDATE ai_employee_profiles
                 SET department_id=?,updated_at=CURRENT_TIMESTAMP
                 WHERE id=? AND department_id IS ? AND lifecycle='draft' ''',
                 (target,employee,old))
            if changed.rowcount!=1:raise RuntimeError('다른 EXE의 직원 수정과 충돌')
            assignments=con.execute('SELECT task_id FROM company_task_assignments WHERE employee_id=?',
                                    (employee,)).fetchall()
            for (task_id,) in assignments:
                store._clear_task_assignment_in_tx(con,task_id,'employee_changed',
                                                  '소유자 조직 변경으로 기존 배정 해제')
                released+=1
        con.execute('''UPDATE aiwack_staff_transfer_reviews
            SET state=?,decision_note=?,assignments_released=?,decided_at=CURRENT_TIMESTAMP
            WHERE id=? AND state='pending' ''',(decision,note,released,proposal_id))
    return {'id':proposal_id,'decision':decision,'assignments_released':released,
            'model_executed':False,'automatic_permission_grant':False}

def history(store,limit=30):
    store.require_permission('company:manage')
    if type(limit) is not int or not 1<=limit<=100:raise ValueError('감사 조회 범위 오류')
    with store._connect() as con:
        initialize(con)
        rows=con.execute('''SELECT id,employee_id,from_department,to_department,source_run_id,
            state,assignments_released,created_at
            FROM aiwack_staff_transfer_reviews ORDER BY id DESC LIMIT ?''',(limit,)).fetchall()
    return [dict(zip(('id','employee_id','from_department','to_department','source_run_id',
                      'state','assignments_released','created_at'),row)) for row in rows]
