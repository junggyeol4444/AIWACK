"""실제 실패 모델 실행을 기존 업무에 안전하게 연계한다."""
import sys
import pytest
from desktop.storage import LocalStore
from desktop.model_runtime import ModelConfig
from desktop import company_operations as ops
from desktop import company_failure_followups as followup

@pytest.fixture
def failed(tmp_path,monkeypatch):
    db=LocalStore(tmp_path/'fail.sqlite3')
    db.setup_owner('owner','staff-failure-password-2026')
    staff=db.add_employee_draft('failed_agent','실패 원인 담당')
    model=db.add_local_model(ModelConfig('fixture','llamafile',sys.executable,'',32))
    db.set_employee_model(staff,model)
    task=ops.create_task(db,'실제 직원 추론 실패 업무')
    ops.assign_task(db,task)
    def fail(*args,**kwargs):raise RuntimeError('fixture subprocess failure')
    monkeypatch.setattr('desktop.task_runtime.run_local_model',fail)
    with pytest.raises(RuntimeError):ops.execute_task(db,task)
    return db,task

def test_failed_employee_run_creates_one_owner_reviewable_real_task(failed):
    db,task=failed
    first=db.scan_failed_employee_work()
    assert len(first['created'])==1
    assert db.scan_failed_employee_work()['created']==[]
    out=db.decide_failed_employee_followup(first['created'][0],'approved','원인 분석 및 재검수 승인')
    assert out['new_task_id']!=task
    assert db.read_task(out['new_task_id'])['status']=='todo'
    assert out['model_autorun'] is False
    with pytest.raises(ValueError,match='이미 결정'):
        db.decide_failed_employee_followup(first['created'][0],'approved','중복 승인 금지')
    db.logout();reopened=LocalStore(db.path);reopened.login('owner','staff-failure-password-2026')
    assert reopened.failed_employee_followups()[0]['followup_task_id']==out['new_task_id']

def test_paused_company_never_autoruns_a_failed_followup(failed):
    db,task=failed
    db.emergency_stop_local(True,'실제 모델 자동 실행 차단')
    assert db.scan_failed_employee_work()['blocked']=='emergency_stop'
    db.emergency_stop_local(False,'관리자 운영 재개')
    proposal=db.scan_failed_employee_work()['created'][0]
    db.emergency_stop_local(True,'관리자 재차 중단')
    with pytest.raises(PermissionError):
        db.decide_failed_employee_followup(proposal,'approved','중단 중 승인 금지')


def test_owner_enabled_autopilot_creates_failed_run_followup_without_autorun(failed):
    db, task = failed
    from desktop import company_autopilot as autopilot
    autopilot.configure(db, True, now=500)
    tick=autopilot.run_once(db, now=500)
    assert tick['executed'] is True
    assert tick['failed_staff_followup_proposals']==1
    assert db.failed_employee_followups()[0]['state']=='pending'
    assert len(db.list_task_runs(task))==1
    again=autopilot.run_once(db, now=500)
    assert again['executed'] is False
    assert len(db.failed_employee_followups())==1
