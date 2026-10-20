"""Stage 27: explicit owner-only local task runner, privacy and failure recovery."""
from __future__ import annotations

import os
import sqlite3
import sys
import threading
import time

import pytest

from desktop.model_runtime import ModelConfig
from desktop.storage import AuthenticationError, LocalStore
from desktop.task_runtime import invoke_task_execution


@pytest.fixture
def setup(tmp_path):
    db=LocalStore(tmp_path/'aiwack.sqlite3')
    db.setup_owner('local_owner_27','long-safe-passphrase-2026')
    staff=db.add_employee_draft('staff_stage27','로컬 AI 직원')
    task=db.add_task('시장 조사', '로컬에서 작성할 조사 초안')
    assert db.auto_assign_task(task)['employee_id']==staff
    runner=tmp_path/'trusted-local-cli'
    if os.name == 'nt':
        runner=__import__('pathlib').Path(sys.executable)
    else:
        runner.write_text('#!/usr/bin/env python3\nimport sys\nprint("LOCAL_RESULT: " + " ".join(sys.argv[1:]))\n',encoding='utf-8')
        runner.chmod(0o700)
    gguf=tmp_path/'test.gguf'
    gguf.write_bytes(b'GGUF\x03\x00\x00\x00')
    model=db.add_local_model(ModelConfig('test local model','llama_cpp',str(runner),str(gguf),10))
    return db,staff,task,model,runner,gguf


def bind(setup):
    db,staff,task,model,*_=setup
    db.set_employee_model(staff,model)
    return db,staff,task


def test_no_implicit_execution_and_preflight_deny_without_model(setup,monkeypatch):
    db,staff,task,*_=setup
    monkeypatch.setattr('desktop.task_runtime.run_local_model',lambda *a,**k: (_ for _ in ()).throw(AssertionError('spawned')))
    assert db.list_task_runs(task)==[]
    with pytest.raises(ValueError,match='모델'):
        invoke_task_execution(db,task)
    assert db.read_task(task)['status']=='todo'
    assert db.list_task_runs(task)==[]
    assert db.list_employee_model_calls(staff)==[]


def test_success_manual_status_and_no_output_persisted(setup,monkeypatch):
    db,staff,task=bind(setup)
    secret='SENSITIVE_RESPONSE_27_ABC'
    monkeypatch.setattr('desktop.task_runtime.run_local_model',lambda *a,**k: secret)
    assert invoke_task_execution(db,task)==secret
    row=db.list_task_runs(task)[0]
    assert row['status']=='success' and row['employee_id']==staff
    assert row['output_chars']==len(secret) and row['completed_at']
    assert db.read_task(task)['status']=='in_progress'  # NOT auto-done
    assert [e['new_status'] for e in db.list_task_status_events(task)]==['todo','in_progress']
    call=db.list_employee_model_calls(staff)[0]
    assert call['id']==row['model_call_id'] and call['status']=='success'
    assert secret.encode() not in db.path.read_bytes()
    db.logout()
    reopened=LocalStore(db.path)
    with pytest.raises(AuthenticationError):
        reopened.list_task_runs(task)
    reopened.login('local_owner_27','long-safe-passphrase-2026')
    assert reopened.list_task_runs(task)[0]['status']=='success'
    assert reopened.read_task(task)['status']=='in_progress'
    with pytest.raises(ValueError,match='이력'):
        reopened.delete_task(task)
    reopened.set_task_status(task,'done')
    assert reopened.read_task(task)['status']=='done'


def test_failed_execution_blocks_and_can_retry_explicitly(setup,monkeypatch):
    db,staff,task=bind(setup)
    def fail(*a,**kw):
        raise RuntimeError('PRIVATE_MODEL_ERROR_27')
    monkeypatch.setattr('desktop.task_runtime.run_local_model',fail)
    with pytest.raises(RuntimeError):
        invoke_task_execution(db,task)
    row=db.list_task_runs(task)[0]
    assert row['status']=='failure' and row['error_kind']=='RuntimeError'
    assert db.read_task(task)['status']=='blocked'
    assert b'PRIVATE_MODEL_ERROR_27' not in db.path.read_bytes()
    with pytest.raises(ValueError,match='할 일'):
        invoke_task_execution(db,task)
    db.set_task_status(task,'todo')
    monkeypatch.setattr('desktop.task_runtime.run_local_model',lambda *a,**kw:'retry-ok')
    assert invoke_task_execution(db,task)=='retry-ok'
    assert [r['status'] for r in db.list_task_runs(task)]==['success','failure']


