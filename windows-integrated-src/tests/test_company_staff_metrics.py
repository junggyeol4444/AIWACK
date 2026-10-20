"""Persisted performance counts from real SQLite audit, without fake business results."""
import sys
import pytest
from desktop.storage import LocalStore, AuthenticationError
from desktop.model_runtime import ModelConfig
from desktop import company_operations as ops
from desktop import company_staff_metrics as metrics


def test_employee_metrics_record_only_actual_runs_and_reviews(tmp_path,monkeypatch):
    store=LocalStore(tmp_path/'metrics.sqlite3')
    store.setup_owner('metrics_owner','metrics-owner-password-2026')
    staff=[store.add_employee_draft('metrics_'+str(i),'실제 직원 '+str(i)) for i in range(2)]
    model=store.add_local_model(ModelConfig('SYNTH','llamafile',sys.executable,'',32))
    for emp in staff:store.set_employee_model(emp,model)
    before=metrics.snapshot(store)
    assert before['employees']==2
    assert before['recorded_successful_model_calls']==0
    assert all(e['observed_success_rate'] is None for e in before['staff'])
    first=ops.create_task(store,'Real saved staff output')
    assert ops.assign_task(store,first)['employee_id'] in staff
    monkeypatch.setattr('desktop.task_runtime.run_local_model',
                        lambda *a,**k:'VERIFIED LOCAL AUDIT CONTENT')
    art=ops.execute_task(store,first)['artifact_id']
    data=metrics.snapshot(store)
    assert data['recorded_successful_model_calls']==1
    assert sum(e['successful'] for e in data['staff'])==1
    assert data['pending_reviews']==1
    assert sum(e['owner_approved_artifacts'] for e in data['staff'])==0
    assert data['financial_revenue_verified'] is False
    store.review_task_artifact(art,'approved')
    after=metrics.snapshot(store)
    assert sum(e['owner_approved_artifacts'] for e in after['staff'])==1
    assert after['pending_reviews']==0
    assert '실제 판매·매출을 의미하지 않습니다' in metrics.text_report(store)
    store.logout()
    reopened=LocalStore(store.path)
    reopened.login('metrics_owner','metrics-owner-password-2026')
    assert metrics.snapshot(reopened)['recorded_successful_model_calls']==1


def test_metrics_reject_bad_limits_and_logged_out_access(tmp_path):
    db=LocalStore(tmp_path/'metrics.sqlite3')
    db.setup_owner('owner','long-metrics-password-2026')
    for bad in (0,True,101,'31'):
        with pytest.raises(ValueError):metrics.text_report(db,bad)
    db.logout()
    with pytest.raises(AuthenticationError):metrics.snapshot(db)


def test_metrics_failure_is_not_success(tmp_path,monkeypatch):
    db=LocalStore(tmp_path/'failure.sqlite3')
    db.setup_owner('owner','long-fail-password-2026')
    staff=db.add_employee_draft('worker','Failed worker')
    model=db.add_local_model(ModelConfig('SYNTH','llamafile',sys.executable,'',32))
    db.set_employee_model(staff,model)
    tid=ops.create_task(db,'Will fail')
    ops.assign_task(db,tid)
    def fail(*args,**kwargs):raise RuntimeError('Synthetic failure')
    monkeypatch.setattr('desktop.task_runtime.run_local_model',fail)
    with pytest.raises(RuntimeError):ops.execute_task(db,tid)
    row=next(x for x in metrics.snapshot(db)['staff'] if x['employee_id']==staff)
    assert row['failed']==1 and row['successful']==0
    assert metrics.snapshot(db)['recorded_successful_model_calls']==0
