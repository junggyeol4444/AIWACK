"""Stages87-90: owner-only local read-only management panels and a persisted safety stop.
No real AI communications, sales data, external approval, or service execution.
"""
import sqlite3
from desktop.local_commerce_common import digest, note, triggers


def initialize(con):
    con.execute("""CREATE TABLE IF NOT EXISTS local_emergency_control (
        id INTEGER PRIMARY KEY CHECK(id=1), stopped INTEGER NOT NULL DEFAULT 0 CHECK(stopped IN (0,1)))""")
    con.execute('INSERT OR IGNORE INTO local_emergency_control(id,stopped) VALUES(1,0)')
    con.execute("""CREATE TABLE IF NOT EXISTS local_emergency_control_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT, state INTEGER NOT NULL CHECK(state IN (0,1)),
        reason TEXT NOT NULL, previous_digest TEXT NOT NULL, digest TEXT NOT NULL,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)""")
    triggers(con,('local_emergency_control_events',))


def stopped(con):
    """Backward-compatible for tests that initialize the queue without LocalStore."""
    if not con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='local_emergency_control'").fetchone():
        return False
    row=con.execute('SELECT stopped FROM local_emergency_control WHERE id=1').fetchone()
    return bool(row and row[0])


def stop_history(con):
    con.row_factory=sqlite3.Row
    previous='';out=[]
    for r in con.execute('SELECT * FROM local_emergency_control_events ORDER BY id'):
        r=dict(r)
        if r['previous_digest']!=previous or r['digest']!=digest([r['state'],r['reason'],previous]):
            raise ValueError('emergency control audit hash mismatch')
        previous=r['digest'];out.append(r)
    if out and bool(out[-1]['state'])!=stopped(con):
        raise ValueError('emergency control state differs from audit')
    return out


def set_stop(con,value,reason):
    if type(value) is not bool:raise ValueError('boolean required')
    note(reason)
    history=stop_history(con)
    if stopped(con)==value:
        return {'stopped':value,'changed':False,'external_services_blocked_by_this_flag':False}
    prev=history[-1]['digest'] if history else ''
    con.execute('UPDATE local_emergency_control SET stopped=? WHERE id=1',(int(value),))
    con.execute('INSERT INTO local_emergency_control_events(state,reason,previous_digest,digest) VALUES(?,?,?,?)',
                (int(value),reason,prev,digest([int(value),reason,prev])))
    return {'stopped':value,'changed':True,'local_queue_claim_and_scheduler_blocked':value,
            'external_services_blocked_by_this_flag':False}


def organization(con):
    """Fixed SQL, descriptive only; no modifications."""
    return {'departments':[dict(id=r[0],name=r[1]) for r in con.execute('SELECT id,name FROM company_departments ORDER BY id')],
            'employees':[dict(id=r[0],name=r[1],department_id=r[2],lifecycle=r[3]) for r in con.execute('SELECT id,display_name,department_id,lifecycle FROM ai_employee_profiles ORDER BY id')],
            'projects':[dict(id=r[0],name=r[1],business_id=r[2],state=r[3]) for r in con.execute('SELECT id,title,business_id,state FROM managed_business_projects ORDER BY id')],
            'tasks':[dict(id=r[0],title=r[1],status=r[2]) for r in con.execute('SELECT id,title,status FROM company_tasks ORDER BY id LIMIT 250')],
            'read_only':True}


def communications(con):
    """Owner-only historical row counts; deliberately avoids exposing private messages."""
    tables=('direct_messages','department_chat_messages','project_chat_messages','company_meetings','local_task_queue_events')
    result={}
    for table in tables:
        exists=con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",(table,)).fetchone()
        result[table]=int(con.execute('SELECT COUNT(*) FROM "'+table+'"').fetchone()[0]) if exists else 0
    return {'local_records':result,'message_bodies_exposed':False,'live_ai_chat':False,'external_calls':False}


def commerce(con):
    from desktop.local_budget_scenarios import calculate
    budget=calculate(con)
    return {'hypothetical_budget':budget,
            'unpublished_listing_count':con.execute('SELECT COUNT(*) FROM local_unpublished_listings').fetchone()[0],
            'simulated_order_count':con.execute('SELECT COUNT(*) FROM local_simulated_orders').fetchone()[0],
            'actual_sales_verified':False,'actual_expenses_verified':False,'accounting_verified':False}


def approvals(con):
    # Summarizes workflow counts, but does not grant authority to approve external actions.
    result={'local_emergency_stopped':stopped(con), 'emergency_events':stop_history(con),
            'offline_only':True,'real_external_approvals_executed':False}
    for table in ('local_staffing_drafts','local_model_switch_drafts','local_diagnostic_improvement_drafts'):
        result[table+'_count']=con.execute('SELECT COUNT(*) FROM '+table).fetchone()[0]
    return result
