"""9회차 실제 코드 회귀: 모든 모델 텍스트는 모의 입력이며 GGUF 실검증이 아님."""
from __future__ import annotations
import hashlib
import sqlite3
import sys
from pathlib import Path
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from validation import windows_real_30_step_campaign_e2e as real30
from desktop import company_operations as ops
from desktop import company_wide_campaign as wide
from desktop.model_runtime import ModelConfig
from desktop.storage import LocalStore


def _setup(tmp_path):
    store=LocalStore(tmp_path/'real30-structural.sqlite3')
    store.setup_owner(real30.USER,real30.PASSWORD)
    ops.initialize_company_blueprint(store)
    gguf=tmp_path/'not-a-real-model.gguf'
    gguf.write_bytes(b'GGUF'+b'\x00'*8)
    cli=Path(sys.executable).resolve()
    model=store.add_local_model(ModelConfig('fixture only','llama_cpp',str(cli),str(gguf),256))
    for employee in store.list_employee_records():
        store.set_employee_model(employee['id'],model)
    task=ops.create_task(store,'15부서 실제 GGUF 고객 지원 프로젝트',
                         '고객지원 정책과 문서 작성 및 품질 점검')
    return store,cli,gguf.resolve(),task


def test_json_plan_accepts_only_real_model_supplied_three_departments():
    names=['시장조사부','개발부','고객지원부']
    groups=[(n+1,name,n+100,n+200) for n,name in enumerate(names)]
    import json
    content=json.dumps([{'department':n,'title':f'{n} 검토',
                         'instruction':f'{n} 실제 문서의 품질 기준을 검증한다'}
                        for n in names],ensure_ascii=False)
    parsed=wide._parse_group('```json\n'+content+'\n```',groups)
    assert set(parsed)==set(names)
    assert parsed[names[0]][0]==f'{names[0]} 검토'
    mapped=json.dumps({n:{'title':f'{n} 검토',
                             'instruction':f'{n} 실제 문서의 품질 기준을 검증한다'}
                       for n in names},ensure_ascii=False)
    assert wide._parse_group(mapped,groups)==parsed
    with pytest.raises(ValueError,match='부서'):
        wide._parse_group(content.replace(names[0],'알 수 없는 부서'),groups)
    with pytest.raises(ValueError,match='부서'):
        wide._parse_group(json.dumps([{'department':names[0],'title':'검토',
            'instruction':'검토 수행'}],ensure_ascii=False),groups)


def test_resume_rejects_unrelated_worker_call_and_tampered_content(tmp_path,monkeypatch):
    store,cli,gguf,task=_setup(tmp_path)
    def chief_model(config,prompt,**kwargs):
        if '담당 부서: ' in prompt:
            names=prompt.rsplit('담당 부서: ',1)[1].split(', ')
            return '\n'.join(f'{name}|검토 업무|{name}의 업무 기준을 검토하고 검증 문서를 작성한다' for name in names)
        return '총괄 모델의 실제 검토 결과를 흉내 낸 테스트 전용 응답'
    monkeypatch.setattr('desktop.employee_model_runtime.run_local_model',chief_model)
    monkeypatch.setattr('desktop.task_runtime.run_local_model',
                        lambda *a,**kw:'직원 테스트 결과물: 고객 지원 정책과 품질 기준 검토 문서')
    # Real SQLite model-call path with synthetic test text. The chief report
    # must now bind to the exact chief call ID (not just any successful call).
    plan=wide.approve(store,wide.propose(store,task)['id'])
    with store._connect() as con:
        before=con.execute('SELECT COALESCE(MAX(id),0) FROM ai_model_call_history').fetchone()[0]
    work=wide.run_next(store,plan['id'])['work']
    artifact_id=work['artifact_id']
    store.review_task_artifact(artifact_id,'approved')
    store.review_chief_task_report(work['report_id'],'accepted')
    ops.finalize_approved_artifact(store,artifact_id)
    with store._connect() as con:
        calls=con.execute('SELECT id FROM ai_model_call_history WHERE id>? ORDER BY id',(before,)).fetchall()
    assert len(calls)==2
    artifact=store.read_task_artifact(artifact_id)
    chief=store.find_chief_task_report(artifact_id)
    step={'ordinal':1,'employee_id':plan['steps'][0]['employee_id'],
          'artifact_id':artifact_id,'department':plan['steps'][0]['department'],
          'worker_call_id':calls[0][0],'chief_call_id':calls[1][0],
          'artifact_sha256':artifact['sha256'],
          'chief_report_sha256':chief['sha256']}
    checkpoint={'campaign_id':plan['id'],'completed_tasks':1,'steps':[step]}
    assert real30._resume_fixture(LocalStore(store.path),cli,gguf,checkpoint)==(task,plan['id'],1)
    # Valid model call from the SAME employee, but not the model call for this run.
    with store._connect() as con:
        model=store.read_employee_model(step['employee_id'])['model_id']
        con.execute('''INSERT INTO ai_model_call_history
            (employee_id,model_id,model_name,status,prompt_chars,output_chars)
            VALUES (?,?,?,'success',10,10)''',(step['employee_id'],model,'fixture only'))
        unrelated=con.execute('SELECT MAX(id) FROM ai_model_call_history').fetchone()[0]
    wrong={**checkpoint,'steps':[{**step,'worker_call_id':unrelated,'chief_call_id':unrelated+1}]}
    with pytest.raises(ValueError,match='GGUF'):
        real30._resume_fixture(LocalStore(store.path),cli,gguf,wrong)
    with store._connect() as con:
        con.execute('UPDATE company_task_artifacts SET body=? WHERE id=?',
                    ('다른 본문으로 변조',artifact_id))
    with pytest.raises(ValueError,match='체크포인트|무결성'):
        real30._resume_fixture(LocalStore(store.path),cli,gguf,checkpoint)


def test_atomic_checkpoint_keeps_previous_file_on_failed_replace(tmp_path,monkeypatch):
    checkpoint=tmp_path/'checkpoint.json'
    checkpoint.write_text('{"previous":true}',encoding='utf-8')
    def failed_replace(src,dst):
        raise OSError('simulated interrupted atomic replacement')
    monkeypatch.setattr(real30.os,'replace',failed_replace)
    with pytest.raises(OSError,match='interrupted'):
        real30._save_checkpoint_atomic(checkpoint,{'completed_tasks':1})
    assert checkpoint.read_text(encoding='utf-8')=='{"previous":true}'
    assert not list(tmp_path.glob('.aiwack-checkpoint-*'))
    monkeypatch.undo()
    real30._save_checkpoint_atomic(checkpoint,{'completed_tasks':1,'success':False})
    import json
    assert json.loads(checkpoint.read_text(encoding='utf-8'))=={
        'completed_tasks':1,'success':False}
