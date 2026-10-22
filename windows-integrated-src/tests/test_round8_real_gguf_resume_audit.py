"""Round 8 structural regressions; NO real GGUF inference or Windows clicks."""
from __future__ import annotations
import hashlib
import sqlite3
import sys
from pathlib import Path
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from validation import windows_real_30_step_campaign_e2e as real30
from desktop.storage import LocalStore
from desktop.model_runtime import ModelConfig
from desktop import company_operations as ops
from desktop import company_wide_campaign as wide


def _fixture(tmp_path):
    db=LocalStore(tmp_path/'ephemeral_31_agent_campaign.sqlite3')
    db.setup_owner(real30.USER,real30.PASSWORD)
    ops.initialize_company_blueprint(db)
    model_file=tmp_path/'fixture.gguf'
    model_file.write_bytes(b'GGUF' + b'\x00'*8)
    cli=Path(sys.executable).resolve()
    model=db.add_local_model(ModelConfig('structural test only','llama_cpp',str(cli),str(model_file),256))
    for employee in db.list_employee_records():
        db.set_employee_model(employee['id'],model)
    task=ops.create_task(db,'15부서 실제 GGUF 고객 지원 프로젝트',
                         '고객지원 정책과 문서 작성 및 품질 점검')
    return db,cli,model_file.resolve(),task


def test_resume_fixture_requires_original_model_and_31_bindings(tmp_path):
    db,cli,gguf,task=_fixture(tmp_path)
    checkpoint={'completed_tasks':0,'steps':[]}
    assert real30._resume_fixture(LocalStore(db.path),cli,gguf,checkpoint)==(task,None,0)
    with pytest.raises(ValueError,match='모델'):
        real30._resume_fixture(LocalStore(db.path),cli,tmp_path/'wrong.gguf',checkpoint)
    last=db.list_employee_records()[-1]['id']
    db.set_employee_model(last,None)
    with pytest.raises(ValueError,match='31명'):
        real30._resume_fixture(LocalStore(db.path),cli,gguf,checkpoint)


def test_resume_fixture_never_approves_draft_or_skips_checkpoint(tmp_path,monkeypatch):
    db,cli,gguf,task=_fixture(tmp_path)
    def chief_text(config,prompt,**kwargs):
        names=prompt.rsplit('담당 부서: ',1)[1].split(', ')
        return '\n'.join(f'{name}|실제 검수 항목|{name} 업무 품질 기준 문서를 작성하고 검증한다' for name in names)
    monkeypatch.setattr('desktop.employee_model_runtime.run_local_model',chief_text)
    plan=wide.propose(db,task)
    with pytest.raises(ValueError,match='초안'):
        real30._resume_fixture(LocalStore(db.path),cli,gguf,
                               {'campaign_id':plan['id'],'completed_tasks':0,'steps':[]})
    wide.approve(db,plan['id'])
    checkpoint={'campaign_id':plan['id'],'completed_tasks':0,'steps':[]}
    assert real30._resume_fixture(LocalStore(db.path),cli,gguf,checkpoint)==(task,plan['id'],0)
    with pytest.raises(ValueError,match='체크포인트'):
        real30._resume_fixture(LocalStore(db.path),cli,gguf,
                               {'campaign_id':plan['id'],'completed_tasks':1,'steps':[]})
    with db._connect() as con:
        first=wide.read(db,plan['id'])['steps'][0]['task_id']
        con.execute('''INSERT INTO ai_model_call_history
            (employee_id,model_id,model_name,status,prompt_chars,output_chars)
            VALUES (?,?,?,'success',10,10)''',(2,1,'structural test only'))
        call=con.execute('SELECT MAX(id) FROM ai_model_call_history').fetchone()[0]
        con.execute('''INSERT INTO company_task_runs
            (task_id,employee_id,model_id,model_name,model_call_id,status,prompt_chars)
            VALUES (?,?,?,?,?,'running',10)''',(first,2,1,'structural test only',call))
    with pytest.raises(ValueError,match='미완료 모델 실행'):
        real30._resume_fixture(LocalStore(db.path),cli,gguf,checkpoint)


def test_genuine_chief_parse_attempts_persist_bounded_completion_diagnostics(tmp_path,monkeypatch):
    db,cli,gguf,task=_fixture(tmp_path)
    calls=[]
    def chief_text(config,prompt,**kwargs):
        calls.append(prompt)
        names=prompt.rsplit('담당 부서: ',1)[1].split(', ')
        if len(calls)==1:
            return prompt+'\ninvalid 135M format'
        return '\n'.join(f'{name}|검증|{name}의 승인된 업무 결과를 검토한다' for name in names)
    monkeypatch.setattr('desktop.employee_model_runtime.run_local_model',chief_text)
    wide.propose(db,task)
    with db._connect() as con:
        rows=con.execute('''SELECT parsed,output_sha256,output_chars,completion_preview
            FROM aiwack_wide_chief_plan_attempts ORDER BY id''').fetchall()
        assert len(rows)==6
        assert rows[0][0]==0 and rows[0][2]>0
        assert rows[0][1]==hashlib.sha256((calls[0]+'\ninvalid 135M format').encode()).hexdigest()
        assert 'invalid 135M format' in rows[0][3]
        assert '담당 부서:' not in rows[0][3]
        assert all(len(x[1])==64 and x[2]>0 and len(x[3])<=240 for x in rows)
        with pytest.raises(sqlite3.DatabaseError):
            con.execute('DELETE FROM aiwack_wide_chief_plan_attempts WHERE id=1')


def test_additive_chief_audit_migration_keeps_legacy_row():
    with sqlite3.connect(':memory:') as con:
        con.execute('''CREATE TABLE aiwack_wide_chief_plan_attempts (
          id INTEGER PRIMARY KEY AUTOINCREMENT, source_task_id INTEGER NOT NULL,
          chief_employee_id INTEGER NOT NULL,model_call_id INTEGER NOT NULL UNIQUE,
          department_names TEXT NOT NULL,attempt_kind TEXT NOT NULL,
          parsed INTEGER NOT NULL,error_kind TEXT NOT NULL DEFAULT '',
          created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)''')
        con.execute('''INSERT INTO aiwack_wide_chief_plan_attempts
          (source_task_id,chief_employee_id,model_call_id,department_names,attempt_kind,parsed)
          VALUES(1,1,1,'기존부서','three_departments',0)''')
        wide.initialize(con)
        wide.initialize(con)
        row=con.execute('''SELECT department_names,output_sha256,output_chars,completion_preview
          FROM aiwack_wide_chief_plan_attempts WHERE id=1''').fetchone()
        assert row==('기존부서','',0,'')