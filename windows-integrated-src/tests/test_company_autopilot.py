"""Autonomous local repeat work: real SQLite, no fake model activity."""
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
import pytest
from desktop.storage import LocalStore, AuthenticationError
from desktop import company_autopilot as auto


@pytest.fixture
def owners(tmp_path):
    a=LocalStore(tmp_path/'autopilot.sqlite3')
    a.setup_owner('company_owner','very-long-test-passphrase-2026')
    b=LocalStore(a.path)
    b.login('company_owner','very-long-test-passphrase-2026')
    return a,b


def test_default_off_and_no_implicit_activity(owners):
    a,b=owners
    assert auto.run_once(a,now=100)=={'executed':False,'reason':'disabled'}
    assert auto.history(a)==[] and a.list_tasks()==[]
    assert auto.approved_models_enabled(a) is False


def test_goal_schedule_and_event_create_real_drafts_once(owners):
    a,b=owners
    goal=a.add_goal('Future company strategy')
    a.update_goal(goal,'Future company strategy','Analyze local tasks','active')
    a.submit_local_event('autopilot-alert-1','manual_alert','Support request')
    sid=a.add_recurring_schedule('Periodic company note',interval_minutes=5)
    a.set_recurring_schedule_enabled(sid,True)
    due=a.list_recurring_schedules()[0]['next_due']
    auto.configure(a,True,now=due)
    result=auto.run_once(a,now=due)
    assert result['executed'] and result['proposal_created']==1
    assert result['schedule_created']==1 and result['event_created']==1
    assert not result['model_called'] and not result['external_actions']
    assert auto.run_once(b,now=due)['reason']=='not_due'
    assert len(a.list_tasks())==2
    assert all(t['status']=='todo' for t in a.list_tasks())
    assert len(a.list_autonomous_task_proposals())==1
    assert a.list_task_runs()==[]
    assert auto.history(b)[0]['state']=='success'


def test_simultaneous_exe_sessions_only_claim_once(owners):
    a,b=owners
    auto.configure(a,True,now=1000)
    barrier=Barrier(2)
    def invoke(store):
        barrier.wait(timeout=10)
        return auto.run_once(store,now=1000)
    with ThreadPoolExecutor(max_workers=2) as workers:
        fs=[workers.submit(invoke,store) for store in (a,b)]
        results=[f.result(timeout=30) for f in fs]
    assert sum(int(x['executed']) for x in results)==1
    assert len(auto.history(a))==1


def test_owner_emergency_stop_and_resume(owners):
    a,b=owners
    auto.configure(a,True,now=900)
    a.emergency_stop_local(True,'Owner stopped company')
    assert auto.run_once(b,now=900)['reason']=='emergency_stop'
    assert auto.history(a)==[]
    a.emergency_stop_local(False,'Owner resumed company')
    assert auto.run_once(a,now=900)['executed']


def test_disable_and_logout_prevent_work(owners):
    a,b=owners
    auto.configure(a,True,now=1)
    auto.configure(b,False,now=1)
    assert auto.run_once(a,now=1)['reason']=='disabled'
    a.logout()
    with pytest.raises(AuthenticationError):
        auto.run_once(a,now=2)
    with pytest.raises(AuthenticationError):
        auto.configure(a,True,now=2)


def test_interrupted_running_tick_is_not_silently_replayed(owners):
    a,b=owners
    auto.configure(a,True,now=10)
    with a._connect() as con:
        con.execute('UPDATE aiwack_autopilot_settings SET next_due=200 WHERE id=1')
        con.execute("INSERT INTO aiwack_autopilot_runs(planned_at,state) VALUES(10,'running')")
    assert auto.run_once(b,now=10)['reason']=='not_due'
    assert auto.run_once(b,now=200)['executed']
    assert auto.history(a)[1]['state']=='running'


def test_invalid_configuration_or_clock_rejected(owners):
    a,b=owners
    for enabled,interval in [(True,0),(True,61),(True,True),(1,5)]:
        with pytest.raises(ValueError):auto.configure(a,enabled,interval_minutes=interval)
    for time in (True,-1,'100'):
        with pytest.raises(ValueError):auto.run_once(a,now=time)


def test_separate_owner_optin_only_allows_preapproved_real_model_cycle(tmp_path,monkeypatch):
    import sys
    from desktop.model_runtime import ModelConfig
    from desktop import company_operations as ops
    db=LocalStore(tmp_path/'real_approved.sqlite3')
    db.setup_owner('owner','very-long-model-password-2026')
    chief=db.add_employee_draft('chief','Chief')
    staff=db.add_employee_draft('staff','Staff')
    db.assign_reporting_line(chief,'ceo')
    model=db.add_local_model(ModelConfig('MODEL','llamafile',sys.executable,'',32))
    for employee in (chief,staff):db.set_employee_model(employee,model)
    tid=ops.create_task(db,'Preapproved actual model')
    ops.assign_task(db,tid)
    with pytest.raises(PermissionError):auto.configure_approved_models(db,True)
    auto.configure(db,True,now=100)
    assert auto.approved_models_enabled(db) is False
    with pytest.raises(PermissionError):auto.run_one_approved_model(db,(tid,))
    auto.configure_approved_models(db,True)
    assert auto.approved_models_enabled(db)
    with pytest.raises(ValueError,match='실행 가능한'):
        auto.run_one_approved_model(db,(tid,))
    assert db.list_task_runs(tid)==[]
    ops.approve_chief_order(db,tid,'Owner approved this task')
    called=[]
    monkeypatch.setattr('desktop.task_runtime.run_local_model',
                        lambda *a,**k:called.append('staff') or 'SYNTHETIC STAFF')
    monkeypatch.setattr('desktop.chief_task_runtime.collect_chief_task_result',
                        lambda *a,**k:called.append('chief') or 'SYNTHETIC CHIEF')
    result=auto.run_one_approved_model(db,(tid,))
    assert result['completed_cycles']==1 and called==['staff','chief']
    aid=db.list_task_artifacts(tid)[0]['id']
    assert db.read_task_artifact(aid)['review_status']=='pending'
    assert db.find_chief_task_report(aid)['owner_decision']=='pending'
    assert db.read_task(tid)['status']=='in_progress'
    assert auto.approved_model_history(db)[0]['state']=='success'
    with pytest.raises(ValueError):
        auto.run_one_approved_model(db,(tid,))
    assert called==['staff','chief']
    auto.configure(db,False)
    assert not auto.approved_models_enabled(db)


def test_model_policy_emergency_stop_and_unapproved_selection(owners):
    a,b=owners
    auto.configure(a,True,now=10)
    auto.configure_approved_models(a,True)
    assert auto.approved_models_enabled(b)
    a.emergency_stop_local(True,'Stop real models')
    assert auto.approved_models_enabled(b) is False
    with pytest.raises(PermissionError):auto.run_one_approved_model(b,(1,))
    a.emergency_stop_local(False,'Resume')
    auto.configure_approved_models(b,False)
    assert not auto.approved_models_enabled(a)
    # True/False are the two valid explicit user choices. Only non-booleans fail.
    for valid in (True, False):
        assert auto.configure_approved_models(a,valid) is valid
    for wrong in (1,0,'1',None):
        with pytest.raises(ValueError):auto.configure_approved_models(a,wrong)
