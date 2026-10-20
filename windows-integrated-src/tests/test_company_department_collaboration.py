"""다부서 AI 협업: 실제 SQLite 저장·승인·직원 실행 회귀."""
import sys
import pytest
from desktop.storage import LocalStore
from desktop.model_runtime import ModelConfig
from desktop import company_operations as ops
from desktop import company_department_collaboration as chain


def _office(tmp_path,monkeypatch):
    db=LocalStore(tmp_path/'chain.sqlite3')
    db.setup_owner('tester','a'*24)
    research=db.add_department('시장조사부')
    product=db.add_department('상품기획부')
    chief=db.add_employee_draft('collab_ceo','총괄')
    db.assign_reporting_line(chief,'ceo')
    staff=db.add_employee_draft('collab_staff1','조사 직원',department_id=research)
    staff2=db.add_employee_draft('collab_staff2','기획 직원',department_id=product)
    mid=db.add_local_model(ModelConfig('Test','llamafile',sys.executable,'',32))
    for e in (chief,staff,staff2):
        db.set_employee_model(e,mid)
    task=ops.create_task(db,'원본 업무')
    monkeypatch.setattr('desktop.chief_runtime.invoke_chief_model',
        lambda *a,**k:'시장조사부|고객 조사|분석 보고\n상품기획부|상품 기획|결과 활용')
    return db,task,staff2


def test_chief_plan_requires_owner_then_real_staff_chain(tmp_path,monkeypatch):
    db,task,staff2=_office(tmp_path,monkeypatch)
    plan=chain.propose(db,task)
    assert plan['state']=='draft' and len(db.list_tasks())==1
    approved=chain.approve(db,plan['id'])
    assert approved['state']=='approved'
    ids=[s['task_id'] for s in approved['steps']]
    assert len(ids)==2
    assert db.read_chief_task_order(ids[0]) is not None
    assert db.task_dependency_readiness(ids[1])['ready'] is False
    with pytest.raises(ValueError):
        ops.execute_approved_chief_cycle(db,ids[1])
    monkeypatch.setattr('desktop.task_runtime.run_local_model',
                        lambda *a,**k:'실제 저장되는 합성 직원 결과')
    monkeypatch.setattr('desktop.chief_task_runtime.collect_chief_task_result',
                        lambda *a,**k:'총괄 모델의 검토 결과')
    first=ops.execute_approved_chief_cycle(db,ids[0])
    assert db.read_task_artifact(first['artifact_id'])['review_status']=='pending'
    db.review_task_artifact(first['artifact_id'],'approved')
    # Approval safety: worker artifact review alone cannot bypass chief owner acceptance.
    with pytest.raises(ValueError,match='총괄 보고서'):
        ops.finalize_approved_artifact(db,first['artifact_id'])
    db.review_chief_task_report(first['report_id'],'accepted')
    ops.finalize_approved_artifact(db,first['artifact_id'])
    assert db.task_dependency_readiness(ids[1])['ready'] is True
    second=ops.execute_approved_chief_cycle(db,ids[1])
    assert db.read_task_artifact(second['artifact_id'])['review_status']=='pending'
    assert len(db.list_task_runs())==2


def test_unconfigured_department_does_not_create_partial_tasks(tmp_path,monkeypatch):
    db,task,staff2=_office(tmp_path,monkeypatch)
    plan=chain.propose(db,task)
    db.set_employee_model(staff2,None)
    with pytest.raises(ValueError):
        chain.approve(db,plan['id'])
    assert len(db.list_tasks())==1
    assert chain.read_plan(db,plan['id'])['state']=='draft'


def test_changed_source_and_emergency_stop_block_owner_approval(tmp_path,monkeypatch):
    db,task,staff2=_office(tmp_path,monkeypatch)
    plan=chain.propose(db,task)
    db.update_task(task,'변경된 기준 업무','다른 목표')
    with pytest.raises(ValueError):
        chain.approve(db,plan['id'])
    assert len(db.list_tasks())==1
    db.emergency_stop_local(True,'Owner stopped company')
    with pytest.raises(PermissionError):
        chain.approve(db,plan['id'])
    with pytest.raises(PermissionError):
        chain.propose(db,task)
