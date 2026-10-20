"""Durable owner-approved 31-task campaigns, no background retry or auto-approval."""
import sys
import threading
import pytest
from desktop.model_runtime import ModelConfig
from desktop.storage import LocalStore
from desktop import company_operations as ops
from desktop import company_campaign as camp


@pytest.fixture
def team(tmp_path, monkeypatch):
    store=LocalStore(tmp_path/'company_campaign.sqlite3')
    store.setup_owner('campaign_owner','campaign-owner-password-2026')
    ceo=store.add_employee_draft('campaign_chief','총괄 AI')
    store.assign_reporting_line(ceo,'ceo')
    employees=[store.add_employee_draft(f'worker_{i}',f'worker {i}') for i in range(3)]
    model=store.add_local_model(ModelConfig('SyntheticCampaign','llamafile',sys.executable,'',32))
    for emp in [ceo]+employees:store.set_employee_model(emp,model)
    tasks=[]
    for i in range(3):
        tid=ops.create_task(store,f'Owner confirmed #{i}')
        assert ops.assign_task(store,tid)['employee_id']==employees[i]
        ops.approve_chief_order(store,tid,f'Owner instruction #{i}')
        tasks.append(tid)
    events=[]
    monkeypatch.setattr('desktop.task_runtime.run_local_model',
                        lambda *a,**k: events.append('worker') or 'SYNTHETIC RESULT')
    monkeypatch.setattr('desktop.chief_task_runtime.collect_chief_task_result',
                        lambda *a,**k: events.append('chief') or 'SYNTHETIC CHIEF')
    return store,tuple(tasks),employees,events


def test_full_manifest_uses_real_sql_audits_and_persists_owner_pending(team):
    store,ids,employees,events=team
    assert [x['task_id'] for x in camp.candidate_tasks(store)]==list(ids)
    assert store.list_task_runs()==[]
    cid=camp.create_campaign(store,expected_task_ids=ids)
    assert camp.campaign_status(store,cid)['state']=='draft'
    result=camp.execute_campaign(store,cid)
    assert result['state']=='review_pending' and result['review_pending']==3
    assert result['auto_approved'] is False
    assert events.count('worker')==events.count('chief')==3
    for tid in ids:
        assert store.read_task(tid)['status']=='in_progress'
        art=store.list_task_artifacts(tid)[0]
        assert store.find_chief_task_report(art['id'])['owner_decision']=='pending'
    store.logout()
    other=LocalStore(store.path)
    other.login('campaign_owner','campaign-owner-password-2026')
    assert camp.campaign_status(other,cid)['review_pending']==3
    assert camp.candidate_tasks(other)==[]
    with pytest.raises(ValueError):camp.execute_campaign(other,cid)
    assert events.count('worker')==3


def test_manifest_rejects_mismatched_ids_and_unapproved_tasks(team):
    store,ids,employees,events=team
    extra=ops.create_task(store,'Not approved by owner')
    for invalid in ((),(ids[0],ids[0]),(True,),tuple(reversed(ids)),[ids[0]]):
        with pytest.raises(ValueError):camp.create_campaign(store,expected_task_ids=invalid)
    assert all(row['task_id']!=extra for row in camp.candidate_tasks(store))
    assert store.list_task_runs()==[] and events==[]


def test_abandoned_running_campaign_is_read_only_and_not_replayed(team):
    store,ids,employees,events=team
    cid=camp.create_campaign(store,expected_task_ids=ids)
    with store._connect() as con:
        con.execute('UPDATE aiwack_work_campaigns SET state=? WHERE id=?',('running',cid))
        con.execute('UPDATE aiwack_work_campaign_items SET state=? WHERE campaign_id=? AND task_id=?',
                    ('running',cid,ids[0]))
    state=camp.inspect_interrupted_campaign(store,cid)
    assert state['state']=='paused' and state['needs_review']==1
    with pytest.raises(ValueError):camp.execute_campaign(store,cid)
    assert store.list_task_runs()==[] and events==[]


def test_campaign_cancel_and_emergency_stop_preserve_owner_control(team,monkeypatch):
    store,ids,employees,events=team
    cid=camp.create_campaign(store,expected_task_ids=ids)
    cancel=threading.Event()
    cancel.set()
    with pytest.raises(InterruptedError):camp.execute_campaign(store,cid,cancel=cancel)
    assert camp.campaign_status(store,cid)['state']=='draft'
    store.emergency_stop_local(True,'Owner emergency stop')
    with pytest.raises(PermissionError):camp.execute_campaign(store,cid)
    assert store.list_task_runs()==[] and events==[]


def test_campaign_worker_failure_never_auto_retries_or_runs_chief(team,monkeypatch):
    store,ids,employees,events=team
    cid=camp.create_campaign(store,expected_task_ids=ids)
    def failing(*a,**kw):
        raise RuntimeError('SYNTHETIC FAILURE: DO NOT RETRY')
    monkeypatch.setattr('desktop.task_runtime.run_local_model',failing)
    with pytest.raises(RuntimeError):camp.execute_campaign(store,cid)
    status=camp.campaign_status(store,cid)
    assert status['state']=='paused' and status['needs_review']>=1
    assert events.count('chief')==0
    with pytest.raises(ValueError):camp.execute_campaign(store,cid)


def test_manually_recovered_chief_report_reconciles_without_replaying_worker(team,monkeypatch):
    store,ids,employees,events=team
    cid=camp.create_campaign(store,expected_task_ids=ids)
    # First worker returned and saved a real audited result, but EXE died
    # after that checkpoint. The owner later recovered the chief report.
    result=ops.execute_task(store,ids[0])
    artifact_id=result['artifact_id']
    with store._connect() as con:
        con.execute("UPDATE aiwack_work_campaigns SET state='paused' WHERE id=?",(cid,))
        con.execute("""UPDATE aiwack_work_campaign_items SET state='needs_review'
            WHERE campaign_id=? AND task_id=?""",(cid,ids[0]))
    initial=camp.reconcile_manually_recovered_chief_reviews(store,cid)
    assert initial['needs_review']==1 and initial['models_reexecuted'] is False
    assert events.count('worker')==1 and events.count('chief')==0
    ops.collect_chief_review(store,artifact_id)
    reconciled=camp.reconcile_manually_recovered_chief_reviews(store,cid)
    assert reconciled['reconciled_existing_chief_reports']==[ids[0]]
    assert reconciled['review_pending']==1 and reconciled['needs_review']==0
    assert events.count('worker')==events.count('chief')==1
    resumed=camp.execute_campaign(store,cid)
    assert resumed['state']=='review_pending' and resumed['review_pending']==3
    assert events.count('worker')==3 and events.count('chief')==3
    assert len(store.list_task_runs(ids[0]))==1
