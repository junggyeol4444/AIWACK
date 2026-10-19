"""Stage 29: bounded, independent offline task execution with isolated audits."""
from concurrent.futures import ThreadPoolExecutor
import os
import sqlite3
import threading
import time

import pytest

from desktop.model_runtime import ModelConfig
from desktop.storage import AuthenticationError, LocalStore, MAX_PARALLEL_TASK_RUNS
from desktop.task_runtime import invoke_task_execution


@pytest.fixture
def parallel(tmp_path):
    db = LocalStore(tmp_path / 'parallel.sqlite3')
    db.setup_owner('owner29', 'long-private-password-29')
    runner = tmp_path / 'local-runner'
    runner.write_text('#!/usr/bin/env python3\nimport sys,time\ntime.sleep(0.5)\nprint("OFFLINE_PARALLEL " + " ".join(sys.argv[1:]))\n', encoding='utf-8')
    runner.chmod(0o700)
    if os.name == 'nt':
        runner = __import__('pathlib').Path(__import__('sys').executable)
    gguf = tmp_path / 'test.gguf'
    gguf.write_bytes(b'GGUF\x03\x00\x00\x00')
    model = db.add_local_model(ModelConfig('offline-29', 'llama_cpp', str(runner), str(gguf), 8))
    tasks = []
    employees = []
    for i in range(3):
        employee = db.add_employee_draft(f'employee29_{i}', f'직원{i}')
        db.set_employee_model(employee, model)
        task = db.add_task(f'독립업무{i}', f'내용{i}')
        assert db.auto_assign_task(task)['employee_id'] == employee
        tasks.append(task)
        employees.append(employee)
    return db, tasks, employees, model


def test_two_reservations_atomic_and_third_denied(parallel):
    db, tasks, employees, model = parallel
    assert MAX_PARALLEL_TASK_RUNS == 2
    first, _, _ = db.begin_task_execution(tasks[0])
    second, _, _ = db.begin_task_execution(tasks[1])
    assert len([r for r in db.list_task_runs() if r['status'] == 'running']) == 2
    with pytest.raises(ValueError, match='한도'):
        db.begin_task_execution(tasks[2])
    assert db.read_task(tasks[2])['status'] == 'todo'
    assert db.list_task_runs(tasks[2]) == []
    with pytest.raises(ValueError):
        db.begin_task_execution(tasks[0])
    db.finish_task_execution(first, 'success', output_chars=10)
    third, _, _ = db.begin_task_execution(tasks[2])
    db.finish_task_execution(second, 'cancelled', error_kind='InterruptedError')
    db.finish_task_execution(third, 'success', output_chars=5)
    assert [db.read_task(t)['status'] for t in tasks] == ['in_progress','blocked','in_progress']
    assert [r['status'] for r in db.list_task_runs()] == ['success','cancelled','success']
    for task, employee in zip(tasks, employees):
        assert db.list_task_runs(task)[0]['employee_id'] == employee
        assert len(db.list_employee_model_calls(employee)) == 1
    with sqlite3.connect(db.path) as con:
        assert con.execute('PRAGMA foreign_key_check').fetchall() == []


def test_same_employee_cannot_run_twice(parallel):
    db, tasks, employees, _ = parallel
    # Route a second independent task to the same employee before the first starts.
    other = db.add_task('동일 직원 추가 업무')
    # Employee 0 has one assigned task; disable other employees from routing.
    db.set_employee_inactive(employees[1]); db.set_employee_inactive(employees[2])
    assert db.auto_assign_task(other)['employee_id'] == employees[0]
    first, _, _ = db.begin_task_execution(tasks[0])
    with pytest.raises(ValueError, match='같은 AI 직원'):
        db.begin_task_execution(other)
    assert db.list_task_runs(other) == []
    db.finish_task_execution(first, 'success')
    second, _, _ = db.begin_task_execution(other)
    db.finish_task_execution(second, 'success')


def test_dependency_blocks_parallel_successor(parallel):
    db, tasks, _, _ = parallel
    db.add_task_dependency(tasks[1], tasks[0])
    first, _, _ = db.begin_task_execution(tasks[0])
    with pytest.raises(ValueError, match='선행'):
        db.begin_task_execution(tasks[1])
    db.finish_task_execution(first, 'success')
    with pytest.raises(ValueError, match='선행'):
        db.begin_task_execution(tasks[1])
    db.set_task_status(tasks[0], 'done')
    second, _, _ = db.begin_task_execution(tasks[1])
    db.finish_task_execution(second, 'success')


