"""Stage 24 real SQLite task assignment; no HTTP, local model, or fake agent."""
import sqlite3
import pytest
from desktop.storage import AuthenticationError, LocalStore

USERNAME, PASSWORD = 'local_owner_24', 'strong-password-local-2026'


def init(tmp_path):
    db=LocalStore(tmp_path/'company.sqlite3')
    db.setup_owner(USERNAME,PASSWORD)
    dept=db.add_department('연구실')
    other=db.add_department('고객지원')
    job=db.add_designation('job','연구 업무')
    other_job=db.add_designation('job','고객 응대')
    rank=db.add_designation('rank','연구원')
    first=db.add_employee_draft('worker_001','가람',department_id=dept,job_id=job,rank_id=rank)
    second=db.add_employee_draft('worker_002','나래',department_id=dept,job_id=job)
    unrelated=db.add_employee_draft('worker_003','다른 부서',department_id=other,job_id=other_job)
    task=db.add_task('로컬 문서 정리')
    return db,dept,job,rank,first,second,unrelated,task


def test_strict_routing_persistence_and_audit(tmp_path):
    db,dept,job,_,first,_,_,task=init(tmp_path)
    db.save_task_requirements(task,dept,job)
    chosen=db.auto_assign_task(task)
    assert chosen['employee_id']==first and chosen['changed']
    assert '미완료 배정=0건' in chosen['reason']
    assert db.read_task_routing(task)['department_id']==dept
    assert db.read_task_routing(task)['job_id']==job
    assert db.auto_assign_task(task)=={'employee_id':first,'employee_name':'가람','changed':False}
    assert len(db.list_task_assignment_events(task))==1
    db.logout()
    other=LocalStore(db.path)
    with pytest.raises(AuthenticationError): other.read_task_routing(task)
    other.login(USERNAME,PASSWORD)
    assert other.read_task_routing(task)['employee_id']==first
    assert other.list_task_assignment_events(task)[0]['action']=='auto_assigned'


def test_minimum_workload_then_stable_id_and_explicit_clear(tmp_path):
    db,dept,job,_,first,second,_,t1=init(tmp_path)
    t2=db.add_task('별도 업무')
    for t in (t1,t2):db.save_task_requirements(t,dept,job)
    assert db.auto_assign_task(t1)['employee_id']==first
    assert db.auto_assign_task(t2)['employee_id']==second
    db.clear_task_assignment(t1)
    assert db.read_task_routing(t1)['employee_id'] is None
    assert db.list_task_assignment_events(t1)[-1]['action']=='cleared'
    assert db.auto_assign_task(t1)['employee_id']==first


def test_task_completed_not_considered_open_workload(tmp_path):
    db,dept,job,_,first,_,_,t1=init(tmp_path)
    db.save_task_requirements(t1,dept,job)
    assert db.auto_assign_task(t1)['employee_id']==first
    db.set_task_status(t1,'in_progress')
    db.set_task_status(t1,'done')
    t2=db.add_task('새 업무')
    db.save_task_requirements(t2,dept,job)
    assert db.auto_assign_task(t2)['employee_id']==first


def test_no_fallback_when_no_staff_matches(tmp_path):
    db,dept,job,_,first,_,unrelated,task=init(tmp_path)
    db.set_employee_inactive(first)
    db.set_employee_inactive(db.list_employee_records()[1]['id'])
    db.save_task_requirements(task,dept,job)
    with pytest.raises(ValueError,match='조건에 맞는'):
        db.auto_assign_task(task)
    assert db.read_task_routing(task)['employee_id'] is None
    assert db.list_task_assignment_events(task)==[]


def test_wrong_designation_kind_and_invalid_fk_no_writes(tmp_path):
    db,dept,job,rank,_,_,_,task=init(tmp_path)
    for d,j in [(dept,rank),(999999,job),(dept,999999),(-2,job),(True,job),(dept,'1')]:
        with pytest.raises(ValueError):db.save_task_requirements(task,d,j)
    assert db.read_task_routing(task)['job_id'] is None


def test_changing_requirements_revokes_assignee_and_audits(tmp_path):
    db,dept,job,_,first,_,unrelated,task=init(tmp_path)
    db.save_task_requirements(task,dept,job)
    db.auto_assign_task(task)
    db.save_task_requirements(task,None,None)
    assert db.read_task_routing(task)['employee_id'] is None
    assert [x['action'] for x in db.list_task_assignment_events(task)]==['auto_assigned','requirements_changed']
    assert db.auto_assign_task(task)['employee_id']==first
    # identical requirements must be idempotent and leave assignee unchanged
    db.save_task_requirements(task,None,None)
    assert db.read_task_routing(task)['employee_id']==first


def test_employee_inactivation_revokes_then_restored_requires_manual_reassignment(tmp_path):
    db,dept,job,_,first,second,_,task=init(tmp_path)
    db.save_task_requirements(task,dept,job)
    db.auto_assign_task(task)
    db.set_employee_inactive(first)
    assert db.read_task_routing(task)['employee_id'] is None
    assert db.list_task_assignment_events(task)[-1]['action']=='employee_inactive'
    assert db.auto_assign_task(task)['employee_id']==second
    db.restore_employee_draft(first)
    assert db.read_task_routing(task)['employee_id']==second


