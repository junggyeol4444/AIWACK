"""Actual SQLite meeting workflow tests; mocked model text is not real GGUF evidence."""
import json
import sqlite3
import threading
import pytest
from desktop.storage import LocalStore
from desktop.model_runtime import ModelConfig
from desktop import employee_model_runtime as runtime


@pytest.fixture
def case(tmp_path,monkeypatch):
    db=LocalStore(tmp_path/'meeting.sqlite3')
    db.setup_owner('meeting-owner','meeting-test-password-2026')
    d1=db.add_department('기획')
    d2=db.add_department('품질')
    a=db.add_employee_draft('meeting_staff1','기획 담당',department_id=d1)
    b=db.add_employee_draft('meeting_staff2','품질 담당',department_id=d2)
    cli=tmp_path/'model-runner'
    cli.write_bytes(b'mock')
    weights=tmp_path/'local.gguf'
    weights.write_bytes(b'GGUF')
    model=db.add_local_model(ModelConfig('meeting-model','llama_cpp',str(cli),str(weights),64))
    db.set_employee_model(a,model)
    db.set_employee_model(b,model)
    mid=db.create_meeting('출시 회의','다른 부서 의견')
    agenda=db.add_meeting_agenda(mid,'출시 가능 여부')
    for e in (a,b):
        db.add_meeting_attendee(mid,e)
    db.set_meeting_status(mid,'scheduled')
    monkeypatch.setattr(runtime,'run_local_model',lambda *args,**kwargs:
        json.dumps({'stance':'보류','reasoning':'추가 근거가 필요합니다.',
                    'alternative':'품질 검사 자료 확보'},ensure_ascii=False))
    return db,mid,agenda,a,b


def test_two_model_calls_atomic_audit_and_relogin_no_auto_decision(case):
    db,mid,agenda,a,b=case
    one=db.run_real_meeting_employee_opinion(mid,agenda,a)
    two=db.run_real_meeting_employee_opinion(mid,agenda,b)
    assert one['model_call_id']!=two['model_call_id']
    opinions=db.compare_meeting_opinions(mid)['agenda'][0]['opinions']
    assert len(opinions)==2 and all(x['origin']=='real_local_model' for x in opinions)
    assert len(db.real_meeting_opinion_audit(mid))==2
    assert db.list_meeting_decisions(mid)==[] and db.list_tasks()==[]
    db.logout()
    reopened=LocalStore(db.path)
    reopened.login('meeting-owner','meeting-test-password-2026')
    assert len(reopened.real_meeting_opinion_audit(mid))==2
    with reopened._connect() as con:
        with pytest.raises(sqlite3.DatabaseError):
            con.execute('DELETE FROM aiwack_real_meeting_model_opinions')


def test_duplicate_attendee_and_rejected_preflight_no_extra_model(case,monkeypatch):
    db,mid,agenda,a,b=case
    db.run_real_meeting_employee_opinion(mid,agenda,a)
    monkeypatch.setattr(runtime,'run_local_model',lambda *args,**kw:
                        pytest.fail('must not run another model'))
    with pytest.raises(ValueError,match='이미'):
        db.run_real_meeting_employee_opinion(mid,agenda,a)
    outsider=db.add_employee_draft('outside_employee','외부 직원')
    with pytest.raises(ValueError,match='참석'):
        db.run_real_meeting_employee_opinion(mid,agenda,outsider)
    assert len(db.list_employee_model_calls())==1


def test_malformed_response_never_becomes_employee_opinion(case,monkeypatch):
    db,mid,agenda,a,b=case
    monkeypatch.setattr(runtime,'run_local_model',lambda *args,**kw:'NO JSON, 승인합니다')
    with pytest.raises(ValueError,match='JSON'):
        db.run_real_meeting_employee_opinion(mid,agenda,a)
    assert db.list_meeting_opinions(mid)==[]
    assert db.real_meeting_opinion_audit(mid)==[]
    assert db.list_employee_model_calls(a)[0]['status']=='success'


def test_emergency_stop_and_cancellation_before_model_start(case):
    db,mid,agenda,a,b=case
    db.emergency_stop_local(True,'관리자 회의 비상정지')
    with pytest.raises(PermissionError,match='비상'):
        db.run_real_meeting_employee_opinion(mid,agenda,a)
    db.emergency_stop_local(False,'관리자 재개')
    cancelled=threading.Event();cancelled.set()
    with pytest.raises(InterruptedError):
        db.run_real_meeting_employee_opinion(mid,agenda,a,cancel=cancelled)
    assert db.list_employee_model_calls()==[]


def test_model_assignment_changed_during_inference_not_saved(case,monkeypatch):
    db,mid,agenda,a,b=case
    def mutate(*args,**kwargs):
        db.set_employee_model(a,None)
        return '{"stance":"찬성","reasoning":"사용 가능한 이유"}'
    monkeypatch.setattr(runtime,'run_local_model',mutate)
    with pytest.raises(ValueError,match='배정'):
        db.run_real_meeting_employee_opinion(mid,agenda,a)
    assert db.list_meeting_opinions(mid)==[]
    assert db.list_employee_model_calls(a)[0]['status']=='success'


def test_owner_decision_still_separate(case):
    db,mid,agenda,a,b=case
    db.run_real_meeting_employee_opinion(mid,agenda,a)
    with pytest.raises(ValueError,match='확인'):
        db.decide_meeting_agenda(mid,agenda,'approved','품질 기준 확인',False)
    decision=db.decide_meeting_agenda(mid,agenda,'approved','관리자 직접 확인',True)
    assert decision>0
    with pytest.raises(ValueError,match='이미 결정'):
        db.run_real_meeting_employee_opinion(mid,agenda,b)
    assert db.list_tasks()==[]
