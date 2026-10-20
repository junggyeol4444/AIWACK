"""Model-connection acceptance: no fake model, real local subprocess, audit, rollback."""
from __future__ import annotations
import os
import sys
import threading

import pytest
from desktop.storage import LocalStore, AuthenticationError
from desktop.model_runtime import ModelConfig
from desktop import company_operations as office


@pytest.fixture
def store(tmp_path):
    obj=LocalStore(tmp_path/'company.sqlite3')
    obj.setup_owner('windows_owner','proper-long-password-2026')
    return obj


def runnable_config(tmp_path):
    # Integration only: *real OS subprocess*, a synthetic text generator.
    # NOT a real GGUF inference test. Full GGUF requires the user's trusted
    # installed llama.cpp executable and real model weights.
    if os.name == 'nt':
        pytest.skip('Native Windows synthetic runner is exercised in EXE workflow')
    program=tmp_path/'diagnostic-runner'
    program.write_text(f'#!{sys.executable}\nimport sys\nprint("LOCAL_NATIVE_SUBPROCESS_OK")\n',encoding='utf-8')
    program.chmod(0o700)
    return ModelConfig('verified-subprocess','llamafile',str(program),'',32)


def test_real_subprocess_is_invoked_once_and_audited_without_task_or_sale(store,tmp_path):
    employee=store.add_employee_draft('real_employee','실제 실행 검사용 직원')
    model_id=office.connect_employee_model(store,employee,runnable_config(tmp_path))
    assert model_id > 0
    assert store.read_employee_model(employee)['model_id']==model_id
    assert store.list_task_artifacts()==[]
    assert store.list_employee_model_calls()==[]
    result=office.probe_employee_model(store,employee)
    assert result=='LOCAL_NATIVE_SUBPROCESS_OK'
    calls=store.list_employee_model_calls(employee)
    assert len(calls)==1 and calls[0]['status']=='success'
    assert store.list_task_artifacts()==[] and store.list_tasks()==[]
    assert not office.company_snapshot(store)['actual_sales_verified']


def test_cannot_probe_unregistered_or_empty_employee(store):
    employee=store.add_employee_draft('unconfigured','직원')
    with pytest.raises(ValueError,match='연결'):
        office.probe_employee_model(store,employee)
    assert store.list_employee_model_calls()==[]


def test_bad_path_never_creates_orphan_model(store,tmp_path):
    employee=store.add_employee_draft('unconfigured','직원')
    original=store.list_local_models()
    bad=ModelConfig('bad', 'llama_cpp',str(tmp_path/'nonexistent.exe'),str(tmp_path/'missing.gguf'),32)
    with pytest.raises(ValueError):
        office.connect_employee_model(store,employee,bad)
    assert store.list_local_models()==original
    assert store.read_employee_model(employee) is None


def test_id_validation_and_auth_fail_closed(store,tmp_path):
    config=runnable_config(tmp_path)
    for invalid in (True,0,-5,'1',None):
        with pytest.raises(ValueError):
            office.connect_employee_model(store,invalid,config)
    assert office.eligible_model_employees(store)==[]
    store.logout()
    with pytest.raises(AuthenticationError):
        office.eligible_model_employees(store)
    with pytest.raises(AuthenticationError):
        office.connect_employee_model(store,1,config)


def test_binding_twice_fails_and_preserves_original_model(store,tmp_path):
    employee=store.add_employee_draft('single_employee','직원')
    config=runnable_config(tmp_path)
    original=office.connect_employee_model(store,employee,config)
    before=store.list_local_models()
    with pytest.raises(ValueError,match='이미 모델'):
        office.connect_employee_model(store,employee,ModelConfig('second',config.backend,config.executable_path,'',32))
    assert store.read_employee_model(employee)['model_id']==original
    assert store.list_local_models()==before


def test_emergency_stop_blocks_probe_but_preserves_existing_binding(store,tmp_path):
    employee=store.add_employee_draft('healthy_employee','직원')
    model_id=office.connect_employee_model(store,employee,runnable_config(tmp_path))
    store.emergency_stop_local(True,'halt')
    with pytest.raises(PermissionError,match='비상'):
        office.probe_employee_model(store,employee)
    assert store.read_employee_model(employee)['model_id']==model_id
    assert store.list_employee_model_calls()==[]


