"""Real owner/workflow integration for the first-screen AI company operations center."""
import os
import sys
import threading
import pytest
from desktop.storage import LocalStore, AuthenticationError
from desktop.model_runtime import ModelConfig
from desktop import company_operations as ops


@pytest.fixture
def owner(tmp_path):
    store=LocalStore(tmp_path/'office.sqlite3')
    store.setup_owner('office_owner','office-owner-long-password-2026')
    return store


def test_empty_company_shows_unconfigured_instead_of_fake_ai(owner):
    status=ops.company_snapshot(owner)
    assert status['team']==[] and status['chief'] is None
    assert status['total_tasks']==0 and not status['live_model_ready']
    assert not status['actual_sales_verified']


def test_creating_task_and_real_staff_assignment(owner):
    staff=owner.add_employee_draft('office_staff','AI Researcher')
    task=ops.create_task(owner,'Research customers','Market opportunity research')
    assignment=ops.assign_task(owner,task)
    assert assignment['employee_id']==staff
    status=ops.company_snapshot(owner)
    assert status['tasks'][0]['assignee']=='AI Researcher'
    assert status['tasks'][0]['status']=='todo'
    assert not owner.list_task_runs(task)


def test_no_model_no_fake_completion(owner):
    owner.add_employee_draft('office_staff','AI Researcher')
    task=ops.create_task(owner,'Research customers')
    ops.assign_task(owner,task)
    with pytest.raises(ValueError, match='모델'):
        ops.execute_task(owner,task)
    assert owner.read_task(task)['status']=='todo'
    assert owner.list_task_artifacts(task)==[]


def test_genuine_local_model_call_persists_immutable_draft(owner,monkeypatch,tmp_path):
    staff=owner.add_employee_draft('office_staff','AI Researcher')
    task=ops.create_task(owner,'Research customers')
    ops.assign_task(owner,task)
    runner=tmp_path/'ai-model'
    if os.name=='nt':runner=__import__('pathlib').Path(sys.executable)
    else:
        runner.write_text('mock',encoding='utf-8')
        runner.chmod(0o755)
    gguf=tmp_path/'small.gguf';gguf.write_bytes(b'GGUF\x03\x00\x00\x00')
    mid=owner.add_local_model(ModelConfig('Local Model','llama_cpp',str(runner),str(gguf),25))
    owner.set_employee_model(staff,mid)
    calls=[]
    def real_adapter(config,prompt,**kwargs):
        calls.append((config,prompt))
        return 'A real local model result from configured adapter'
    monkeypatch.setattr('desktop.task_runtime.run_local_model',real_adapter)
    result=ops.execute_task(owner,task)
    assert len(calls)==1 and calls[0][0].name=='Local Model'
    assert result['status']=='awaiting_owner_review'
    assert owner.read_task(task)['status']=='in_progress'
    art=owner.list_task_artifacts(task)
    assert len(art)==1 and art[0]['id']==result['artifact_id']
    assert owner.read_task_artifact(art[0]['id'])['body']==result['response']
    assert owner.list_task_runs(task)[0]['status']=='success'
    with pytest.raises(ValueError):
        ops.execute_task(owner,task)


def test_emergency_stop_blocks_legacy_direct_and_office_model_start(owner):
    owner.add_employee_draft('office_staff','AI Researcher')
    task=ops.create_task(owner,'Research customers')
    owner.auto_assign_task(task)
    owner.emergency_stop_local(True,'Owner blocked all future starts')
    assert ops.company_snapshot(owner)['emergency'] is True
    with pytest.raises(PermissionError,match='비상'):
        ops.assign_task(owner,task)
    with pytest.raises(PermissionError,match='비상'):
        ops.execute_task(owner,task)
    with pytest.raises(PermissionError,match='비상'):
        owner.begin_task_execution(task)
    with pytest.raises(PermissionError,match='비상'):
        owner.begin_employee_model_call(1,'hello')
    assert owner.list_task_runs(task)==[]
    owner.emergency_stop_local(False,'Owner explicitly released')
    assert ops.company_snapshot(owner)['emergency'] is False


