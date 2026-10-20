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


def _recovery_queue_tasks(tmp_path, monkeypatch):
    store=LocalStore(tmp_path/'batched-recovery.sqlite3')
    store.setup_owner('batch_recovery_owner','test-batch-recovery-password-2026')
    chief=store.add_employee_draft('batch_chief','Chief AI')
    worker=store.add_employee_draft('batch_worker','Worker AI')
    store.assign_reporting_line(chief,'ceo')
    model=store.add_local_model(ModelConfig('synthetic batch recovery', 'llamafile',
                                           sys.executable,'',24))
    store.set_employee_model(chief,model)
    store.set_employee_model(worker,model)
    monkeypatch.setattr('desktop.task_runtime.run_local_model',
                        lambda *a,**kw:'SYNTHETIC SAVED WORKER OUTPUT')
    tasks=[]
    for idx in range(3):
        tid=ops.create_task(store,f'Saved task for batch recovery {idx}')
        ops.assign_task(store,tid)
        ops.approve_chief_order(store,tid,'Owner approved bounded chief order')
        aid=ops.execute_task(store,tid)['artifact_id']
        tasks.append((tid,aid))
    return store,tasks


def test_recovery_candidate_listing_read_only_and_persistent(tmp_path,monkeypatch):
    store,tasks=_recovery_queue_tasks(tmp_path,monkeypatch)
    before=[store.list_task_runs(tid) for tid,_ in tasks]
    assert [(p['task_id'],p['artifact_id']) for p in
            ops.list_interrupted_chief_reviews(store)]==tasks
    assert len(ops.list_interrupted_chief_reviews(store,limit=2))==2
    assert [store.list_task_runs(tid) for tid,_ in tasks]==before
    store.logout()
    with pytest.raises(AuthenticationError):
        ops.list_interrupted_chief_reviews(store)
    reopened=LocalStore(store.path)
    reopened.login('batch_recovery_owner','test-batch-recovery-password-2026')
    assert len(ops.list_interrupted_chief_reviews(reopened))==3


def test_batch_chief_recovery_three_no_duplicate_staff_and_no_auto_approval(tmp_path,monkeypatch):
    store,tasks=_recovery_queue_tasks(tmp_path,monkeypatch)
    before=[store.list_task_runs(tid) for tid,_ in tasks]
    calls=[]
    def forbidden_worker(*args,**kwargs):
        raise AssertionError('Replayed worker during bounded chief-only recovery')
    def synthetic_chief(_store,artifact_id,**kwargs):
        calls.append(artifact_id)
        return f'SYNTHETIC CHIEF RE-REVIEW {artifact_id}'
    monkeypatch.setattr('desktop.task_runtime.run_local_model',forbidden_worker)
    monkeypatch.setattr('desktop.chief_task_runtime.collect_chief_task_result',synthetic_chief)
    out=ops.recover_interrupted_chief_review_queue(store)
    assert calls==[aid for _,aid in tasks]
    assert out['recovered_reviews']==3 and out['worker_reexecuted'] is False
    assert out['auto_approved'] is False and out['tasks_finalized'] is False
    for (tid,aid),runs in zip(tasks,before):
        assert store.list_task_runs(tid)==runs
        assert store.read_task(tid)['status']=='in_progress'
        assert store.read_task_artifact(aid)['review_status']=='pending'
        assert store.find_chief_task_report(aid)['owner_decision']=='pending'
    assert ops.list_interrupted_chief_reviews(store)==[]
    with pytest.raises(ValueError,match='중단 총괄 검토'):
        ops.recover_interrupted_chief_review_queue(store)
    assert len(calls)==3


def test_batch_chief_recovery_limits_cancel_and_emergency(tmp_path,monkeypatch):
    store,tasks=_recovery_queue_tasks(tmp_path,monkeypatch)
    for invalid in (0,4,True,-1,'2'):
        with pytest.raises(ValueError,match='1~3'):
            ops.recover_interrupted_chief_review_queue(store,limit=invalid)
    flag=threading.Event();flag.set()
    with pytest.raises(InterruptedError):
        ops.recover_interrupted_chief_review_queue(store,cancel=flag)
    store.emergency_stop_local(True,'Owner paused all local work')
    with pytest.raises(PermissionError,match='비상'):
        ops.recover_interrupted_chief_review_queue(store)
    # Read-only recovery status remains available while emergency stop is on.
    assert len(ops.list_interrupted_chief_reviews(store))==3
    assert all(store.find_chief_task_report(aid) is None for _,aid in tasks)


