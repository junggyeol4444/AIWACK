"""Owner-confirmed two-employee parallel work, sequential chief reviews; synthetic models."""
from __future__ import annotations
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
import pytest
from desktop.model_runtime import ModelConfig
from desktop.storage import LocalStore
from desktop import company_operations as ops


@pytest.fixture
def parallel_office(tmp_path):
    store = LocalStore(tmp_path / 'approved-parallel.sqlite3')
    store.setup_owner('parallel_owner', 'parallel-test-password-2026')
    chief = store.add_employee_draft('parallel_ceo', '총괄 AI')
    staff = [store.add_employee_draft(f'parallel_{i}', f'직원 {i}') for i in range(2)]
    store.assign_reporting_line(chief, 'ceo')
    model = store.add_local_model(ModelConfig('SYNTHETIC-no-real-gguf', 'llamafile', sys.executable, '', 32))
    for emp in [chief] + staff:
        store.set_employee_model(emp, model)
    ids = []
    for i in range(2):
        tid = ops.create_task(store, f'Independent approved work {i}')
        assert ops.assign_task(store, tid)['employee_id'] == staff[i]
        ops.approve_chief_order(store, tid, f'Owner approved instruction {i}')
        ids.append(tid)
    return store, tuple(ids), tuple(staff)


def test_two_staff_actually_overlap_chief_sequential_and_restart_persists(parallel_office, monkeypatch):
    store, ids, staff = parallel_office
    barrier = threading.Barrier(2)
    entered = []
    lock = threading.Lock()
    chief_calls = []
    def worker(config, prompt, *, timeout, cancel):
        with lock:
            entered.append(prompt)
        barrier.wait(timeout=12)
        assert not cancel.is_set()
        return 'SYNTHETIC INDEPENDENT STAFF OUTPUT'
    def chief(_store, artifact_id, **kwargs):
        chief_calls.append((artifact_id, threading.current_thread().name))
        return 'SYNTHETIC CHIEF FEEDBACK'
    monkeypatch.setattr('desktop.task_runtime.run_local_model', worker)
    monkeypatch.setattr('desktop.chief_task_runtime.collect_chief_task_result', chief)
    candidates = ops.list_approved_parallel_candidates(store)
    assert tuple(c['task_id'] for c in candidates) == ids
    assert [c['employee_id'] for c in candidates] == list(staff)
    assert store.list_task_runs() == []
    outcome = ops.execute_approved_parallel_cycle(store, expected_task_ids=ids, expected_employee_ids=staff)
    assert outcome['staff_execution_parallel'] is True
    assert outcome['staff_executions'] == outcome['chief_reviews'] == 2
    assert outcome['auto_approved'] is False and outcome['tasks_finalized'] is False
    assert len(entered) == 2 and len(chief_calls) == 2
    assert all(name == threading.current_thread().name for _, name in chief_calls)
    for tid in ids:
        art = store.list_task_artifacts(tid)[0]
        assert store.list_task_runs(tid)[0]['status'] == 'success'
        assert store.find_chief_task_report(art['id'])['owner_decision'] == 'pending'
        assert store.read_task(tid)['status'] == 'in_progress'
    store.logout()
    restarted = LocalStore(store.path)
    restarted.login('parallel_owner', 'parallel-test-password-2026')
    for tid in ids:
        art_id = restarted.list_task_artifacts(tid)[0]['id']
        assert restarted.find_chief_task_report(art_id)['owner_decision'] == 'pending'
    with pytest.raises(ValueError):
        ops.execute_approved_parallel_cycle(restarted, expected_task_ids=ids, expected_employee_ids=staff)


def test_wrong_owner_list_and_unapproved_work_never_starts(parallel_office, monkeypatch):
    store, ids, staff = parallel_office
    calls = []
    monkeypatch.setattr('desktop.task_runtime.run_local_model',
                        lambda *a, **kw: calls.append('worker') or 'SYNTHETIC')
    for wrong in ((), (ids[0],), [ids[0], ids[1]], (ids[0], ids[0]), (True, ids[1]), tuple(reversed(ids))):
        with pytest.raises(ValueError):
            ops.execute_approved_parallel_cycle(store, expected_task_ids=wrong, expected_employee_ids=staff)
    other = ops.create_task(store, 'Unapproved external task')
    store.auto_assign_task(other)
    assert len(ops.list_approved_parallel_candidates(store)) == 2
    with pytest.raises(ValueError, match='담당 직원이 변경'):
        ops.execute_approved_parallel_cycle(store, expected_task_ids=ids,
                                            expected_employee_ids=tuple(reversed(staff)))
    with pytest.raises(ValueError, match='담당 직원'):
        ops.execute_approved_parallel_cycle(store, expected_task_ids=ids,
                                            expected_employee_ids=(staff[0], staff[0]))
    assert calls == [] and store.list_task_runs() == []
    cancelled = threading.Event()
    cancelled.set()
    with pytest.raises(InterruptedError):
        ops.execute_approved_parallel_cycle(store, expected_task_ids=ids, expected_employee_ids=staff, cancel=cancelled)
    assert calls == []


