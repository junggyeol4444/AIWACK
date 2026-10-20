"""Native SQLite concurrency/recovery tests. Model text is synthetic, not GGUF."""
import sys
from concurrent.futures import ThreadPoolExecutor
from threading import Event

import pytest
from desktop.storage import LocalStore
from desktop.model_runtime import ModelConfig
from desktop import company_operations as ops
from desktop import company_chief_review_leases as leases
from desktop import company_department_collaboration as chain
from desktop import company_collaboration_coverage as coverage
from desktop.health_monitor import evaluate_company_health


def office(tmp_path, monkeypatch):
    store=LocalStore(tmp_path/'owner.sqlite3')
    store.setup_owner('owner','a'*24)
    first=store.add_department('시장조사부')
    second=store.add_department('상품기획부')
    chief=store.add_employee_draft('chief','총괄 AI')
    store.assign_reporting_line(chief,'ceo')
    worker=store.add_employee_draft('worker','조사 직원',department_id=first)
    worker2=store.add_employee_draft('worker2','상품 직원',department_id=second)
    model=store.add_local_model(ModelConfig('Test','llamafile',sys.executable,'',32))
    for eid in (chief,worker,worker2):
        store.set_employee_model(eid,model)
    task=ops.create_task(store,'협업 업무')
    monkeypatch.setattr('desktop.chief_runtime.invoke_chief_model',
                        lambda *a,**kw:'시장조사부|시장 조사|조사\n상품기획부|상품 분석|분석')
    plan=chain.propose(store,task)
    plan=chain.approve(store,plan['id'])
    first_task=plan['steps'][0]['task_id']
    monkeypatch.setattr('desktop.task_runtime.run_local_model',
                        lambda *a,**kw:'저장된 직원 모델 응답(합성)')
    artifact=ops.execute_task(store,first_task)
    return store,plan,artifact,chief,worker


def test_chief_lease_excludes_two_windows_before_model_call(tmp_path,monkeypatch):
    store,plan,artifact,chief,worker=office(tmp_path,monkeypatch)
    second=LocalStore(store.path)
    second.login('owner','a'*24)
    started=Event();release=Event()
    calls=[]
    def slow_chief(*args,**kwargs):
        calls.append(1)
        started.set()
        assert release.wait(10)
        return '총괄 모델 응답(합성)'
    monkeypatch.setattr('desktop.chief_task_runtime.collect_chief_task_result',slow_chief)
    with ThreadPoolExecutor(max_workers=2) as pool:
        future=pool.submit(ops.collect_chief_review,store,artifact['artifact_id'])
        assert started.wait(10)
        with pytest.raises(RuntimeError,match='다른 Windows 창'):
            ops.collect_chief_review(second,artifact['artifact_id'])
        assert len(leases.snapshot(second))==1
        release.set()
        result=future.result(timeout=15)
    assert result['owner_approval_required'] if 'owner_approval_required' in result else result['status']=='awaiting_owner_review'
    assert len(calls)==1
    assert leases.snapshot(store)==[]
    assert store.find_chief_task_report(artifact['artifact_id']) is not None


def test_failure_releases_lease_and_allows_explicit_retry(tmp_path,monkeypatch):
    store,plan,artifact,chief,worker=office(tmp_path,monkeypatch)
    def fail(*a,**k):
        raise TimeoutError('synthetic timeout')
    monkeypatch.setattr('desktop.chief_task_runtime.collect_chief_task_result',fail)
    with pytest.raises(TimeoutError):
        ops.collect_chief_review(store,artifact['artifact_id'])
    assert leases.snapshot(store)==[]
    monkeypatch.setattr('desktop.chief_task_runtime.collect_chief_task_result',
                        lambda *a,**k:'수동 재개 총괄 결과')
    assert ops.collect_chief_review(store,artifact['artifact_id'])['report_id']>0


def test_crash_lease_requires_owner_and_age_to_clear(tmp_path,monkeypatch):
    store,plan,artifact,chief,worker=office(tmp_path,monkeypatch)
    aid=artifact['artifact_id']
    token=leases.reserve(store,aid)
    with pytest.raises(RuntimeError):
        leases.reserve(store,aid)
    with pytest.raises(PermissionError):
        leases.clear_after_owner_inspection(store,aid)
    with pytest.raises(ValueError,match='3분'):
        leases.clear_after_owner_inspection(store,aid,owner_confirmed=True)
    with store._connect() as con:
        con.execute('UPDATE aiwack_chief_review_leases SET started_epoch=started_epoch-600')
        state=evaluate_company_health(con)
        assert state['metrics']['stale_chief_review_leases']==1
    assert leases.snapshot(store)[0]['process_state']=='unknown'
    leases.clear_after_owner_inspection(store,aid,owner_confirmed=True)
    assert leases.snapshot(store)==[]
    assert store.find_chief_task_report(aid) is None
    assert store.read_task_artifact(aid)['id']==aid
    assert leases.reserve(store,aid)!=token


def test_lease_blocks_recovery_queue_but_keeps_worker_result(tmp_path,monkeypatch):
    store,plan,artifact,chief,worker=office(tmp_path,monkeypatch)
    assert len(ops.list_interrupted_chief_reviews(store))==1
    token=leases.reserve(store,artifact['artifact_id'])
    assert ops.list_interrupted_chief_reviews(store)==[]
    state=ops.inspect_recovery_state(store)
    assert len(state['chief_review_leases'])==1
    assert state['pending_chief_reviews']==[]
    leases.release(store,artifact['artifact_id'],token)
    assert len(ops.list_interrupted_chief_reviews(store))==1


