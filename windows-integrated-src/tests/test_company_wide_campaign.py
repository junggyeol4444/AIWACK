"""T05 company-wide 31 role campaign: 15 departments, real audited chief model calls.

Local inference responses in this test are synthetic, not a real GGUF acceptance.
"""
import sys
import threading
import pytest
from desktop.storage import LocalStore
from desktop.model_runtime import ModelConfig
from desktop import company_operations as ops
from desktop import company_wide_campaign as wide


@pytest.fixture
def office(tmp_path, monkeypatch):
    db=LocalStore(tmp_path/'wide.sqlite3')
    db.setup_owner('owner','wide-campaign-password-2026')
    ops.initialize_company_blueprint(db)
    assert len(db.list_employee_records())==31
    model=db.add_local_model(ModelConfig('test-chief-and-workers','llamafile',sys.executable,'',32))
    for employee in db.list_employee_records():
        db.set_employee_model(employee['id'],model)
    task=ops.create_task(db,'15개 부서 협력으로 고객지원 제품 출범','모든 결과물 관리자 승인')
    # Invoke actual model-call audit / SQLite using a bounded fixture response.
    def chief_lines(config,prompt,**kwargs):
        names=prompt.rsplit('담당 부서: ',1)[1].split(', ')
        assert len(names)==3
        return '\n'.join(f'{name}|검증과 개선|{name} 업무를 분석하고 개선안을 제출하세요' for name in names)
    monkeypatch.setattr('desktop.employee_model_runtime.run_local_model',chief_lines)
    return db,task,model


def test_full_31_role_campaign_actual_sqlite_model_evidence_and_restart(office,monkeypatch):
    db,task,model=office
    plan=wide.propose(db,task)
    assert plan['state']=='draft' and plan['distinct_departments']==15
    assert plan['distinct_worker_roles']==30 and len(plan['steps'])==30
    assert len(db.list_task_runs())==0 and len(db.list_tasks())==1
    chief_id=db.read_chief_profile()['employee_id']
    assert len(db.list_employee_model_calls(chief_id))==5
    with pytest.raises(ValueError,match='이미'):
        wide.propose(db,task)
    saved=wide.approve(db,plan['id'])
    ids=[s['task_id'] for s in saved['steps']]
    assert len(ids)==30 and len(set(ids))==30
    assert all(db.read_chief_task_order(i) for i in ids)
    assert db.task_dependency_readiness(ids[1])['ready'] is False
    assert db.task_dependency_readiness(ids[0])['ready'] is True
    assert len(db.list_tasks())==31
    with pytest.raises(ValueError):
        wide.run_next(db,plan['id']+1000)
    monkeypatch.setattr('desktop.task_runtime.run_local_model',lambda *a,**k:'실제 결과물: 테스트 모의 모델')
    monkeypatch.setattr('desktop.chief_task_runtime.collect_chief_task_result',lambda *a,**k:'총괄 검수 모의 답변')
    first=wide.run_next(db,plan['id'])
    assert first['step']==1 and first['owner_review_required'] is True
    worker=first['work']
    assert db.read_task_artifact(worker['artifact_id'])['review_status']=='pending'
    with pytest.raises(ValueError):
        wide.run_next(db,plan['id'])
    db.review_task_artifact(worker['artifact_id'],'approved')
    with pytest.raises(ValueError,match='총괄'):
        ops.finalize_approved_artifact(db,worker['artifact_id'])
    db.review_chief_task_report(worker['report_id'],'accepted')
    ops.finalize_approved_artifact(db,worker['artifact_id'])
    assert db.task_dependency_readiness(ids[1])['ready'] is True
    db.logout()
    db=LocalStore(db.path)
    db.login('owner','wide-campaign-password-2026')
    restored=wide.read(db,plan['id'])
    assert restored['state']=='approved' and len(restored['steps'])==30
    assert restored['steps'][0]['task_status']=='done'


def test_preflight_incomplete_model_or_emergency_causes_no_partial_tasks(office):
    db,task,model=office
    worker=db.list_employee_records()[-1]
    db.set_employee_model(worker['id'],None)
    with pytest.raises(ValueError,match='모델'):
        wide.propose(db,task)
    assert len(db.list_tasks())==1
    db.set_employee_model(worker['id'],model)
    plan=wide.propose(db,task)
    db.emergency_stop_local(True,'소유자 긴급중단')
    with pytest.raises(PermissionError):
        wide.approve(db,plan['id'])
    assert len(db.list_tasks())==1


def test_cancelled_real_chief_planning_retains_no_partial_campaign(office,monkeypatch):
    db,task,model=office
    cancel=threading.Event()
    def close(*args,**kwargs):
        cancel.set()
        return '결과 무시',999
    monkeypatch.setattr(wide,'invoke_employee_model',close)
    with pytest.raises(InterruptedError):
        wide.propose(db,task,cancel=cancel)
    with db._connect() as con:
        wide.initialize(con)
        assert con.execute('SELECT COUNT(*) FROM aiwack_wide_campaigns').fetchone()[0]==0
    assert len(db.list_tasks())==1


