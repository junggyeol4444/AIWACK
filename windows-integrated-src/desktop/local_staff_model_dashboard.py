"""Stages84-86: offline STAFFING DRAFTS, model registry comparison DRAFTS, snapshot dashboard.
NO real agents are hired/run, no AI model benchmark or live external monitoring.
"""
import sqlite3
from desktop.local_commerce_common import digest,ident,key,note,triggers
from desktop.local_company_diagnostics import performance,diagnostics

STAFF_KINDS=('CREATE_PROFILE_DRAFT','REASSIGN_DRAFT')

def initialize(con):
    con.execute('''CREATE TABLE IF NOT EXISTS local_staffing_drafts (
       id INTEGER PRIMARY KEY AUTOINCREMENT,
       plan_key TEXT NOT NULL UNIQUE,
       kind TEXT NOT NULL CHECK(kind IN ('CREATE_PROFILE_DRAFT','REASSIGN_DRAFT')),
       employee_id INTEGER REFERENCES ai_employee_profiles(id),
       department_id INTEGER NOT NULL REFERENCES company_departments(id),
       note TEXT NOT NULL,
       source_digest TEXT NOT NULL,
       previous_digest TEXT NOT NULL,
       digest TEXT NOT NULL,
       created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)''')
    con.execute('''CREATE TABLE IF NOT EXISTS local_model_switch_drafts (
       id INTEGER PRIMARY KEY AUTOINCREMENT,
       switch_key TEXT NOT NULL UNIQUE,
       model_id INTEGER NOT NULL REFERENCES ai_local_models(id),
       intended_use TEXT NOT NULL CHECK(intended_use IN ('OFFLINE_REVIEW_ONLY','OWNER_TEST_PROPOSAL')),
       note TEXT NOT NULL,
       registry_digest TEXT NOT NULL,
       previous_digest TEXT NOT NULL,
       digest TEXT NOT NULL,
       created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)''')
    triggers(con,('local_staffing_drafts','local_model_switch_drafts'))

def staffing_history(con):
    con.row_factory=sqlite3.Row
    prev='';out=[]
    for row in con.execute('SELECT * FROM local_staffing_drafts ORDER BY id'):
        r=dict(row)
        if r['previous_digest']!=prev or digest([r['plan_key'],r['kind'],r['employee_id'],r['department_id'],r['note'],r['source_digest'],prev])!=r['digest']:
            raise ValueError('staffing draft hash audit mismatch')
        key(r['plan_key']);note(r['note'])
        out.append({**r,'staff_changed':False,'agent_launched':False,'owner_review_pending':True})
        prev=r['digest']
    return out

def staffing_draft(con,plan_key,kind,department_id,note_text,employee_id=None):
    key(plan_key);ident(department_id);note(note_text)
    if kind not in STAFF_KINDS:raise ValueError('staffing metadata drafts only')
    dept=con.execute('SELECT name FROM company_departments WHERE id=?',(department_id,)).fetchone()
    if dept is None:raise ValueError('unknown department')
    if kind=='REASSIGN_DRAFT':
        ident(employee_id)
        emp=con.execute('SELECT department_id,lifecycle FROM ai_employee_profiles WHERE id=?',(employee_id,)).fetchone()
        if emp is None or emp[1]!='draft' or emp[0]==department_id:
            raise ValueError('employee missing/inactive or unchanged department')
        snapshot=[employee_id,emp[0],emp[1],department_id]
    else:
        if employee_id is not None:raise ValueError('profile creation draft must not name existing employee')
        snapshot=[department_id,dept[0],'NO_REAL_HIRING']
    src=digest(snapshot)
    rows=staffing_history(con)
    for row in rows:
        if row['plan_key']==plan_key:
            if (row['kind'],row['employee_id'],row['department_id'],row['note'],row['source_digest'])!=(kind,employee_id,department_id,note_text,src):
                raise ValueError('staffing plan key conflict')
            return {**row,'duplicate':True}
    prev=rows[-1]['digest'] if rows else ''
    h=digest([plan_key,kind,employee_id,department_id,note_text,src,prev])
    cur=con.execute('''INSERT INTO local_staffing_drafts
     (plan_key,kind,employee_id,department_id,note,source_digest,previous_digest,digest)
     VALUES(?,?,?,?,?,?,?,?)''',(plan_key,kind,employee_id,department_id,note_text,src,prev,h))
    return {**[r for r in staffing_history(con) if r['id']==cur.lastrowid][0],'duplicate':False}