def test_employee_department_job_change_revokes_but_renaming_does_not(tmp_path):
    db,dept,job,rank,first,_,unrelated,task=init(tmp_path)
    db.save_task_requirements(task,dept,job)
    db.auto_assign_task(task)
    db.update_employee_record(first,'가람 변경',department_id=dept,job_id=job,rank_id=rank)
    assert db.read_task_routing(task)['employee_id']==first
    other_dept=db.add_department('개발')
    db.update_employee_record(first,'가람 변경',department_id=other_dept,job_id=job,rank_id=rank)
    assert db.read_task_routing(task)['employee_id'] is None
    assert db.list_task_assignment_events(task)[-1]['action']=='employee_changed'


def test_inactive_or_executive_not_assigned(tmp_path):
    db,dept,job,_,first,second,other,task=init(tmp_path)
    # a chief profile must have no department, distinct from regular worker.
    ceo=db.add_employee_draft('ceo_stage24','CEO')
    db.assign_reporting_line(ceo,'ceo')
    # An unassigned employee without department/job is also excluded by strict matching.
    db.save_task_requirements(task,dept,job)
    assert db.auto_assign_task(task)['employee_id']==first
    assert db.read_task_routing(task)['employee_id']!=ceo


@pytest.mark.parametrize('status', ['in_progress','blocked','done','cancelled'])
def test_assign_only_todo(tmp_path,status):
    db,_,_,_,_,_,_,task=init(tmp_path)
    if status in ('blocked','in_progress'):
        db.set_task_status(task,status)
    elif status=='done':
        db.set_task_status(task,'in_progress');db.set_task_status(task,'done')
    else:
        db.set_task_status(task,'cancelled')
    with pytest.raises(ValueError,match='todo'): db.auto_assign_task(task)
    with pytest.raises(ValueError,match='할 일'): db.save_task_requirements(task)
    with pytest.raises(ValueError,match='할 일'): db.clear_task_assignment(task)


def test_permissions_denied_on_every_routing_method(tmp_path):
    db,dept,job,_,_,_,_,task=init(tmp_path)
    db.logout()
    for fn in (lambda:db.read_task_routing(task),lambda:db.auto_assign_task(task),
               lambda:db.save_task_requirements(task,dept,job),lambda:db.clear_task_assignment(task),
               lambda:db.list_task_assignment_events(task)):
        with pytest.raises(AuthenticationError):fn()


def test_assignment_atomic_if_history_insert_fails(tmp_path):
    db,dept,job,_,_,_,_,task=init(tmp_path)
    db.save_task_requirements(task,dept,job)
    with sqlite3.connect(db.path) as con:
        con.execute("""CREATE TRIGGER fail_assignment BEFORE INSERT ON company_task_assignment_events
               WHEN NEW.action='auto_assigned' BEGIN SELECT RAISE(ABORT, 'reject event'); END""")
    with pytest.raises(sqlite3.IntegrityError):db.auto_assign_task(task)
    assert db.read_task_routing(task)['employee_id'] is None


def test_existing_stage23_data_stays_untouched_on_upgrade(tmp_path):
    db,dept,job,_,first,_,_,task=init(tmp_path)
    db.save_note('오래된 메모')
    db.logout()
    db=LocalStore(db.path)
    db.login(USERNAME,PASSWORD)
    assert db.read_task(task)['title']=='로컬 문서 정리'
    assert db.read_note()=='오래된 메모'
    assert db.read_task_routing(task)['department_id'] is None
    assert db.auto_assign_task(task)['employee_id']==first


def test_no_network_or_process_triggered_by_assignment(tmp_path, monkeypatch):
    import socket, subprocess
    db,dept,job,_,_,_,_,task=init(tmp_path)
    db.save_task_requirements(task,dept,job)
    def never(*args,**kwargs): raise AssertionError('auto assignment must never run processes or sockets')
    monkeypatch.setattr(subprocess,'Popen',never)
    monkeypatch.setattr(socket,'create_connection',never)
    assert db.auto_assign_task(task)['changed']


def test_department_head_is_excluded_from_assignment(tmp_path):
    db,dept,job,_,first,second,_,task=init(tmp_path)
    ceo=db.add_employee_draft('ceo_002','총괄')
    db.assign_reporting_line(ceo,'ceo')
    db.assign_reporting_line(first,'department_head',ceo)
    db.set_employee_inactive(second)
    db.save_task_requirements(task,dept,job)
    with pytest.raises(ValueError,match='조건에 맞는'):
        db.auto_assign_task(task)
    assert db.read_task_routing(task)['employee_id'] is None


def test_promoting_assigned_staff_to_head_revokes_assignment(tmp_path):
    db,dept,job,_,first,_,_,task=init(tmp_path)
    ceo=db.add_employee_draft('ceo_003','총괄')
    db.assign_reporting_line(ceo,'ceo')
    db.save_task_requirements(task,dept,job)
    assert db.auto_assign_task(task)['employee_id']==first
    db.assign_reporting_line(first,'department_head',ceo)
    assert db.read_task_routing(task)['employee_id'] is None
    assert db.list_task_assignment_events(task)[-1]['action']=='employee_changed'