def test_collaboration_coverage_only_counts_distinct_verified_people(tmp_path,monkeypatch):
    store,plan,artifact,chief,worker=office(tmp_path,monkeypatch)
    first=coverage.snapshot(store)
    assert first['employee_profiles']==3
    assert first['model_bound_employees']==3
    assert first['approved_plan_steps']==2
    assert first['observed_successful_workers']==1
    assert first['verified_owner_accepted_workers']==0
    assert first['distinct_verified_participants']==0
    monkeypatch.setattr('desktop.chief_task_runtime.collect_chief_task_result',
                        lambda *a,**k:'총괄 검토 결과(합성)')
    report=ops.collect_chief_review(store,artifact['artifact_id'])
    store.review_task_artifact(artifact['artifact_id'],'approved')
    store.review_chief_task_report(report['report_id'],'accepted')
    verified=coverage.snapshot(store)
    assert verified['verified_owner_accepted_workers']==1
    assert verified['verified_chief_reviewers']==1
    assert verified['distinct_verified_participants']==2
    assert verified['distinct_verified_departments']==1
    assert verified['plans'][0]['verified_steps']==1
    assert not verified['full_31_participation_verified']
    assert '31명 전원 협업 최종 실증: 미완료' in coverage.text_report(store)


def test_two_departments_and_chief_are_three_distinct_participants(tmp_path,monkeypatch):
    store,plan,artifact,chief,worker=office(tmp_path,monkeypatch)
    monkeypatch.setattr('desktop.chief_task_runtime.collect_chief_task_result',
                        lambda *a,**k:'총괄 단계 검토(합성)')
    first_report=ops.collect_chief_review(store,artifact['artifact_id'])
    store.review_task_artifact(artifact['artifact_id'],'approved')
    store.review_chief_task_report(first_report['report_id'],'accepted')
    ops.finalize_approved_artifact(store,artifact['artifact_id'])
    second_task=plan['steps'][1]['task_id']
    second_artifact=ops.execute_task(store,second_task)
    second_report=ops.collect_chief_review(store,second_artifact['artifact_id'])
    store.review_task_artifact(second_artifact['artifact_id'],'approved')
    store.review_chief_task_report(second_report['report_id'],'accepted')
    ops.finalize_approved_artifact(store,second_artifact['artifact_id'])
    data=coverage.snapshot(store)
    assert data['observed_successful_workers']==2
    assert data['verified_owner_accepted_workers']==2
    assert data['verified_chief_reviewers']==1
    assert data['distinct_verified_participants']==3
    assert data['distinct_verified_departments']==2
    assert data['plans'][0]['fully_reviewed'] is True
    assert data['plans'][0]['verified_steps']==2
    assert data['full_31_participation_verified'] is False


def test_rejected_model_audit_cannot_unlock_next_department(tmp_path,monkeypatch):
    """실제 직원 모델 호출 감사가 손상되면 이전 완료 상태를 신뢰하지 않는다."""
    from desktop import company_department_progress as progress
    store,plan,artifact,chief,worker=office(tmp_path,monkeypatch)
    monkeypatch.setattr('desktop.chief_task_runtime.collect_chief_task_result',
                        lambda *a,**kw:'총괄 검토 응답(합성)')
    report=ops.collect_chief_review(store,artifact['artifact_id'])
    store.review_task_artifact(artifact['artifact_id'],'approved')
    store.review_chief_task_report(report['report_id'],'accepted')
    ops.finalize_approved_artifact(store,artifact['artifact_id'])
    next_task=plan['steps'][1]['task_id']
    assert progress.next_step(store,plan['id'])['ready']
    with store._connect() as con:
        con.execute("""UPDATE ai_model_call_history SET status='failure'
            WHERE id=(SELECT model_call_id FROM company_task_runs WHERE task_id=?)""",
            (plan['steps'][0]['task_id'],))
    assert not progress.next_step(store,plan['id'])['ready']
    assert coverage.snapshot(store)['verified_owner_accepted_workers']==0
    with pytest.raises(ValueError,match='선행 부서'):
        ops.execute_task(store,next_task)


def test_wrong_chief_provenance_cannot_unlock_next_department(tmp_path,monkeypatch):
    """다른 AI의 검토 기록을 붙여도 원래 승인된 총괄로 인정하지 않는다."""
    from desktop import company_department_progress as progress
    store,plan,artifact,chief,worker=office(tmp_path,monkeypatch)
    monkeypatch.setattr('desktop.chief_task_runtime.collect_chief_task_result',
                        lambda *a,**kw:'총괄 검토 응답(합성)')
    report=ops.collect_chief_review(store,artifact['artifact_id'])
    store.review_task_artifact(artifact['artifact_id'],'approved')
    store.review_chief_task_report(report['report_id'],'accepted')
    ops.finalize_approved_artifact(store,artifact['artifact_id'])
    assert progress.next_step(store,plan['id'])['ready']
    with store._connect() as con:
        con.execute('UPDATE company_chief_task_reports SET chief_employee_id=? WHERE id=?',
                    (worker,report['report_id']))
    assert not progress.next_step(store,plan['id'])['ready']
    assert coverage.snapshot(store)['distinct_verified_participants']==0
    with pytest.raises(ValueError,match='선행 부서'):
        ops.execute_task(store,plan['steps'][1]['task_id'])


def test_emergency_stop_blocks_lease_in_atomic_reservation(tmp_path,monkeypatch):
    """검토 예약 트랜잭션 내부에서도 비상 정지를 다시 검사한다."""
    store,plan,artifact,chief,worker=office(tmp_path,monkeypatch)
    store.emergency_stop_local(True,'관리자 비상정지')
    with pytest.raises(PermissionError,match='비상 정지'):
        leases.reserve(store,artifact['artifact_id'])
    assert leases.snapshot(store)==[]