def model_registry(con):
    """Does not read, run or confirm executables/model files."""
    rows=con.execute('SELECT id,name,backend,max_tokens FROM ai_local_models ORDER BY id').fetchall()
    return {'models':[{'id':r[0],'name':r[1],'backend':r[2],'configured_max_tokens':r[3],
                       'benchmark_verified':False,'model_file_verified':False,'inference_performed':False} for r in rows],
            'comparison_basis':'CONFIGURATION_ONLY_NOT_SPEED_OR_QUALITY',
            'validated_real_model_count':0,'actual_switch_performed':False}

def switch_history(con):
    con.row_factory=sqlite3.Row
    prev='';rows=[]
    for record in con.execute('SELECT * FROM local_model_switch_drafts ORDER BY id'):
        r=dict(record)
        if r['previous_digest']!=prev or digest([r['switch_key'],r['model_id'],r['intended_use'],r['note'],r['registry_digest'],prev])!=r['digest']:
            raise ValueError('model selection hash audit mismatch')
        key(r['switch_key']);note(r['note'])
        rows.append({**r,'real_model_switched':False,'quality_benchmarked':False,'owner_review_pending':True})
        prev=r['digest']
    return rows

def switch_draft(con,switch_key,model_id,intended_use,note_text):
    key(switch_key);ident(model_id);note(note_text)
    if intended_use not in ('OFFLINE_REVIEW_ONLY','OWNER_TEST_PROPOSAL'):
        raise ValueError('real model switch not allowed in local draft')
    selected=next((m for m in model_registry(con)['models'] if m['id']==model_id),None)
    if selected is None:raise ValueError('no matching configured model')
    registry_digest=digest(selected)
    rows=switch_history(con)
    for r in rows:
        if r['switch_key']==switch_key:
            if (r['model_id'],r['intended_use'],r['note'],r['registry_digest'])!=(model_id,intended_use,note_text,registry_digest):
                raise ValueError('model review key conflict')
            return {**r,'duplicate':True}
    prev=rows[-1]['digest'] if rows else ''
    hashed=digest([switch_key,model_id,intended_use,note_text,registry_digest,prev])
    cur=con.execute('INSERT INTO local_model_switch_drafts(switch_key,model_id,intended_use,note,registry_digest,previous_digest,digest) VALUES(?,?,?,?,?,?,?)',
                    (switch_key,model_id,intended_use,note_text,registry_digest,prev,hashed))
    return {**[r for r in switch_history(con) if r['id']==cur.lastrowid][0],'duplicate':False}

def dashboard(con):
    """Refresh on user request; no background polling and no real-time guarantees."""
    personnel=performance(con)
    local_signals=diagnostics(con)
    return {'snapshot_only':True,'live_monitoring':False,'real_sales_verified':False,
            'real_customer_count_known':False,'model_inference_running':False,
            'employee_profile_count':len(personnel['employees']),
            'department_count':len(personnel['departments']),
            'business_plan_count':len(personnel['businesses']),
            'task_status_counts':personnel['tasks'],
            'local_signal_count':len(local_signals['indicators']),
            'hypothetical_budget':personnel['assumed_budget'],
            'configured_model_count':len(model_registry(con)['models']),
            'pending_staffing_draft_count':len(staffing_history(con)),
            'pending_model_review_draft_count':len(switch_history(con)),
            'no_side_effects':True}
