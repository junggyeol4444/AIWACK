"""Approved single-task automation; synthetic local subprocess, not GGUF."""
from __future__ import annotations
import sys
import threading
import pytest
from desktop.model_runtime import ModelConfig
from desktop.storage import LocalStore
from desktop import company_operations as ops

@pytest.fixture
def session(tmp_path,monkeypatch):
    store=LocalStore(tmp_path/'approved-cycle.sqlite3')
    store.setup_owner('auto_owner','owner-test-password-2026')
    chief=store.add_employee_draft('auto_chief','Chief')
    worker=store.add_employee_draft('auto_worker','Staff')
    store.assign_reporting_line(chief,'ceo')
    mid=store.add_local_model(ModelConfig('SyntheticAutocycle','llamafile',sys.executable,'',24))
    store.set_employee_model(chief,mid)
    store.set_employee_model(worker,mid)
    tid=ops.create_task(store,'Approved safe offline task')
    assert ops.assign_task(store,tid)['employee_id']==worker
    events=[]
    def fake_worker(*a,**k):
        events.append('worker')
        return 'SYNTHETIC STAFF OUTPUT'
    def fake_chief(*a,**k):
        events.append('chief')
        return 'SYNTHETIC CHIEF REVIEW; OWNER DECIDES'
    monkeypatch.setattr('desktop.task_runtime.run_local_model',fake_worker)
    monkeypatch.setattr('desktop.chief_task_runtime.collect_chief_task_result',fake_chief)
    return store,tid,events

def test_no_owner_order_means_no_worker_or_chief(session):
    store,tid,events=session
    with pytest.raises(ValueError,match='승인'):
        ops.execute_approved_chief_cycle(store,tid)
    assert events==[] and not store.list_task_runs(tid)

def test_one_approved_click_dispatches_worker_then_chief_and_leaves_review_pending(session):
    store,tid,events=session
    ops.approve_chief_order(store,tid,'Owner approved order')
    result=ops.execute_approved_chief_cycle(store,tid)
    assert events==['worker','chief']
    aid=result['artifact_id']
    assert result['automatic_worker_and_chief'] and result['owner_approval_required']
    assert store.read_task_artifact(aid)['review_status']=='pending'
    assert store.find_chief_task_report(aid)['owner_decision']=='pending'
    assert store.read_task(tid)['status']=='in_progress'
    with pytest.raises(ValueError,match='아직 실행하지 않은'):
        ops.execute_approved_chief_cycle(store,tid)
    assert events==['worker','chief']
    store.logout()
    check=LocalStore(store.path)
    check.login('auto_owner','owner-test-password-2026')
    assert check.find_chief_task_report(aid)['owner_decision']=='pending'

def test_pre_cancel_never_starts_model(session):
    store,tid,events=session
    ops.approve_chief_order(store,tid,'Approved')
    stopped=threading.Event();stopped.set()
    with pytest.raises(InterruptedError):
        ops.execute_approved_chief_cycle(store,tid,cancel=stopped)
    assert not events

def test_cancel_after_staff_preserves_pending_draft_without_chief(session,monkeypatch):
    store,tid,events=session
    ops.approve_chief_order(store,tid,'Approved')
    flag=threading.Event()
    def worker(*a,**k):
        events.append('worker')
        flag.set()
        return 'SYNTHETIC STAFF OUTPUT'
    monkeypatch.setattr('desktop.task_runtime.run_local_model',worker)
    with pytest.raises(InterruptedError):
        ops.execute_approved_chief_cycle(store,tid,cancel=flag)
    assert events==['worker']
    artifact=store.list_task_artifacts(tid)[0]
    assert artifact['review_status']=='pending'
    assert store.find_chief_task_report(artifact['id']) is None

def test_emergency_stop_prevents_chief_after_worker(session,monkeypatch):
    store,tid,events=session
    ops.approve_chief_order(store,tid,'Approved')
    def worker(*a,**k):
        events.append('worker')
        store.emergency_stop_local(True,'Owner stopped automation')
        return 'SYNTHETIC STAFF OUTPUT'
    monkeypatch.setattr('desktop.task_runtime.run_local_model',worker)
    with pytest.raises(PermissionError,match='비상'):
        ops.execute_approved_chief_cycle(store,tid)
    assert events==['worker']
    aid=store.list_task_artifacts(tid)[0]['id']
    assert store.find_chief_task_report(aid) is None
    assert store.read_task(tid)['status']=='in_progress'

def test_failed_staff_does_not_invoke_chief(session,monkeypatch):
    store,tid,events=session
    ops.approve_chief_order(store,tid,'Approved')
    def broken(*a,**k):
        events.append('worker')
        raise RuntimeError('Synthetic worker error')
    monkeypatch.setattr('desktop.task_runtime.run_local_model',broken)
    with pytest.raises(RuntimeError):
        ops.execute_approved_chief_cycle(store,tid)
    assert events==['worker']
    assert not store.list_task_artifacts(tid)