def test_prerequisite_guard_and_owner_access(setup,monkeypatch):
    db,staff,task=bind(setup)
    prerequisite=db.add_task('선행 작업')
    db.add_task_dependency(task,prerequisite)
    monkeypatch.setattr('desktop.task_runtime.run_local_model',lambda *a,**kw:'OK')
    with pytest.raises(ValueError,match='선행'):
        invoke_task_execution(db,task)
    assert not db.list_task_runs(task)
    db.logout()
    for op in (lambda: db.begin_task_execution(task),lambda: db.list_task_runs(task),
               lambda: db.recover_interrupted_task_run(1)):
        with pytest.raises(AuthenticationError):
            op()
    db.login('local_owner_27','long-safe-passphrase-2026')
    db.set_task_status(prerequisite,'in_progress')
    db.set_task_status(prerequisite,'done')
    assert invoke_task_execution(db,task)=='OK'


def test_running_lock_prevents_concurrent_runs_mutation_and_status(setup):
    db,staff,task=bind(setup)
    run_id,config,prompt=db.begin_task_execution(task)
    assert '시장 조사' in prompt and '로컬' in prompt
    assert db.read_task(task)['status']=='in_progress'
    other=db.add_task('다른 업무')
    db.auto_assign_task(other)
    for op in (lambda: db.begin_task_execution(other),
               lambda: db.set_task_status(task,'done'),
               lambda: db.update_task(task,'변경')):
        with pytest.raises(ValueError):
            op()
    assert len(db.list_task_runs(task))==1
    db.finish_task_execution(run_id,'success',output_chars=3,duration_ms=5)
    with pytest.raises(ValueError,match='이미'):
        db.finish_task_execution(run_id,'success')
    assert db.read_task(task)['status']=='in_progress'


def test_running_employee_model_and_lifecycle_changes_denied(setup):
    db,staff,task=bind(setup)
    run_id,_,_=db.begin_task_execution(task)
    with pytest.raises(ValueError,match='실행 중'):
        db.set_employee_model(staff,None)
    with pytest.raises(ValueError,match='실행 중'):
        db.set_employee_inactive(staff)
    with pytest.raises(ValueError,match='실행 중'):
        db.update_employee_record(staff,'Changed')
    db.finish_task_execution(run_id,'cancelled',error_kind='InterruptedError')
    db.set_employee_model(staff,None)
    assert db.read_employee_model(staff) is None


def test_explicit_stale_recovery_no_autorestart(setup):
    db,staff,task=bind(setup)
    run_id,_,_=db.begin_task_execution(task)
    db.logout()
    reopened=LocalStore(db.path)
    reopened.login('local_owner_27','long-safe-passphrase-2026')
    assert reopened.list_task_runs(task)[0]['status']=='running'
    assert reopened.read_task(task)['status']=='in_progress'
    reopened.recover_interrupted_task_run(run_id)
    assert reopened.list_task_runs(task)[0]['status']=='interrupted'
    assert reopened.list_employee_model_calls(staff)[0]['status']=='failure'
    assert reopened.read_task(task)['status']=='blocked'
    with pytest.raises(ValueError):
        reopened.recover_interrupted_task_run(run_id)
    reopened.set_task_status(task,'todo')
    assert reopened.read_task(task)['status']=='todo'


@pytest.mark.parametrize('kind,exc', [('cancel',InterruptedError),('timeout',TimeoutError)])
def test_cancel_timeout_finalized(setup,monkeypatch,kind,exc):
    db,staff,task=bind(setup)
    def interrupted(*a,**kw):
        raise exc('private runtime diagnostic')
    monkeypatch.setattr('desktop.task_runtime.run_local_model',interrupted)
    with pytest.raises(exc):
        invoke_task_execution(db,task)
    expected='cancelled' if kind=='cancel' else 'timeout'
    assert db.list_task_runs(task)[0]['status']==expected
    assert db.list_employee_model_calls(staff)[0]['status']==expected
    assert db.read_task(task)['status']=='blocked'
    assert b'private runtime diagnostic' not in db.path.read_bytes()


