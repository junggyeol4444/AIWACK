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


@pytest.mark.skipif(__import__('os').name == 'nt', reason='Linux subprocess fixture; Windows GGUF is a separate EXE action')
def test_real_local_cli_subprocess_audit_survives_restart(tmp_path):
    """Actually launches a local subprocess; fixture is not a genuine GGUF model."""
    db=LocalStore(tmp_path/'actual_local_cli_meeting.sqlite3')
    db.setup_owner('local-cli-owner','local-cli-password-2026')
    dep=db.add_department('실행 테스트')
    a=db.add_employee_draft('local_cli_staff1','실행 직원1',department_id=dep)
    b=db.add_employee_draft('local_cli_staff2','실행 직원2',department_id=dep)
    cli=tmp_path/'local-llama-cli-fixture'
    cli.write_text("#!/usr/bin/env python3\nimport json\nprint(json.dumps(dict(stance='보류',reasoning='미검증 사실은 채택할 수 없습니다.')))\n",encoding='utf8')
    cli.chmod(0o700)
    weights=tmp_path/'fixture.gguf'
    weights.write_bytes(b'GGUF\x03\x00\x00\x00')
    model=db.add_local_model(ModelConfig('real-process-fixture','llama_cpp',str(cli),str(weights),48))
    db.set_employee_model(a,model)
    meeting=db.create_meeting('로컬 프로세스 회의')
    agenda=db.add_meeting_agenda(meeting,'확인 항목')
    for staff in (a,b):db.add_meeting_attendee(meeting,staff)
    db.set_meeting_status(meeting,'scheduled')
    result=db.run_real_meeting_employee_opinion(meeting,agenda,a)
    assert result['origin']=='real_local_model'
    assert db.list_employee_model_calls(a)[0]['status']=='success'
    db.logout()
    db=LocalStore(db.path)
    db.login('local-cli-owner','local-cli-password-2026')
    assert len(db.real_meeting_opinion_audit(meeting))==1
