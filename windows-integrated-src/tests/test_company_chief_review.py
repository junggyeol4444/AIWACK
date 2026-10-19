"""Owner-gated chief re-review after a real audited employee task run.

This is the second handoff in a real AI company: chief -> staff -> chief ->
owner. Mock text in these tests is labelled synthetic; a separate Windows
native-subprocess integration scenario exercises the actual local runner.
"""
from __future__ import annotations

import threading
import sys

import pytest
from desktop.model_runtime import ModelConfig
from desktop.storage import AuthenticationError, LocalStore
from desktop import company_operations as ops


@pytest.fixture
def reviewed_candidate(tmp_path, monkeypatch):
    store = LocalStore(tmp_path/'chief-review.sqlite3')
    store.setup_owner('report_owner', 'test-only-owner-password-2026')
    chief = store.add_employee_draft('report_chief', 'Chief Local AI')
    worker = store.add_employee_draft('report_worker', 'Staff Local AI')
    store.assign_reporting_line(chief, 'ceo')
    local = store.add_local_model(ModelConfig('test adapter synthetic, not real GGUF',
                                            'llamafile',sys.executable,'',24))
    store.set_employee_model(chief, local)
    store.set_employee_model(worker, local)
    tid = ops.create_task(store,'Chief report task')
    assert ops.assign_task(store,tid)['employee_id']==worker
    order = ops.approve_chief_order(store,tid,'Please produce an offline report')
    assert order
    monkeypatch.setattr('desktop.task_runtime.run_local_model',
                        lambda *a,**kw:'SYNTHETIC STAFF REPORT FOR STORAGE TEST')
    artifact = ops.execute_task(store,tid)['artifact_id']
    assert store.read_task_artifact(artifact)['review_status']=='pending'
    assert store.read_task(tid)['status']=='in_progress'
    return store,tid,artifact,chief,worker


def test_real_chief_review_saved_pending_without_job_completion(reviewed_candidate,monkeypatch):
    store,tid,artifact,chief,worker=reviewed_candidate
    requests=[]
    def chief(_store,aid,**kwargs):
        requests.append(aid)
        return 'SYNTHETIC CHIEF RECONCILIATION ONLY: revise detail before approval'
    monkeypatch.setattr('desktop.chief_task_runtime.collect_chief_task_result',chief)
    output=ops.collect_chief_review(store,artifact)
    assert requests==[artifact]
    assert output['chief_model_called'] is True
    assert output['status']=='awaiting_owner_review'
    assert output['task_completed'] is False
    report=store.find_chief_task_report(artifact)
    assert report['id']==output['report_id']
    assert report['owner_decision']=='pending'
    assert store.read_task(tid)['status']=='in_progress'
    assert store.read_task_artifact(artifact)['review_status']=='pending'
    with pytest.raises(ValueError,match='이미'):
        ops.collect_chief_review(store,artifact)
    assert requests==[artifact]


def test_owner_accepts_or_rejects_only_report_not_worker_result(reviewed_candidate,monkeypatch):
    store,tid,artifact,_,_=reviewed_candidate
    monkeypatch.setattr('desktop.chief_task_runtime.collect_chief_task_result',
                        lambda *a,**kw:'SYNTHETIC CHIEF REVIEW: needs owner')
    report_id=ops.collect_chief_review(store,artifact)['report_id']
    for invalid in ('approved','done','accept',''):
        with pytest.raises(ValueError): ops.review_chief_feedback(store,report_id,invalid)
    ops.review_chief_feedback(store,report_id,'accepted','Owner read and agreed')
    report=store.read_chief_task_report(report_id)
    assert report['owner_decision']=='accepted'
    assert report['owner_note']=='Owner read and agreed'
    assert store.read_task(tid)['status']=='in_progress'
    assert store.read_task_artifact(artifact)['review_status']=='pending'
    with pytest.raises(ValueError,match='이미'):
        ops.review_chief_feedback(store,report_id,'rejected')
    store.logout()
    fresh=LocalStore(store.path)
    with pytest.raises(AuthenticationError):fresh.read_chief_task_report(report_id)
    fresh.login('report_owner','test-only-owner-password-2026')
    assert fresh.read_chief_task_report(report_id)['owner_decision']=='accepted'
    assert fresh.read_task(tid)['status']=='in_progress'


def test_cancelled_before_and_after_model_discards_report(reviewed_candidate,monkeypatch):
    store,_,artifact,_,_=reviewed_candidate
    cancelled=threading.Event();cancelled.set()
    with pytest.raises(InterruptedError):ops.collect_chief_review(store,artifact,cancel=cancelled)
    assert store.find_chief_task_report(artifact) is None
    cancelled.clear()
    def respondent(*args,**kwargs):
        cancelled.set()
        return 'SYNTHETIC late response'
    monkeypatch.setattr('desktop.chief_task_runtime.collect_chief_task_result',respondent)
    with pytest.raises(InterruptedError):ops.collect_chief_review(store,artifact,cancel=cancelled)
    assert store.find_chief_task_report(artifact) is None


def test_emergency_stop_after_model_response_prevents_persistence(reviewed_candidate,monkeypatch):
    store,_,artifact,_,_=reviewed_candidate
    def respondent(*args,**kwargs):
        store.emergency_stop_local(True,'Owner hit stop while chief was thinking')
        return 'SYNTHETIC response after stop'
    monkeypatch.setattr('desktop.chief_task_runtime.collect_chief_task_result',respondent)
    with pytest.raises(PermissionError,match='비상'):
        ops.collect_chief_review(store,artifact)
    assert store.find_chief_task_report(artifact) is None


