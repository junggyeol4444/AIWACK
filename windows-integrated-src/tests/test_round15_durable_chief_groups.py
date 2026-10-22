"""15회차 SQLite/모의 GGUF 문자열 회귀. 실제 Windows GGUF/EXE 시험이 아님."""
from __future__ import annotations
import sqlite3
import sys
import pytest
from desktop import company_operations as ops
from desktop import company_wide_campaign as wide
from desktop.storage import LocalStore
from desktop.model_runtime import ModelConfig


def _office(tmp_path):
    store=LocalStore(tmp_path/'round15.sqlite3')
    store.setup_owner('round15-owner','round15-local-password')
    ops.initialize_company_blueprint(store)
    model=store.add_local_model(ModelConfig('모의 직원','llamafile',sys.executable,'',32))
    for e in store.list_employee_records():
        store.set_employee_model(e['id'],model)
    source=ops.create_task(store,'15부서 연속 기획','모든 결과물은 관리자 검수 후 처리')
    return store,source,model


def _good(prompt):
    names=prompt.rsplit('담당 부서: ',1)[1].split(', ')
    return '\n'.join(f'{name}|실행 계획|{name}의 실제 자료를 조사하고 검증 보고서를 작성한다'
                     for name in names)


def _interrupt_after_first_group(store,source,monkeypatch):
    calls=[]
    def fake(config,prompt,**kw):
        calls.append(prompt)
        if '담당 부서: ' in prompt and '경영기획부' in prompt:
            return _good(prompt)
        return 'x'  # rejected by both real-chief parsing routes
    monkeypatch.setattr('desktop.employee_model_runtime.run_local_model',fake)
    with pytest.raises(ValueError,match='재계획도 실패'):
        wide.propose(store,source)
    assert wide.staged_plan_progress(store,source)['completed_group_numbers']==[1]
    with store._connect() as con:
        assert con.execute('SELECT COUNT(*) FROM aiwack_wide_campaigns').fetchone()[0]==0
        assert con.execute('SELECT COUNT(*) FROM company_tasks').fetchone()[0]==1
    return calls


def test_partial_chief_plan_survives_crash_and_reuses_only_verified_calls(tmp_path,monkeypatch):
    store,source,_=_office(tmp_path)
    initial=_interrupt_after_first_group(store,source,monkeypatch)
    store.logout()
    restored=LocalStore(store.path)
    restored.login('round15-owner','round15-local-password')
    resumed=[]
    def fake(config,prompt,**kw):
        resumed.append(prompt)
        return _good(prompt)
    monkeypatch.setattr('desktop.employee_model_runtime.run_local_model',fake)
    result=wide.propose(restored,source)
    assert result['state']=='draft'
    assert len(result['steps'])==30 and result['distinct_departments']==15
    assert len(resumed)==4  # group 1 genuine call is NOT repeated
    assert wide.staged_plan_progress(restored,source)['completed_groups']==5
    with restored._connect() as con:
        assert con.execute('SELECT COUNT(*) FROM aiwack_wide_chief_group_staging').fetchone()[0]==5
        assert con.execute('SELECT COUNT(*) FROM company_tasks').fetchone()[0]==1
    approved=wide.approve(restored,result['id'])
    assert len({step['task_id'] for step in approved['steps']})==30
    assert len(restored.list_tasks())==31


def test_staged_chief_plan_is_append_only(tmp_path,monkeypatch):
    store,source,_=_office(tmp_path)
    _interrupt_after_first_group(store,source,monkeypatch)
    with store._connect() as con:
        with pytest.raises(sqlite3.IntegrityError,match='변경·삭제 금지'):
            con.execute("UPDATE aiwack_wide_chief_group_staging SET group_sha256='0' WHERE group_start=0")
        with pytest.raises(sqlite3.IntegrityError,match='변경·삭제 금지'):
            con.execute('DELETE FROM aiwack_wide_chief_group_staging WHERE group_start=0')


def test_changed_source_refuses_old_staged_plan(tmp_path,monkeypatch):
    store,source,_=_office(tmp_path)
    _interrupt_after_first_group(store,source,monkeypatch)
    with store._connect() as con:
        con.execute("UPDATE company_tasks SET description='새로운 지시' WHERE id=?",(source,))
    monkeypatch.setattr('desktop.employee_model_runtime.run_local_model',lambda *a,**kw:_good(a[1]))
    with pytest.raises(ValueError,match='원본 업무·조직·모델'):
        wide.propose(store,source)
    assert len(store.list_tasks())==1


