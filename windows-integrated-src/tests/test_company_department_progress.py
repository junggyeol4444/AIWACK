"""다부서 실제 SQLite 승인 단계, 직원+총괄 호출 및 안전 회귀."""
import pytest
from desktop.storage import LocalStore
from desktop import company_department_collaboration as chain
from desktop import company_department_progress as progress
from desktop import company_operations as ops
from test_company_department_collaboration import _office


def _approved(tmp_path, monkeypatch):
    db,source,_=_office(tmp_path,monkeypatch)
    draft=chain.propose(db,source)
    assert not progress.next_step(db,draft['id'])['ready']
    return db,chain.approve(db,draft['id'])


def test_actual_two_department_execution_owner_review_and_restart(tmp_path,monkeypatch):
    db,plan=_approved(tmp_path,monkeypatch)
    first=progress.next_step(db,plan['id'])
    assert first['ready'] and first['ordinal']==1
    monkeypatch.setattr('desktop.task_runtime.run_local_model',
                        lambda *a,**k:'실제 SQLite에 저장되는 직원 결과')
    monkeypatch.setattr('desktop.chief_task_runtime.collect_chief_task_result',
                        lambda *a,**k:'총괄 모델 검토 기록')
    result=progress.execute_next_step(db,plan['id'],first['task_id'],first['employee_id'])
    assert db.read_task_artifact(result['artifact_id'])['review_status']=='pending'
    assert not progress.next_step(db,plan['id'])['ready']
    with pytest.raises(ValueError):
        progress.execute_next_step(db,plan['id'],first['task_id'],first['employee_id'])
    db.review_task_artifact(result['artifact_id'],'approved')
    db.review_chief_task_report(result['report_id'],'accepted')
    ops.finalize_approved_artifact(db,result['artifact_id'])
    reopened=LocalStore(db.path)
    reopened.login('tester','a'*24)
    second=progress.next_step(reopened,plan['id'])
    assert second['ready'] and second['ordinal']==2
    second_result=progress.execute_next_step(
        reopened,plan['id'],second['task_id'],second['employee_id'])
    assert reopened.read_task_artifact(second_result['artifact_id'])['review_status']=='pending'
    assert not progress.next_step(reopened,plan['id'])['ready']
    assert len(reopened.list_task_runs())==2
    assert '실제 결과물 1건' in progress.report(reopened,plan['id'])


def test_changed_confirmed_task_or_employee_never_executes(tmp_path,monkeypatch):
    db,plan=_approved(tmp_path,monkeypatch)
    step=progress.next_step(db,plan['id'])
    def forbidden(*args,**kwargs):
        raise AssertionError('승인하지 않은 모델 실행 금지')
    monkeypatch.setattr('desktop.task_runtime.run_local_model',forbidden)
    for task,employee in ((step['task_id']+100,step['employee_id']),
                          (step['task_id'],step['employee_id']+100)):
        with pytest.raises(ValueError):
            progress.execute_next_step(db,plan['id'],task,employee)
    assert db.list_task_runs()==[]


def test_emergency_stop_and_assignment_change_block(tmp_path,monkeypatch):
    db,plan=_approved(tmp_path,monkeypatch)
    stage=progress.next_step(db,plan['id'])
    db.emergency_stop_local(True,'Owner emergency stop')
    with pytest.raises(PermissionError):
        progress.execute_next_step(db,plan['id'],stage['task_id'],stage['employee_id'])
    db.emergency_stop_local(False,'Owner resumed')
    db.clear_task_assignment(stage['task_id'])
    assert not progress.next_step(db,plan['id'])['ready']
    with pytest.raises(ValueError):
        progress.execute_next_step(db,plan['id'],stage['task_id'],stage['employee_id'])
    assert db.list_task_runs()==[]


def test_invalid_plan_and_cancelled_before_start(tmp_path,monkeypatch):
    import threading
    db,plan=_approved(tmp_path,monkeypatch)
    stage=progress.next_step(db,plan['id'])
    for invalid in (True,0,'1'):
        with pytest.raises(ValueError):
            progress.execute_next_step(db,invalid,stage['task_id'],stage['employee_id'])
    event=threading.Event();event.set()
    with pytest.raises(InterruptedError):
        progress.execute_next_step(db,plan['id'],stage['task_id'],stage['employee_id'],cancel=event)
    assert db.list_task_runs()==[]