def test_bad_inputs_and_audit_atomicity(setup):
    db,staff,task=bind(setup)
    for value in (True,0,121,'60'):
        with pytest.raises(ValueError):
            invoke_task_execution(db,task,timeout=value)
    assert not db.list_task_runs(task)
    for value in (0,True,999):
        with pytest.raises(ValueError):
            db.begin_task_execution(value)
    run_id,_,_=db.begin_task_execution(task)
    for status in ('invalid','running'):
        with pytest.raises(ValueError):
            db.finish_task_execution(run_id,status)
    with sqlite3.connect(db.path) as con:
        con.execute('''CREATE TRIGGER break_model_history BEFORE UPDATE ON ai_model_call_history
            BEGIN SELECT RAISE(ABORT,'simulated audit failure'); END''')
    with pytest.raises(sqlite3.IntegrityError):
        db.finish_task_execution(run_id,'success')
    assert db.list_task_runs(task)[0]['status']=='running'
    with sqlite3.connect(db.path) as con:
        con.execute('DROP TRIGGER break_model_history')
    db.finish_task_execution(run_id,'success')


def test_old_database_upgrade_no_implicit_run(setup):
    db,staff,task=bind(setup)
    path=db.path
    db.logout()
    fresh=LocalStore(path)
    fresh.login('local_owner_27','long-safe-passphrase-2026')
    assert fresh.list_task_runs(task)==[]
    assert fresh.read_task(task)['status']=='todo'
    assert fresh.read_task_routing(task)['employee_id']==staff


@pytest.mark.skipif(os.name=='nt',reason='Linux executable fixture; Windows EXE not built here')
def test_real_offline_subprocess_once_and_no_output_storage(setup):
    db,staff,task=bind(setup)
    response=invoke_task_execution(db,task,timeout=5)
    assert 'LOCAL_RESULT' in response and '시장 조사' in response
    assert db.list_task_runs(task)[0]['status']=='success'
    assert response.encode() not in db.path.read_bytes()

def test_worker_cancelled_after_native_reply_keeps_failed_audit_without_artifact(setup, monkeypatch):
    from desktop import company_operations as office
    db, employee, task = bind(setup)
    cancel = threading.Event()
    def respond(*args, **kwargs):
        cancel.set()
        return 'SYNTHETIC RESULTS NEVER ACCEPTED'
    monkeypatch.setattr('desktop.task_runtime.run_local_model', respond)
    with pytest.raises(InterruptedError):
        office.execute_task(db, task, cancel=cancel)
    assert db.list_task_artifacts(task) == []
    assert db.list_task_runs(task)[0]['status'] == 'cancelled'
    assert db.list_employee_model_calls(employee)[0]['status'] == 'cancelled'
    assert db.read_task(task)['status'] == 'blocked'


def test_worker_emergency_stop_after_native_reply_blocks_result_and_restart(setup, monkeypatch):
    from desktop import company_operations as office
    db, employee, task = bind(setup)
    def respond(*args, **kwargs):
        db.emergency_stop_local(True, 'Owner stopped worker execution')
        return 'SYNTHETIC MODEL RESULT NEVER APPROVED'
    monkeypatch.setattr('desktop.task_runtime.run_local_model', respond)
    with pytest.raises(PermissionError, match='비상'):
        office.execute_task(db, task)
    assert db.list_task_artifacts(task) == []
    assert db.list_task_runs(task)[0]['status'] == 'failure'
    assert db.list_employee_model_calls(employee)[0]['status'] == 'failure'
    assert db.read_task(task)['status'] == 'blocked'
    db.logout()
    reopened = LocalStore(db.path)
    reopened.login('local_owner_27', 'long-safe-passphrase-2026')
    assert reopened.list_task_artifacts(task) == []
    assert reopened.list_task_runs(task)[0]['status'] == 'failure'
    assert reopened.read_task(task)['status'] == 'blocked'


def test_artifact_save_refuses_emergency_stop_in_same_sql_transaction(setup):
    db, employee, task = bind(setup)
    run_id, _, _ = db.begin_task_execution(task)
    db.finish_task_execution(run_id, 'success', output_chars=4)
    db.emergency_stop_local(True, 'Stop before artifact save')
    with pytest.raises(PermissionError, match='비상'):
        db.save_task_artifact(task, run_id, 'blocked title', 'blocked result')
    assert db.list_task_artifacts(task) == []


def test_late_stop_inside_audit_commit_never_records_success(setup, monkeypatch):
    db, employee, task = bind(setup)
    run_id, _, _ = db.begin_task_execution(task)
    db.emergency_stop_local(True, 'Stop after reservation')
    with pytest.raises(PermissionError, match='비상'):
        db.finish_task_execution(run_id, 'success', output_chars=200)
    assert db.list_task_runs(task)[0]['status'] == 'failure'
    assert db.list_task_runs(task)[0]['output_chars'] == 0
    assert db.list_employee_model_calls(employee)[0]['status'] == 'failure'
    assert db.read_task(task)['status'] == 'blocked'