def test_batch_chief_recovery_stops_at_first_failed_model(tmp_path,monkeypatch):
    store,tasks=_recovery_queue_tasks(tmp_path,monkeypatch)
    calls=[]
    def chief(_store,artifact_id,**kwargs):
        calls.append(artifact_id)
        if len(calls)==2:
            raise RuntimeError('Synthetic chief failed, never retry automatically')
        return 'SYNTHETIC FIRST CHIEF SUCCESS'
    monkeypatch.setattr('desktop.chief_task_runtime.collect_chief_task_result',chief)
    with pytest.raises(RuntimeError,match='never retry'):
        ops.recover_interrupted_chief_review_queue(store)
    assert calls==[tasks[0][1],tasks[1][1]]
    assert store.find_chief_task_report(tasks[0][1]) is not None
    assert store.find_chief_task_report(tasks[1][1]) is None
    assert store.find_chief_task_report(tasks[2][1]) is None
    assert [p['task_id'] for p in ops.list_interrupted_chief_reviews(store)]==[
        tasks[1][0],tasks[2][0]]


def test_batch_chief_recovery_skips_already_reported_results(tmp_path,monkeypatch):
    store,tasks=_recovery_queue_tasks(tmp_path,monkeypatch)
    monkeypatch.setattr('desktop.chief_task_runtime.collect_chief_task_result',
                        lambda *args,**kwargs:'SYNTHETIC ALREADY-REVIEWED RESULT')
    ops.recover_interrupted_chief_review(store,tasks[0][0])
    assert [c['task_id'] for c in ops.list_interrupted_chief_reviews(store)]==[
        tasks[1][0],tasks[2][0]]
    result=ops.recover_interrupted_chief_review_queue(store,limit=3)
    assert result['recovered_reviews']==2
    assert result['task_ids']==[tasks[1][0],tasks[2][0]]
    assert all(store.find_chief_task_report(aid) is not None for _,aid in tasks)


def test_recovery_candidates_exclude_unexecuted_work(tmp_path,monkeypatch):
    store,tasks=_recovery_queue_tasks(tmp_path,monkeypatch)
    tid=ops.create_task(store,'Unexecuted candidate must not be recovered')
    ops.assign_task(store,tid)
    ops.approve_chief_order(store,tid,'Explicitly approved but still unexecuted')
    assert len(ops.list_interrupted_chief_reviews(store))==3
    with pytest.raises(ValueError):
        ops.recover_interrupted_chief_review(store,tid)
    for invalid in (0,True,-1,'3',101):
        with pytest.raises(ValueError):
            ops.list_interrupted_chief_reviews(store,limit=invalid)


def test_recovery_status_reveals_running_audits_without_closing_live_process(tmp_path,monkeypatch):
    """An unfinalized running row might be live. Never auto-terminate it."""
    store,tasks=_recovery_queue_tasks(tmp_path,monkeypatch)
    tid=ops.create_task(store,'Potentially still live model subprocess')
    ops.assign_task(store,tid)
    ops.approve_chief_order(store,tid,'Owner approved this pending worker')
    run_id,model,prompt=store.begin_task_execution(tid)
    before=store.list_task_runs(tid)
    summary=ops.inspect_recovery_state(store)
    assert [s['run_id'] for s in summary['running_worker_runs']]==[run_id]
    assert len(summary['pending_chief_reviews'])==3
    assert summary['requires_owner_process_confirmation'] is True
    assert summary['changed_task_state'] is False
    assert summary['auto_reran_worker'] is False
    assert store.list_task_runs(tid)==before
    assert store.read_task(tid)['status']=='in_progress'
    store.logout()
    with pytest.raises(AuthenticationError):
        ops.inspect_recovery_state(store)
    fresh=LocalStore(store.path)
    fresh.login('batch_recovery_owner','test-batch-recovery-password-2026')
    assert len(ops.inspect_recovery_state(fresh)['running_worker_runs'])==1
    # Existing storage provides an explicit (not automated) recovery action.
    fresh.recover_interrupted_task_run(run_id)
    assert fresh.read_task(tid)['status']=='blocked'
    assert ops.inspect_recovery_state(fresh)['running_worker_runs']==[]
    for old_tid,aid in tasks:
        assert fresh.read_task(old_tid)['status']=='in_progress'
        assert fresh.find_chief_task_report(aid) is None


def test_recovery_status_requires_owner_and_bounded_audit_window(tmp_path,monkeypatch):
    store,tasks=_recovery_queue_tasks(tmp_path,monkeypatch)
    for invalid in (0,True,-1,'3',201):
        with pytest.raises(ValueError,match='1~200'):
            ops.inspect_recovery_state(store,max_runs=invalid)
    state=ops.inspect_recovery_state(store,max_runs=1)
    assert state['run_scan_limit']==1
    assert state['running_worker_runs']==[]
    assert len(state['pending_chief_reviews'])==3
    assert all(store.find_chief_task_report(aid) is None for _,aid in tasks)