def test_entire_31_role_chain_requires_30_distinct_model_worker_reviews(office,monkeypatch):
    """Complete 30-task chain using synthetic model text, but REAL original SQLite safeguards."""
    from desktop.company_collaboration_coverage import snapshot
    db,task,model=office
    campaign=wide.approve(db,wide.propose(db,task)['id'])
    assert snapshot(db)['full_31_participation_verified'] is False
    monkeypatch.setattr('desktop.task_runtime.run_local_model',
                        lambda *a,**k:'합성 직원 결과: 업무 수행 검토 전')
    monkeypatch.setattr('desktop.chief_task_runtime.collect_chief_task_result',
                        lambda *a,**k:'합성 총괄 모델 검수 의견')
    for index in range(30):
        step=wide.run_next(db,campaign['id'])
        assert step['step']==index+1
        artifact=step['work']['artifact_id']
        report=step['work']['report_id']
        db.review_task_artifact(artifact,'approved')
        db.review_chief_task_report(report,'accepted')
        assert ops.finalize_approved_artifact(db,artifact)==campaign['steps'][index]['task_id']
    assert wide.run_next(db,campaign['id'])['completed'] is True
    summary=snapshot(db)
    assert summary['distinct_verified_workers']==30
    assert summary['distinct_verified_participants']==31
    assert summary['distinct_verified_departments']==15
    assert summary['full_31_participation_verified'] is True
    assert len(db.list_task_runs())==30
    # This is a STRUCTURAL regression with synthetic model text, not 31 real GGUF inferences.


def test_verified_progress_handoff_real_approval_and_worker_prompt(office,monkeypatch):
    """Owner-accepted output must appear as untrusted context in the next model prompt."""
    db,task,_=office
    plan=wide.approve(db,wide.propose(db,task)['id'])
    before=wide.verified_progress(db,plan['id'])
    assert before['verified_completed_tasks']==0
    assert before['next_task_id']==plan['steps'][0]['task_id']
    assert before['all_30_tasks_evidence_verified'] is False
    seen=[]
    def worker(config,prompt,**kw):
        seen.append(prompt)
        return '승인된 실제 직원 결과: 이전 부서 시험 내용 및 증빙'
    monkeypatch.setattr('desktop.task_runtime.run_local_model',worker)
    monkeypatch.setattr('desktop.chief_task_runtime.collect_chief_task_result',
                        lambda *a,**k:'총괄 검토 시험 응답')
    first=wide.run_next(db,plan['id'])['work']
    assert wide.verified_progress(db,plan['id'])['verified_completed_tasks']==0
    db.review_task_artifact(first['artifact_id'],'approved')
    db.review_chief_task_report(first['report_id'],'accepted')
    ops.finalize_approved_artifact(db,first['artifact_id'])
    progress=wide.verified_progress(db,plan['id'])
    assert progress['verified_completed_tasks']==1
    assert progress['verified_distinct_workers']==1
    assert progress['next_task_id']==plan['steps'][1]['task_id']
    assert progress['verified_evidence'][0]['artifact_id']==first['artifact_id']
    next_result=wide.run_next(db,plan['id'])
    assert next_result['step']==2 and len(seen)==2
    assert f"[업무 #{plan['steps'][0]['task_id']}·승인 결과물 #{first['artifact_id']}]" in seen[1]
    assert '승인된 실제 직원 결과' in seen[1]
    assert '신뢰할 수 없는 데이터' in seen[1]
    assert wide.verified_progress(db,plan['id'])['verified_completed_tasks']==1


def test_tampered_approved_handoff_prevents_next_real_model_call(office,monkeypatch):
    db,task,_=office
    plan=wide.approve(db,wide.propose(db,task)['id'])
    hits=[]
    monkeypatch.setattr('desktop.task_runtime.run_local_model',
        lambda *a,**kw:(hits.append(1) or '정상 회사 업무 결과물'))
    monkeypatch.setattr('desktop.chief_task_runtime.collect_chief_task_result',
                        lambda *a,**k:'총괄 AI 감사 모델 결과')
    first=wide.run_next(db,plan['id'])['work']
    db.review_task_artifact(first['artifact_id'],'approved')
    db.review_chief_task_report(first['report_id'],'accepted')
    ops.finalize_approved_artifact(db,first['artifact_id'])
    with db._connect() as con:
        con.execute('UPDATE company_task_artifacts SET body=? WHERE id=?',
                    ('다른 창에서 손상된 직원 보고서',first['artifact_id']))
    with pytest.raises(ValueError,match='무결성'):
        wide.run_next(db,plan['id'])
    assert hits==[1]
    assert db.list_task_runs(plan['steps'][1]['task_id'])==[]
    assert wide.verified_progress(db,plan['id'])['verified_completed_tasks']==0


def test_real_chief_plan_bad_format_retry_is_audited_and_does_not_auto_approve(office,monkeypatch):
    db,task,_=office
    calls=[]
    def local_answer(config,prompt,**kw):
        calls.append(prompt)
        if len(calls)==1:return 'invalid plan text'
        names=prompt.rsplit('담당 부서: ',1)[1].split(', ')
        return '\n'.join(f'{name}|승인 준비|{name} 업무 분석과 자료 정리' for name in names)
    monkeypatch.setattr('desktop.employee_model_runtime.run_local_model',local_answer)
    plan=wide.propose(db,task)
    assert len(calls)==6 and len(plan['steps'])==30
    assert '이전 출력은 부서별 정확한 형식' in calls[1]
    chief=db.read_chief_profile()['employee_id']
    assert len(db.list_employee_model_calls(chief))==6
    assert len(db.list_tasks())==1

def test_real_chief_three_invalid_answers_fail_closed_without_campaign(office,monkeypatch):
    db,task,_=office
    monkeypatch.setattr('desktop.employee_model_runtime.run_local_model',lambda *a,**kw:'invalid')
    with pytest.raises(ValueError,match='세 번 연속'):
        wide.propose(db,task)
    chief=db.read_chief_profile()['employee_id']
    assert len(db.list_employee_model_calls(chief))==3
    assert len(db.list_tasks())==1
    with db._connect() as con:
        wide.initialize(con)
        assert con.execute('SELECT COUNT(*) FROM aiwack_wide_campaigns').fetchone()[0]==0
