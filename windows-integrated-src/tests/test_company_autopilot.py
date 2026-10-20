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