def test_cancel_prior_to_execution_does_not_start_runner(store,tmp_path):
    employee=store.add_employee_draft('cancel_employee','직원')
    office.connect_employee_model(store,employee,runnable_config(tmp_path))
    cancel=threading.Event();cancel.set()
    with pytest.raises(InterruptedError):
        office.probe_employee_model(store,employee,cancel=cancel)
    assert store.list_employee_model_calls()==[]


def test_model_binding_rolls_back_on_failure(store,tmp_path,monkeypatch):
    employee=store.add_employee_draft('race_employee','직원')
    config=runnable_config(tmp_path)
    original=store.set_employee_model
    def always_fail(*args,**kwargs):
        raise ValueError('concurrent binding mutation')
    monkeypatch.setattr(store,'set_employee_model',always_fail)
    with pytest.raises(ValueError,match='concurrent'):
        office.connect_employee_model(store,employee,config)
    monkeypatch.setattr(store,'set_employee_model',original)
    assert store.list_local_models()==[]
    assert store.read_employee_model(employee) is None


def test_approved_real_staff_output_can_be_explicitly_finalized_once(store,tmp_path):
    employee=store.add_employee_draft('finish_worker','검수하는 직원')
    office.connect_employee_model(store,employee,runnable_config(tmp_path))
    task=office.create_task(store,'Complete after owner review')
    office.assign_task(store,task)
    output=office.execute_task(store,task)
    artifact=output['artifact_id']
    assert store.read_task(task)['status']=='in_progress'
    with pytest.raises(ValueError,match='승인'):
        office.finalize_approved_artifact(store,artifact)
    assert store.read_task(task)['status']=='in_progress'
    store.review_task_artifact(artifact,'approved')
    assert office.finalize_approved_artifact(store,artifact)==task
    assert store.read_task(task)['status']=='done'
    assert len(store.list_task_status_events(task))>=3
    with pytest.raises(ValueError,match='진행 중'):
        office.finalize_approved_artifact(store,artifact)


def test_cannot_complete_unrelated_or_invalid_artifact(store):
    for invalid in (True,0,-1,'1',None):
        with pytest.raises(ValueError):
            office.finalize_approved_artifact(store,invalid)
    with pytest.raises(ValueError,match='찾지'):
        office.finalize_approved_artifact(store,999999)
    store.logout()
    with pytest.raises(AuthenticationError):
        office.finalize_approved_artifact(store,1)

def test_emergency_stop_arriving_after_model_reply_refuses_probe_and_audits(store, tmp_path, monkeypatch):
    employee = store.add_employee_draft('late_stop_worker', '직원')
    office.connect_employee_model(store, employee, runnable_config(tmp_path))
    def respond(*args, **kwargs):
        store.emergency_stop_local(True, 'Owner clicked emergency stop mid-probe')
        return 'SYNTHETIC REPLY NEVER DISPLAYED'
    monkeypatch.setattr('desktop.employee_model_runtime.run_local_model', respond)
    with pytest.raises(PermissionError, match='비상'):
        office.probe_employee_model(store, employee)
    assert store.list_employee_model_calls(employee)[0]['status'] == 'failure'
    assert store.list_employee_model_calls(employee)[0]['output_chars'] == 0


def test_model_audit_atomic_guard_refuses_success_post_emergency_stop(store, tmp_path):
    employee = store.add_employee_draft('atomic_stop_worker', '직원')
    office.connect_employee_model(store, employee, runnable_config(tmp_path))
    call_id, _ = store.begin_employee_model_call(employee, 'SYNTHETIC prompt')
    store.emergency_stop_local(True, 'Late stop while model still running')
    with pytest.raises(PermissionError, match='비상'):
        store.finish_employee_model_call(call_id, 'success', output_chars=200)
    row = store.list_employee_model_calls(employee)[0]
    assert row['id'] == call_id and row['status'] == 'failure'
    assert row['output_chars'] == 0