def test_parallel_real_workers_and_cancel_isolation(parallel, monkeypatch):
    db, tasks, employees, model = parallel
    entered = set()
    lock = threading.Lock()
    both_started = threading.Event()
    release = threading.Event()
    def fake_run(config, prompt, *, timeout, cancel):
        with lock:
            entered.add(prompt.split('업무 제목: ')[-1].splitlines()[0])
            if len(entered) == 2:
                both_started.set()
        assert release.wait(5)
        if cancel.is_set():
            raise InterruptedError('cancelled')
        return 'RESPONSE29:' + prompt.split('업무 제목: ')[-1]
    monkeypatch.setattr('desktop.task_runtime.run_local_model', fake_run)
    cancel_one = threading.Event()
    cancel_two = threading.Event()
    with ThreadPoolExecutor(max_workers=2) as pool:
        a = pool.submit(invoke_task_execution, db, tasks[0], cancel=cancel_one)
        b = pool.submit(invoke_task_execution, db, tasks[1], cancel=cancel_two)
        assert both_started.wait(5), 'Both workers should run concurrently'
        assert len([r for r in db.list_task_runs() if r['status'] == 'running']) == 2
        cancel_one.set()
        release.set()
        with pytest.raises(InterruptedError):
            a.result(timeout=5)
        assert 'RESPONSE29:' in b.result(timeout=5)
    assert db.list_task_runs(tasks[0])[0]['status'] == 'cancelled'
    assert db.list_task_runs(tasks[1])[0]['status'] == 'success'
    assert db.read_task(tasks[0])['status'] == 'blocked'
    assert db.read_task(tasks[1])['status'] == 'in_progress'
    assert b'RESPONSE29:' not in db.path.read_bytes()


def test_simultaneous_reservations_never_exceed_cap(parallel):
    db, tasks, _, _ = parallel
    barrier = threading.Barrier(3)
    def reserve(task):
        barrier.wait(timeout=5)
        try:
            return db.begin_task_execution(task)[0]
        except ValueError:
            return None
    with ThreadPoolExecutor(max_workers=3) as pool:
        futures = [pool.submit(reserve, t) for t in tasks]
        values = [f.result(timeout=10) for f in futures]
    assert sum(v is not None for v in values) == 2
    for run in values:
        if run is not None:
            db.finish_task_execution(run, 'success')


def test_old_single_flight_index_migrated_preserving_running_record(parallel):
    db, tasks, _, _ = parallel
    # Emulate the legacy Stage 28 index on an existing DB.
    with sqlite3.connect(db.path) as con:
        con.execute('DROP INDEX task_runs_task_running_idx')
        con.execute('DROP INDEX task_runs_employee_running_idx')
        con.execute("CREATE UNIQUE INDEX task_runs_one_running_idx ON company_task_runs((1)) WHERE status='running'")
    old, _, _ = db.begin_task_execution(tasks[0])
    reopened = LocalStore(db.path)
    reopened.login('owner29', 'long-private-password-29')
    with sqlite3.connect(db.path) as con:
        indexes = {row[1] for row in con.execute("PRAGMA index_list('company_task_runs')")}
    assert 'task_runs_one_running_idx' not in indexes
    assert {'task_runs_task_running_idx', 'task_runs_employee_running_idx'} <= indexes
    assert reopened.list_task_runs(tasks[0])[0]['status'] == 'running'
    new, _, _ = reopened.begin_task_execution(tasks[1])
    reopened.finish_task_execution(old, 'interrupted', error_kind='RuntimeError')
    reopened.finish_task_execution(new, 'success')


def test_running_model_config_protected(parallel):
    db, tasks, _, model = parallel
    first, _, _ = db.begin_task_execution(tasks[0])
    current = db.read_local_model(model)
    with pytest.raises(ValueError, match='실행 중'):
        db.update_local_model(model, ModelConfig('changed', 'llama_cpp', current['executable_path'], current['model_path'], 8))
    with pytest.raises(ValueError, match='실행 중'):
        db.delete_local_model(model)
    db.finish_task_execution(first, 'success')


def test_owner_access_and_independent_recovery(parallel):
    db, tasks, _, _ = parallel
    a, _, _ = db.begin_task_execution(tasks[0])
    b, _, _ = db.begin_task_execution(tasks[1])
    db.logout()
    with pytest.raises(AuthenticationError):
        db.begin_task_execution(tasks[2])
    reopened = LocalStore(db.path)
    reopened.login('owner29', 'long-private-password-29')
    reopened.recover_interrupted_task_run(a)
    assert reopened.list_task_runs(tasks[1])[0]['status'] == 'running'
    assert reopened.read_task(tasks[0])['status'] == 'blocked'
    reopened.finish_task_execution(b, 'success')


@pytest.mark.skipif(os.name == 'nt', reason='Linux executable fixture, Windows EXE not built')
def test_real_two_local_subprocesses_overlap(parallel):
    db, tasks, _, _ = parallel
    start = time.monotonic()
    with ThreadPoolExecutor(max_workers=2) as pool:
        a = pool.submit(invoke_task_execution, db, tasks[0], timeout=5)
        b = pool.submit(invoke_task_execution, db, tasks[1], timeout=5)
        assert 'OFFLINE_PARALLEL' in a.result(timeout=8)
        assert 'OFFLINE_PARALLEL' in b.result(timeout=8)
    duration = time.monotonic() - start
    assert duration < 1.5, f'Unexpected serialized execution: {duration:.2f}s'
    assert all(db.list_task_runs(t)[0]['status'] == 'success' for t in tasks[:2])