def test_manual_done_without_approved_staff_artifact_cannot_unlock_next(tmp_path,monkeypatch):
    db,plan=_approved(tmp_path,monkeypatch)
    first=progress.next_step(db,plan['id'])
    db.set_task_status(first['task_id'],'in_progress')
    with pytest.raises(ValueError,match='소유자 수락'):
        db.set_task_status(first['task_id'],'done')
    blocked=progress.next_step(db,plan['id'])
    assert blocked['ready'] is False
    assert blocked['task_id']==first['task_id']
    assert '진행 중' in blocked['reason']
    assert len(db.list_task_runs())==0


def test_two_owner_windows_compete_for_same_step_only_one_model_run(tmp_path,monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier, Event
    db,plan=_approved(tmp_path,monkeypatch)
    second=LocalStore(db.path)
    second.login('tester','a'*24)
    step=progress.next_step(db,plan['id'])
    started=Event()
    release=Event()
    def slow_model(*args,**kwargs):
        started.set()
        assert release.wait(10)
        return 'SQLite에 실제 저장하는 합성 직원 결과'
    monkeypatch.setattr('desktop.task_runtime.run_local_model',slow_model)
    monkeypatch.setattr('desktop.chief_task_runtime.collect_chief_task_result',
                        lambda *a,**k:'총괄 AI 검토 내용')
    def execute(store):
        return progress.execute_next_step(store,plan['id'],step['task_id'],step['employee_id'])
    with ThreadPoolExecutor(max_workers=2) as pool:
        first=pool.submit(execute,db)
        assert started.wait(10)
        other=pool.submit(execute,second)
        try:
            with pytest.raises((ValueError,RuntimeError)):
                other.result(timeout=15)
        finally:
            release.set()
        assert first.result(timeout=15)['owner_approval_required'] is True
    assert len(db.list_task_runs(step['task_id']))==1
    assert len(db.list_task_artifacts(step['task_id']))==1


def test_manual_worker_only_result_without_chief_review_cannot_unlock_next(tmp_path, monkeypatch):
    db, plan = _approved(tmp_path, monkeypatch)
    first = progress.next_step(db, plan['id'])
    monkeypatch.setattr('desktop.task_runtime.run_local_model',
                        lambda *a, **k: '총괄 검토 없는 직원 결과')
    worker = ops.execute_task(db, first['task_id'])
    assert db.find_chief_task_report(worker['artifact_id']) is None
    db.review_task_artifact(worker['artifact_id'], 'approved')
    with pytest.raises(ValueError,match='총괄 보고서'):
        ops.finalize_approved_artifact(db, worker['artifact_id'])
    with pytest.raises(ValueError,match='소유자 수락'):
        db.set_task_status(first['task_id'],'done')
    state = progress.next_step(db, plan['id'])
    assert state['ready'] is False
    assert state['task_id'] == first['task_id']
    assert '총괄' in state['reason'] or '검수' in state['reason']
    assert len(db.list_task_runs(first['task_id'])) == 1


def test_rejected_chief_report_never_unlocks_next_department(tmp_path, monkeypatch):
    db, plan = _approved(tmp_path, monkeypatch)
    first = progress.next_step(db, plan['id'])
    monkeypatch.setattr('desktop.task_runtime.run_local_model',
                        lambda *a, **k: '승인된 직원 결과물')
    monkeypatch.setattr('desktop.chief_task_runtime.collect_chief_task_result',
                        lambda *a, **k: '총괄 모델 검토 기록')
    result = progress.execute_next_step(db, plan['id'], first['task_id'], first['employee_id'])
    db.review_chief_task_report(result['report_id'], 'rejected', '총괄 결과가 부적합합니다.')
    db.review_task_artifact(result['artifact_id'], 'approved')
    with pytest.raises(ValueError,match='총괄 보고서'):
        ops.finalize_approved_artifact(db, result['artifact_id'])
    with pytest.raises(ValueError,match='소유자 수락'):
        db.set_task_status(first['task_id'],'done')
    state = progress.next_step(db, plan['id'])
    assert state['ready'] is False
    assert state['task_id'] == first['task_id']
    assert '총괄' in state['reason'] or '검수' in state['reason']


def test_interrupted_chief_review_guides_owner_without_auto_rerun(tmp_path, monkeypatch):
    db, plan = _approved(tmp_path, monkeypatch)
    first = progress.next_step(db, plan['id'])
    monkeypatch.setattr('desktop.task_runtime.run_local_model',
                        lambda *a, **k: '저장된 직원 결과물')
    worker = ops.execute_task(db, first['task_id'])
    state = progress.next_step(db, plan['id'])
    assert state['ready'] is False
    assert '총괄 AI 검토 복구' in state['reason']
    assert len(db.list_task_runs(first['task_id'])) == 1
    assert db.find_chief_task_report(worker['artifact_id']) is None


def test_direct_legacy_execution_cannot_bypass_missing_chief_review(tmp_path,monkeypatch):
    db,plan=_approved(tmp_path,monkeypatch)
    first=progress.next_step(db,plan['id'])
    db.set_task_status(first['task_id'],'in_progress')
    with pytest.raises(ValueError,match='소유자 수락'):
        db.set_task_status(first['task_id'],'done')
    second=plan['steps'][1]['task_id']
    with pytest.raises(ValueError,match='선행 부서 업무'):
        db.begin_task_execution(second)
    assert db.list_task_runs()==[]


def test_direct_legacy_execution_cannot_bypass_rejected_chief(tmp_path,monkeypatch):
    db,plan=_approved(tmp_path,monkeypatch)
    first=progress.next_step(db,plan['id'])
    monkeypatch.setattr('desktop.task_runtime.run_local_model',
                        lambda *a,**k:'직원 테스트 결과')
    monkeypatch.setattr('desktop.chief_task_runtime.collect_chief_task_result',
                        lambda *a,**k:'총괄 테스트 검토')
    result=progress.execute_next_step(db,plan['id'],first['task_id'],first['employee_id'])
    db.review_chief_task_report(result['report_id'],'rejected','반려')
    db.review_task_artifact(result['artifact_id'],'approved')
    with pytest.raises(ValueError,match='총괄 보고서'):
        ops.finalize_approved_artifact(db,result['artifact_id'])
    with pytest.raises(ValueError,match='소유자 수락'):
        db.set_task_status(first['task_id'],'done')
    with pytest.raises(ValueError,match='선행 부서 업무'):
        db.begin_task_execution(plan['steps'][1]['task_id'])


def test_direct_legacy_execution_after_real_owner_review_is_allowed(tmp_path,monkeypatch):
    db,plan=_approved(tmp_path,monkeypatch)
    first=progress.next_step(db,plan['id'])
    monkeypatch.setattr('desktop.task_runtime.run_local_model',
                        lambda *a,**k:'직원 테스트 결과')
    monkeypatch.setattr('desktop.chief_task_runtime.collect_chief_task_result',
                        lambda *a,**k:'총괄 테스트 검토')
    result=progress.execute_next_step(db,plan['id'],first['task_id'],first['employee_id'])
    db.review_task_artifact(result['artifact_id'],'approved')
    db.review_chief_task_report(result['report_id'],'accepted')
    ops.finalize_approved_artifact(db,result['artifact_id'])
    second=plan['steps'][1]['task_id']
    run_id, config, prompt = db.begin_task_execution(second)
    assert run_id>0 and config is not None and '업무' in prompt
    assert len(db.list_task_runs(second))==1


def test_chief_pending_is_not_owner_acceptance(tmp_path,monkeypatch):
    db,plan=_approved(tmp_path,monkeypatch)
    first=progress.next_step(db,plan['id'])
    monkeypatch.setattr('desktop.task_runtime.run_local_model',
                        lambda *a,**k:'직원 업무 실제 저장 기록')
    monkeypatch.setattr('desktop.chief_task_runtime.collect_chief_task_result',
                        lambda *a,**k:'총괄 검토 실제 저장 기록')
    result=progress.execute_next_step(db,plan['id'],first['task_id'],first['employee_id'])
    db.review_task_artifact(result['artifact_id'],'approved')
    assert db.find_chief_task_report(result['artifact_id'])['owner_decision']=='pending'
    with pytest.raises(ValueError,match='소유자가 수락'):
        ops.finalize_approved_artifact(db,result['artifact_id'])
    with pytest.raises(ValueError,match='소유자 수락'):
        db.set_task_status(first['task_id'],'done')
    assert db.read_task(first['task_id'])['status']=='in_progress'
    db.review_chief_task_report(result['report_id'],'accepted')
    assert ops.finalize_approved_artifact(db,result['artifact_id'])==first['task_id']
    assert progress.next_step(db,plan['id'])['ready'] is True


def test_unrelated_task_manual_status_keeps_existing_behavior(tmp_path,monkeypatch):
    db,plan=_approved(tmp_path,monkeypatch)
    task=ops.create_task(db,'일반 업무는 기존 관리자 상태 변경 허용')
    db.set_task_status(task,'in_progress')
    db.set_task_status(task,'done')
    assert db.read_task(task)['status']=='done'