def test_owner_confirmed_recovery_queue_rejects_changed_candidates(tmp_path, monkeypatch):
    store, tasks = _recovery_queue_tasks(tmp_path, monkeypatch)
    approved = tuple(tid for tid, _ in tasks)
    calls = []
    monkeypatch.setattr('desktop.chief_task_runtime.collect_chief_task_result',
                        lambda *args, **kwargs: calls.append(args) or 'SYNTHETIC CHIEF')
    for invalid in ((), (True,), ('1',), (approved[0], approved[0]),
                    (approved[0], approved[1], approved[2], 999), [approved[0]]):
        with pytest.raises(ValueError, match='복구 업무 번호'):
            ops.recover_interrupted_chief_review_queue(
                store, limit=3, expected_task_ids=invalid)
    with pytest.raises(ValueError, match='복구 대상이 변경'):
        ops.recover_interrupted_chief_review_queue(
            store, limit=3, expected_task_ids=tuple(reversed(approved)))
    store.save_chief_task_report(tasks[0][1], 'SYNTHETIC REPORT FROM ANOTHER WINDOW')
    with pytest.raises(ValueError, match='복구 대상이 변경'):
        ops.recover_interrupted_chief_review_queue(
            store, limit=3, expected_task_ids=approved)
    assert calls == []
    assert all(store.find_chief_task_report(aid) is None for _, aid in tasks[1:])


def test_running_audit_survives_more_than_200_newer_successes(tmp_path, monkeypatch):
    store, tasks = _recovery_queue_tasks(tmp_path, monkeypatch)
    tid = ops.create_task(store, 'Old running worker needs explicit owner inspection')
    ops.assign_task(store, tid)
    ops.approve_chief_order(store, tid, 'Owner-approved task for crash recovery inspection')
    run_id, _, _ = store.begin_task_execution(tid)
    current = store.list_task_runs(tid)[0]
    with store._connect() as con:
        for _ in range(205):
            call_id = con.execute(
                """INSERT INTO ai_model_call_history
                   (employee_id,model_id,model_name,prompt_chars,status)
                   VALUES(?,?,?,?,?)""",
                (current['employee_id'], current['model_id'], 'SYNTHETIC', 10, 'success')
            ).lastrowid
            con.execute(
                """INSERT INTO company_task_runs
                   (task_id,employee_id,model_id,model_name,model_call_id,status,prompt_chars)
                   VALUES(?,?,?,?,?,?,?)""",
                (tid, current['employee_id'], current['model_id'],
                 'SYNTHETIC', call_id, 'success', 10))
    assert not any(r['id'] == run_id for r in store.list_task_runs(limit=200))
    state = ops.inspect_recovery_state(store, max_runs=1)
    assert [row['run_id'] for row in state['running_worker_runs']] == [run_id]
    assert state['running_worker_runs_truncated'] is False
    assert store.read_task(tid)['status'] == 'in_progress'
    store.logout()
    reopened = LocalStore(store.path)
    reopened.login('batch_recovery_owner', 'test-batch-recovery-password-2026')
    assert [row['run_id'] for row in ops.inspect_recovery_state(reopened)['running_worker_runs']] == [run_id]
    assert reopened.read_task(tid)['status'] == 'in_progress'


def test_owner_queue_does_not_continue_if_candidate_changes_mid_batch(tmp_path, monkeypatch):
    """Stop after the first persisted review if another session alters the queue."""
    store, tasks = _recovery_queue_tasks(tmp_path, monkeypatch)
    approved = tuple(tid for tid, _ in tasks)
    monkeypatch.setattr('desktop.chief_task_runtime.collect_chief_task_result',
                        lambda *args, **kwargs: 'SYNTHETIC CHIEF REPORT ONLY')
    original = ops.recover_interrupted_chief_review
    called = []
    def change_queue(current_store, task_id, **kwargs):
        result = original(current_store, task_id, **kwargs)
        called.append(task_id)
        if len(called) == 1:
            current_store.save_chief_task_report(
                tasks[1][1], 'SYNTHETIC OTHER WINDOW STORED A REPORT')
        return result
    monkeypatch.setattr(ops, 'recover_interrupted_chief_review', change_queue)
    with pytest.raises(ValueError, match='복구 대상이 실행 중 변경'):
        ops.recover_interrupted_chief_review_queue(
            store, limit=3, expected_task_ids=approved)
    assert called == [approved[0]]
    assert store.find_chief_task_report(tasks[0][1]) is not None
    assert store.find_chief_task_report(tasks[2][1]) is None