def test_one_worker_failure_requests_peer_cancel_without_chief_or_unapproved_run(parallel_office, monkeypatch):
    store, ids, staff = parallel_office
    barrier = threading.Barrier(2)
    calls = []
    def broken(config, prompt, *, timeout, cancel):
        barrier.wait(timeout=12)
        if 'work 0' in prompt:
            raise RuntimeError('SYNTHETIC FIRST STAFF FAILURE')
        assert cancel.wait(timeout=12), 'Peer must observe shared stop after failure'
        raise InterruptedError('SYNTHETIC PEER CANCELLED')
    monkeypatch.setattr('desktop.task_runtime.run_local_model', broken)
    monkeypatch.setattr('desktop.chief_task_runtime.collect_chief_task_result',
                        lambda *a, **kw: calls.append('chief') or 'NEVER')
    with pytest.raises(RuntimeError, match='후속 총괄 AI를 실행하지 않았습니다'):
        ops.execute_approved_parallel_cycle(store, expected_task_ids=ids, expected_employee_ids=staff)
    assert calls == []
    assert all(store.list_task_artifacts(tid) == [] for tid in ids)
    assert {store.list_task_runs(tid)[0]['status'] for tid in ids} == {'failure','cancelled'}
    assert all(store.read_task(tid)['status'] == 'blocked' for tid in ids)


def test_emergency_stop_during_parallel_workers_never_saves_any_artifact(parallel_office, monkeypatch):
    store, ids, staff = parallel_office
    barrier = threading.Barrier(2)
    def worker(config, prompt, *, timeout, cancel):
        barrier.wait(timeout=12)
        store.emergency_stop_local(True, 'owner stopping concurrent tasks')
        return 'SYNTHETIC MODEL RESULT SHOULD BE DISCARDED'
    monkeypatch.setattr('desktop.task_runtime.run_local_model', worker)
    monkeypatch.setattr('desktop.chief_task_runtime.collect_chief_task_result',
                        lambda *a, **kw: (_ for _ in ()).throw(AssertionError('chief ran after stop')))
    with pytest.raises(PermissionError, match='비상'):
        ops.execute_approved_parallel_cycle(store, expected_task_ids=ids, expected_employee_ids=staff)
    assert all(store.list_task_artifacts(tid) == [] for tid in ids)
    statuses = [store.list_task_runs(tid)[0]['status'] for tid in ids]
    # The peer may see shared cancellation before it tries to commit its result.
    # Both statuses are safe, but neither may be marked successful.
    assert set(statuses) <= {'failure', 'cancelled'}
    assert 'failure' in statuses

def test_parallel_preview_skips_unfinished_dependencies_before_owner_confirmation(parallel_office):
    store, ids, staff = parallel_office
    # The second task cannot run until the first is separately approved done.
    store.add_task_dependency(ids[1], ids[0])
    third_employee = store.add_employee_draft('parallel_alternative', '대체 직원')
    model_id = store.read_employee_model(staff[0])['model_id']
    store.set_employee_model(third_employee, model_id)
    third_id = ops.create_task(store, 'Independent third available task')
    assert ops.assign_task(store, third_id)['employee_id'] == third_employee
    ops.approve_chief_order(store, third_id, 'Owner signed third instruction')
    preview = ops.list_approved_parallel_candidates(store)
    assert [row['task_id'] for row in preview] == [ids[0], third_id]
    assert [row['employee_id'] for row in preview] == [staff[0], third_employee]
    assert all(store.list_task_runs(tid) == [] for tid in (*ids, third_id))


def test_parallel_staff_evidence_must_match_saved_model_and_owner_approval(
        parallel_office, monkeypatch):
    """Mock output only; real SQLite model-call and artifact linkage is checked."""
    store, ids, staff = parallel_office
    monkeypatch.setattr('desktop.task_runtime.run_local_model',
                        lambda *a, **k: 'SYNTHETIC STAFF DRAFT FOR LOCAL AUDIT')
    result = ops.execute_task(store, ids[0])
    proof = ops._verified_parallel_worker_result(store, ids[0], staff[0], result)
    assert proof['verified_saved_real_model_result'] is True
    assert proof['owner_approval_pending'] is True
    assert proof['artifact_id'] == result['artifact_id']
    with pytest.raises(ValueError, match='승인 원본'):
        ops._verified_parallel_worker_result(store, ids[0], staff[1], result)
    with store._connect() as con:
        con.execute('UPDATE company_task_artifacts SET body=? WHERE id=?',
                    ('LOCAL ARTIFACT CORRUPTION', result['artifact_id']))
    with pytest.raises(ValueError, match='SHA256'):
        ops._verified_parallel_worker_result(store, ids[0], staff[0], result)


def test_parallel_staff_model_binding_changed_before_chief_is_rejected(
        parallel_office, monkeypatch):
    store, ids, staff = parallel_office
    monkeypatch.setattr('desktop.task_runtime.run_local_model',
                        lambda *a, **k: 'SYNTHETIC STAFF OUTPUT FOR LOCAL AUDIT')
    output = ops.execute_task(store, ids[0])
    alternate = store.add_local_model(ModelConfig(
        'DIFFERENT-SYNTHETIC-MODEL', 'llamafile', sys.executable, '', 32))
    store.set_employee_model(staff[0], alternate)
    with pytest.raises(ValueError, match='모델 배정 원본'):
        ops._verified_parallel_worker_result(store, ids[0], staff[0], output)
