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