def test_changed_model_refuses_old_staged_plan(tmp_path,monkeypatch):
    store,source,_=_office(tmp_path)
    _interrupt_after_first_group(store,source,monkeypatch)
    new=store.add_local_model(ModelConfig('다른 모의 모델','llamafile',sys.executable,'',64))
    chief=store.read_chief_profile()['employee_id']
    store.set_employee_model(chief,new)
    with pytest.raises(ValueError,match='원본 업무·조직·모델'):
        wide.propose(store,source)
    assert len(store.list_tasks())==1


def test_emergency_stop_blocks_resumed_model_calls(tmp_path,monkeypatch):
    store,source,_=_office(tmp_path)
    _interrupt_after_first_group(store,source,monkeypatch)
    store.emergency_stop_local(True,'15회차 실제 계획 보호')
    monkeypatch.setattr('desktop.employee_model_runtime.run_local_model',
                        lambda *a,**kw:pytest.fail('비상정지 중 모델을 호출해서는 안 됨'))
    with pytest.raises(PermissionError):
        wide.propose(store,source)
    assert len(store.list_tasks())==1


def test_staging_rejects_tampered_model_call_audit(tmp_path,monkeypatch):
    store,source,_=_office(tmp_path)
    _interrupt_after_first_group(store,source,monkeypatch)
    with store._connect() as con:
        # Direct mutation simulates DB corruption; never accepted as a genuine call.
        call=con.execute('SELECT model_call_id FROM aiwack_wide_chief_plan_attempts WHERE parsed=1').fetchone()[0]
        con.execute("UPDATE ai_model_call_history SET output_chars=0 WHERE id=?",(call,))
    with pytest.raises(ValueError,match='실제 모델 호출 감사'):
        wide.staged_plan_progress(store,source)


def test_real30_resume_preflight_recovers_partial_chief_groups_without_synthetic_calls(tmp_path,monkeypatch):
    """Only SQLite preflight: fake binaries are never executed or claimed real."""
    from pathlib import Path
    sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
    from validation import windows_real_30_step_campaign_e2e as real30
    cli=tmp_path/'llama-completion.exe'
    gguf=tmp_path/'real-model-fixture.gguf'
    cli.write_bytes(b'not-an-executable')
    gguf.write_bytes(b'GGUF-not-a-real-model')
    store=LocalStore(tmp_path/'ephemeral_31_agent_campaign.sqlite3')
    store.setup_owner(real30.USER,real30.PASSWORD)
    ops.initialize_company_blueprint(store)
    model=store.add_local_model(ModelConfig('GGUF preflight fixture','llama_cpp',str(cli),str(gguf),256))
    for e in store.list_employee_records():
        store.set_employee_model(e['id'],model)
    source=ops.create_task(store,'15부서 실제 GGUF 고객 지원 프로젝트',
                           '고객지원 정책과 문서 작성 및 품질 점검')
    _interrupt_after_first_group(store,source,monkeypatch)
    store.logout()
    monkeypatch.setattr('desktop.employee_model_runtime.run_local_model',
                        lambda *a,**kw:pytest.fail('재개 사전검사에서 모델 호출 금지'))
    restored=LocalStore(store.path)
    checkpoint={'model_backend':'real GGUF Windows','completed_tasks':0,'steps':[],
                'success':False}
    assert real30._resume_fixture(restored,cli.resolve(),gguf.resolve(),checkpoint)==(source,None,0)
    assert wide.staged_plan_progress(restored,source)['completed_groups']==1


def test_fallback_three_real_single_department_calls_are_staged_without_synthesis(tmp_path,monkeypatch):
    store,source,_=_office(tmp_path)
    attempts=[]
    def fake(config,prompt,**kw):
        attempts.append(prompt)
        if '담당 부서: ' in prompt:
            return 'x'  # genuine 3-dept response was unusable
        import re
        match=re.search(r'for department ([^.]*)\.',prompt)
        assert match,prompt
        name=match.group(1)
        return f'{name}|검증 계획|{name} 부서의 기존 자료를 확인하고 실제 검증 문서를 작성한다'
    monkeypatch.setattr('desktop.employee_model_runtime.run_local_model',fake)
    draft=wide.propose(store,source)
    assert draft['distinct_departments']==15
    assert wide.staged_plan_progress(store,source)['completed_groups']==5
    with store._connect() as con:
        rows=con.execute('''SELECT group_json FROM aiwack_wide_chief_group_staging
                            ORDER BY group_start''').fetchall()
        import json
        assert all(len({v['chief_call_id'] for v in json.loads(row[0])})==3 for row in rows)
        assert con.execute("SELECT COUNT(*) FROM aiwack_wide_chief_plan_attempts WHERE attempt_kind='single_department' AND parsed=1").fetchone()[0]==15
    assert len(store.list_tasks())==1  # approval not bypassed