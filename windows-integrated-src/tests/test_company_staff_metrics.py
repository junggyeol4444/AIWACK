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



def test_metrics_aggregate_runs_separately_from_reviewed_artifacts(tmp_path):
    """결과물 검수 감사 행이 증가해도 실제 모델 실행 횟수는 부풀리지 않는다."""
    import hashlib
    db=LocalStore(tmp_path/'aggregate.sqlite3')
    db.setup_owner('owner','metrics-aggregate-password-2026')
    emp=db.add_employee_draft('worker','Worker')
    with db._connect() as con:
        con.execute("INSERT INTO company_tasks(title,description,status) VALUES('Saved run','', 'todo')")
        task_id=con.execute('SELECT MAX(id) FROM company_tasks').fetchone()[0]
        call=con.execute("INSERT INTO ai_model_call_history(employee_id,model_id,model_name,status,prompt_chars) VALUES(?,?,?,?,?)",
                         (emp,1,'audit','success',1)).lastrowid
        run=con.execute("INSERT INTO company_task_runs(task_id,employee_id,model_id,model_name,model_call_id,status,prompt_chars,output_chars,duration_ms) VALUES(?,?,?,?,?,?,?,?,?)",
                        (task_id,emp,1,'audit',call,'success',1,4,1)).lastrowid
        body='실제로 저장된 결과'
        con.execute("INSERT INTO company_task_artifacts(task_id,run_id,title,body,sha256,review_status) VALUES(?,?,?,?,?,'approved')",
                    (task_id,run,'결과',body,hashlib.sha256(body.encode()).hexdigest()))
        for _ in range(3):
            con.execute("INSERT INTO company_task_artifact_reviews(artifact_id,old_status,new_status,note) VALUES((SELECT MAX(id) FROM company_task_artifacts),'pending','approved','검수')")
    row=next(x for x in metrics.snapshot(db)['staff'] if x['employee_id']==emp)
    assert row['actual_attempts']==1 and row['successful']==1
    assert row['owner_approved_artifacts']==1
    assert row['observed_success_rate']==100.0