def test_queue_never_runs_unapproved_work_and_runs_two_approved_in_order(tmp_path,monkeypatch):
    store=LocalStore(tmp_path/'two-approved.sqlite3')
    store.setup_owner('queue_owner','queue-test-password-2026')
    chief=store.add_employee_draft('chief-queue','Chief')
    staff=store.add_employee_draft('staff-queue','Staff')
    store.assign_reporting_line(chief,'ceo')
    mid=store.add_local_model(ModelConfig('SyntheticQueue','llamafile',sys.executable,'',24))
    store.set_employee_model(chief,mid)
    store.set_employee_model(staff,mid)
    ids=[ops.create_task(store,f'Approved queue task {k}') for k in range(3)]
    for tid in ids:
        assert ops.assign_task(store,tid)['employee_id']==staff
    for tid in ids[:2]:
        ops.approve_chief_order(store,tid,f'Owner approved queue task {tid}')
    events=[]
    def fake_worker(*args,**kwargs):
        events.append('worker')
        return 'SYNTHETIC WORKER QUEUE RESULT'
    def fake_chief(*args,**kwargs):
        events.append('chief')
        return 'SYNTHETIC CHIEF QUEUE REVIEW'
    monkeypatch.setattr('desktop.task_runtime.run_local_model',fake_worker)
    monkeypatch.setattr('desktop.chief_task_runtime.collect_chief_task_result',fake_chief)
    result=ops.execute_approved_chief_queue(store,limit=3)
    assert result['task_ids']==ids[:2]
    assert result['completed_cycles']==2 and result['pending_owner_review']==2
    assert events==['worker','chief','worker','chief']
    for tid in ids[:2]:
        assert store.read_task(tid)['status']=='in_progress'
        aid=store.list_task_artifacts(tid)[0]['id']
        assert store.find_chief_task_report(aid)['owner_decision']=='pending'
    assert store.read_task(ids[2])['status']=='todo'
    assert store.list_task_runs(ids[2])==[]
    with pytest.raises(ValueError,match='실행 가능한'):
        ops.execute_approved_chief_queue(store,limit=3)

def test_queue_invalid_limits_and_precancel(session):
    store,tid,events=session
    ops.approve_chief_order(store,tid,'approved order')
    for invalid in (True,0,4,-1,'2'):
        with pytest.raises(ValueError,match='1~3'):
            ops.execute_approved_chief_queue(store,limit=invalid)
    flag=threading.Event();flag.set()
    with pytest.raises(InterruptedError):
        ops.execute_approved_chief_queue(store,cancel=flag)
    assert not events and not store.list_task_runs(tid)

def test_queue_stops_on_model_failure_without_running_following_task(tmp_path,monkeypatch):
    store=LocalStore(tmp_path/'fail-queue.sqlite3')
    store.setup_owner('queue_fail_owner','queue-test-password-2026')
    chief=store.add_employee_draft('chief-failqueue','Chief')
    staff=store.add_employee_draft('staff-failqueue','Staff')
    store.assign_reporting_line(chief,'ceo')
    mid=store.add_local_model(ModelConfig('SyntheticFailQueue','llamafile',sys.executable,'',24))
    store.set_employee_model(chief,mid)
    store.set_employee_model(staff,mid)
    ids=[ops.create_task(store,'Queue fail task A'),ops.create_task(store,'Queue fail task B')]
    for tid in ids:
        ops.assign_task(store,tid)
        ops.approve_chief_order(store,tid,'Approved')
    seen=[]
    def fail_worker(*args,**kwargs):
        seen.append('worker')
        raise RuntimeError('First synthetic worker failed')
    monkeypatch.setattr('desktop.task_runtime.run_local_model',fail_worker)
    with pytest.raises(RuntimeError,match='First synthetic worker'):
        ops.execute_approved_chief_queue(store)
    assert seen==['worker']
    assert store.list_task_runs(ids[1])==[] and store.read_task(ids[1])['status']=='todo'

def test_auto_routing_prefers_model_connected_staff_over_unconfigured_profiles(tmp_path):
    """The ready worker must win before equal-load, unconfigured drafts."""
    db=LocalStore(tmp_path/'ready-routing.sqlite3')
    db.setup_owner('ready_route_owner','ready-route-password-2026')
    chief=db.add_employee_draft('ready_chief','Chief')
    ready_a=db.add_employee_draft('ready_staff_a','Ready A')
    ready_b=db.add_employee_draft('ready_staff_b','Ready B')
    unbound=db.add_employee_draft('unbound_staff','Unconfigured')
    db.assign_reporting_line(chief,'ceo')
    m=db.add_local_model(ModelConfig('SyntheticReadyRoute','llamafile',sys.executable,'',32))
    db.set_employee_model(chief,m)
    db.set_employee_model(ready_a,m)
    db.set_employee_model(ready_b,m)
    first=ops.create_task(db,'First work with real ready runner')
    second=ops.create_task(db,'Second work with real ready runner')
    third=ops.create_task(db,'Fallback still allowed for explicitly routed draft')
    for task_id in (first,second,third):
        assigned=ops.assign_task(db,task_id)['employee_id']
        assert assigned in (ready_a,ready_b)
        assert db.read_employee_model(assigned) is not None
    # No silent routing to an unconfigured draft despite its zero workload.
    assert db.read_employee_model(unbound) is None