@pytest.mark.parametrize('invalid', ['', ' ', '\x00', 'x'*10001, None, 5])
def test_bad_chief_text_rejected_with_no_report(reviewed_candidate,monkeypatch,invalid):
    store,_,artifact,_,_=reviewed_candidate
    monkeypatch.setattr('desktop.chief_task_runtime.collect_chief_task_result',
                        lambda *a,**kw:invalid)
    with pytest.raises(ValueError):ops.collect_chief_review(store,artifact)
    assert store.find_chief_task_report(artifact) is None


def test_bad_artifact_and_unauthenticated_user_rejected(reviewed_candidate):
    store,_,artifact,_,_=reviewed_candidate
    for invalid in (-1,0,'1',True,None):
        with pytest.raises(ValueError):ops.collect_chief_review(store,invalid)
    store.logout()
    with pytest.raises(AuthenticationError):ops.collect_chief_review(store,artifact)
    with pytest.raises(AuthenticationError):ops.review_chief_feedback(store,1,'accepted')


def test_non_chief_provenance_is_not_accepted(tmp_path,monkeypatch):
    store=LocalStore(tmp_path/'normal-worker.sqlite3')
    store.setup_owner('normal_worker_owner','owner-not-chief-test-pass')
    staff=store.add_employee_draft('just_staff','Staff only')
    mid=store.add_local_model(ModelConfig('synthetic', 'llamafile',sys.executable,'',24))
    store.set_employee_model(staff,mid)
    tid=ops.create_task(store,'no chief order')
    ops.assign_task(store,tid)
    monkeypatch.setattr('desktop.task_runtime.run_local_model',lambda *a,**kw:'STAFF ONLY SYNTHETIC')
    artifact=ops.execute_task(store,tid)['artifact_id']
    with pytest.raises(ValueError,match='승인된 총괄'):
        ops.collect_chief_review(store,artifact)
    assert store.find_chief_task_report(artifact) is None

def test_explicit_interruption_recovery_persists_without_duplicate_worker(reviewed_candidate, monkeypatch):
    """Crash after persisted worker output, restart owner session and run chief only."""
    store, tid, aid, _, _ = reviewed_candidate
    first_runs = store.list_task_runs(tid)
    first_artifacts = store.list_task_artifacts(tid)
    store.logout()
    restored = LocalStore(store.path)
    restored.login('report_owner', 'test-only-owner-password-2026')
    events = []
    def forbidden_worker(*args, **kwargs):
        events.append('worker-duplicate')
        raise AssertionError('Worker must never rerun during review recovery')
    def chief(_store, artifact_id, **kwargs):
        events.append(('chief-review-only', artifact_id))
        return 'SYNTHETIC RECOVERED CHIEF REVIEW, OWNER STILL DECIDES'
    monkeypatch.setattr('desktop.task_runtime.run_local_model', forbidden_worker)
    monkeypatch.setattr('desktop.chief_task_runtime.collect_chief_task_result', chief)
    recovered = ops.recover_interrupted_chief_review(restored, tid)
    assert recovered['artifact_id'] == aid
    assert recovered['recovered_saved_worker_result'] is True
    assert recovered['worker_reexecuted'] is False
    assert recovered['owner_approval_required'] is True
    assert events == [('chief-review-only', aid)]
    assert restored.list_task_runs(tid) == first_runs
    assert restored.list_task_artifacts(tid) == first_artifacts
    assert restored.find_chief_task_report(aid)['owner_decision'] == 'pending'
    assert restored.read_task(tid)['status'] == 'in_progress'
    with pytest.raises(ValueError, match='이미 총괄 AI 회수 보고서'):
        ops.recover_interrupted_chief_review(restored, tid)
    assert events == [('chief-review-only', aid)]


def test_interrupted_recovery_cancel_stop_and_wrong_state(reviewed_candidate, monkeypatch):
    store, tid, aid, _, _ = reviewed_candidate
    calls = []
    monkeypatch.setattr('desktop.chief_task_runtime.collect_chief_task_result',
                        lambda *a, **kw: calls.append('chief') or 'SYNTHETIC REPORT')
    for invalid in (0, True, -1, '1'):
        with pytest.raises(ValueError):
            ops.recover_interrupted_chief_review(store, invalid)
    cancelled = threading.Event(); cancelled.set()
    with pytest.raises(InterruptedError):
        ops.recover_interrupted_chief_review(store, tid, cancel=cancelled)
    assert store.find_chief_task_report(aid) is None
    store.emergency_stop_local(True, 'Owner forbids recovery until resumed')
    with pytest.raises(PermissionError, match='비상'):
        ops.recover_interrupted_chief_review(store, tid)
    assert calls == []


def test_interrupted_recovery_refuses_unapproved_or_missing_results(reviewed_candidate, monkeypatch):
    store, tid, aid, chief, worker = reviewed_candidate
    another = ops.create_task(store, 'No approved staff work')
    ops.assign_task(store, another)
    calls = []
    monkeypatch.setattr('desktop.chief_task_runtime.collect_chief_task_result',
                        lambda *a, **kw: calls.append('chief') or 'SYNTHETIC')
    with pytest.raises(ValueError):
        ops.recover_interrupted_chief_review(store, another)
    # A terminal task must not be re-opened merely by the recovery path.
    store.set_task_status(tid, 'blocked')
    with pytest.raises(ValueError, match='실행 중 중단'):
        ops.recover_interrupted_chief_review(store, tid)
    assert calls == []