def test_batch_is_explicit_bounded_and_reports_blocked_without_claiming_sales(owner):
    owner.add_employee_draft('office_staff','AI Researcher')
    for i in range(4):ops.create_task(owner,'Task '+str(i))
    assert len(owner.list_tasks())==4
    result=ops.execute_batch(owner,max_tasks=2)
    assert len(result)==2 and all(item['status']=='blocked' for item in result)
    assert all(row['status']=='todo' for row in owner.list_tasks())
    assert owner.list_task_artifacts()==[]
    with pytest.raises(ValueError):ops.execute_batch(owner,max_tasks=15)


def test_owner_auth_and_input_guards(owner):
    for invalid in ['', ' ', 'x'*121]:
        with pytest.raises(ValueError): ops.create_task(owner,invalid)
    with pytest.raises(ValueError):ops.create_task(owner,'valid',description='x'*1501)
    owner.logout()
    with pytest.raises(AuthenticationError):ops.company_snapshot(owner)
    with pytest.raises(AuthenticationError):ops.create_task(owner,'unprivileged')
    with pytest.raises(AuthenticationError):ops.execute_batch(owner)


def test_cancel_prior_to_start(owner):
    flag=threading.Event();flag.set()
    with pytest.raises(InterruptedError):ops.execute_task(owner,1,cancel=flag)


def test_after_restart_real_task_assignment_persists(owner):
    staff=owner.add_employee_draft('office_staff','AI Researcher')
    task=ops.create_task(owner,'Persistent project')
    ops.assign_task(owner,task)
    owner.logout()
    store=LocalStore(owner.path)
    with pytest.raises(AuthenticationError):ops.company_snapshot(store)
    store.login('office_owner','office-owner-long-password-2026')
    snapshot=ops.company_snapshot(store)
    assert snapshot['tasks'][0]['assignee']=='AI Researcher'
    assert snapshot['team'][0]['id']==staff


def test_create_original_fifteen_department_chief_head_staff_blueprint(owner):
    result=ops.initialize_company_blueprint(owner)
    assert result['departments']==15 and result['draft_ai_profiles']==31
    assert result['real_model_calls']==0
    data=ops.company_snapshot(owner)
    assert len(data['departments'])==15 and len(data['team'])==31
    assert data['chief']['model_id'] is None
    assert not data['live_model_ready']
    lines=owner.list_reporting_lines()
    assert [row['tier'] for row in lines].count('ceo')==1
    assert [row['tier'] for row in lines].count('department_head')==15
    assert [row['tier'] for row in lines].count('staff')==15
    with pytest.raises(ValueError,match='기존'):
        ops.initialize_company_blueprint(owner)
    assert len(owner.list_employee_records())==31


def test_blueprint_refuses_to_overwrite_any_existing_org(owner):
    owner.add_department('내 조직')
    with pytest.raises(ValueError):ops.initialize_company_blueprint(owner)
    assert [x['name'] for x in owner.list_departments()]==['내 조직']


def test_cockpit_uses_real_review_queue_and_model_binding(owner, monkeypatch, tmp_path):
    staff = owner.add_employee_draft('chief_staff', 'QA analyst')
    task_id = ops.create_task(owner, 'Release candidate QA')
    ops.assign_task(owner, task_id)
    runner = tmp_path / 'runner'
    if os.name == 'nt':
        runner = __import__('pathlib').Path(sys.executable)
    else:
        runner.write_text('test adapter runner')
        runner.chmod(0o700)
    gguf = tmp_path / 'local.gguf'
    gguf.write_bytes(b'GGUF\x03\x00\x00\x00')
    model_id = owner.add_local_model(ModelConfig('QA model', 'llama_cpp', str(runner), str(gguf), 20))
    owner.set_employee_model(staff, model_id)
    monkeypatch.setattr('desktop.task_runtime.run_local_model',
                        lambda config, prompt, **kwargs: 'Actual adapter text for owner review')
    output = ops.execute_task(owner, task_id)
    dashboard = ops.company_snapshot(owner)
    assert dashboard['model_ready_count'] == 1
    assert dashboard['pending_reviews'] == 1
    assert dashboard['recent_artifacts'][0]['id'] == output['artifact_id']
    assert dashboard['actual_sales_verified'] is False
    owner.review_task_artifact(output['artifact_id'], 'approved')
    refreshed = ops.company_snapshot(owner)
    assert refreshed['pending_reviews'] == 0
    assert refreshed['recent_artifacts'][0]['review_status'] == 'approved'
    assert owner.read_task(task_id)['status'] != 'done'
