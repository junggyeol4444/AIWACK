"""T15: 실제 직원 모델 실패 증빙 → 관리자 승인 부서 이동 → 기존 업무 해제."""
import sys
import pytest
from desktop.storage import LocalStore
from desktop.model_runtime import ModelConfig
from desktop import company_operations as ops
from desktop import company_staff_reallocation as moves

@pytest.fixture
def company(tmp_path,monkeypatch):
    db=LocalStore(tmp_path/'staff-transfer.sqlite3')
    db.setup_owner('owner','reassignment-password-2026')
    first=db.add_department('연구개발부')
    other=db.add_department('품질관리부')
    staff=db.add_employee_draft('transfer_staff','실제 모델 실패 직원',department_id=first)
    model=db.add_local_model(ModelConfig('fixture','llamafile',sys.executable,'',32))
    db.set_employee_model(staff,model)
    task=ops.create_task(db,'실제 모델 실패 기록 업무')
    ops.assign_task(db,task)
    def fail(*args,**kwargs):raise RuntimeError('test subprocess failed')
    monkeypatch.setattr('desktop.task_runtime.run_local_model',fail)
    with pytest.raises(RuntimeError):
        ops.execute_task(db,task)
    run=db.list_task_runs(task)[0]['id']
    return db,staff,first,other,task,run

def test_owner_approved_reassignment_releases_old_assignments_and_survives_restart(company):
    db,staff,source,target,task,run=company
    p=db.propose_staff_department_transfer(staff,target,run,'실제 실패 후 품질부에 재배치 제안')
    assert not p['executed']
    assert db.read_employee_record(staff)['department_id']==source
    assert db.propose_staff_department_transfer(staff,target,run,'중복 등록 제안')['duplicate']
    result=db.decide_staff_department_transfer(p['id'],'accepted','실제 오류 검토 후 부서 이동 승인')
    assert result['decision']=='accepted' and not result['model_executed']
    assert db.read_employee_record(staff)['department_id']==target
    assert db.read_task_routing(task)['employee_id'] is None
    with pytest.raises(ValueError,match='대기'):
        db.decide_staff_department_transfer(p['id'],'accepted','중복 재승인 금지')
    db.logout()
    reopened=LocalStore(db.path)
    reopened.login('owner','reassignment-password-2026')
    audit=reopened.staff_department_transfer_audit()
    assert len(audit)==1 and audit[0]['assignments_released']>=1

def test_invented_evidence_rejected_stop_blocks_and_rejection_preserves_staff(company):
    db,staff,old,target,task,run=company
    with pytest.raises(ValueError,match='실제 실패'):
        db.propose_staff_department_transfer(staff,target,run+1000,'실제 실패 없는 이동 차단')
    p=db.propose_staff_department_transfer(staff,target,run,'모델 실패 기록에 따른 이동 검토')
    db.emergency_stop_local(True,'운영 중단')
    with pytest.raises(PermissionError):
        db.decide_staff_department_transfer(p['id'],'accepted','비상정지 중 이동 거부')
    db.emergency_stop_local(False,'소유자 재개')
    db.decide_staff_department_transfer(p['id'],'rejected','기존 부서에서 재검토')
    assert db.read_employee_record(staff)['department_id']==old


def test_staff_transfer_evidence_is_write_once(company):
    import sqlite3
    db,staff,source,target,task,run=company
    proposal=db.propose_staff_department_transfer(staff,target,run,'실제 직원 모델 실패 기반 이직 증거')
    with db._connect() as con:
        with pytest.raises(sqlite3.DatabaseError):
            con.execute('UPDATE aiwack_staff_transfer_reviews SET employee_id=? WHERE id=?',(staff+99,proposal['id']))
    db.decide_staff_department_transfer(proposal['id'],'rejected','관리자 부서 이동 보류 결정')
    with db._connect() as con:
        with pytest.raises(sqlite3.DatabaseError):
            con.execute("UPDATE aiwack_staff_transfer_reviews SET state='accepted' WHERE id=?",(proposal['id'],))
