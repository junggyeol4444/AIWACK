"""Round 11 structural regressions; not genuine Windows EXE/GGUF proof."""
from __future__ import annotations
import hashlib
import json
import sqlite3
import sys
from pathlib import Path
import pytest
from desktop.storage import LocalStore
from desktop.model_runtime import ModelConfig
from desktop import company_operations as ops
from desktop import company_wide_campaign as wide

sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from validation import windows_real_30_step_campaign_e2e as real30


def _office(tmp_path,monkeypatch):
    store=LocalStore(tmp_path/'round11.sqlite3')
    store.setup_owner('round11-owner','round11-test-password')
    ops.initialize_company_blueprint(store)
    model=store.add_local_model(ModelConfig('structural fixture','llamafile',sys.executable,'',32))
    for e in store.list_employee_records():
        store.set_employee_model(e['id'],model)
    source=ops.create_task(store,'원본 15부서 협업','모든 계획과 결과는 관리자 승인')
    def fake_chief(config,prompt,**kw):
        names=prompt.rsplit('담당 부서: ',1)[1].split(', ')
        return '\n'.join(f'{name}|원본 검증|{name}에서 업무 문서를 작성하고 실제 결과를 확인한다' for name in names)
    monkeypatch.setattr('desktop.employee_model_runtime.run_local_model',fake_chief)
    return store,source


def test_real_output_json_preamble_plans_and_strict_department_names():
    part=[(1,'시장조사부',2,3),(2,'상품기획부',4,5),(3,'고객지원부',6,7)]
    def data(name):
        return {'department':name,'title':'시장 검토','instruction':name+'에서 보고서를 작성하고 품질을 확인한다'}
    response='계획 초안:\n'+json.dumps({'plans':[data(x[1]) for x in part]},ensure_ascii=False)
    parsed=wide._parse_group(response,part)
    assert len(parsed)==3
    with pytest.raises(ValueError,match='없는 부서'):
        wide._parse_group(response.replace('고객지원부','존재하지않는부서'),part)
    with pytest.raises(ValueError,match='누락'):
        wide._parse_group('계획 초안:\n'+json.dumps({'plans':[data(x[1]) for x in part[:2]]},ensure_ascii=False),part)


def test_immutable_chief_draft_prevents_tamper_before_owner_approval(tmp_path,monkeypatch):
    store,source=_office(tmp_path,monkeypatch)
    draft=wide.propose(store,source)
    with store._connect() as con:
        original=con.execute('''SELECT title,plan_sha256 FROM aiwack_wide_campaign_steps
            WHERE campaign_id=? AND ordinal=1''',(draft['id'],)).fetchone()
        assert len(original[1])==64
        with pytest.raises(sqlite3.IntegrityError,match='초안은 수정'):
            con.execute('''UPDATE aiwack_wide_campaign_steps SET title=?
                WHERE campaign_id=? AND ordinal=1''',('임의 수정',draft['id']))
        assert con.execute('''SELECT title,plan_sha256 FROM aiwack_wide_campaign_steps
            WHERE campaign_id=? AND ordinal=1''',(draft['id'],)).fetchone()==original
    assert wide.approve(store,draft['id'])['state']=='approved'
    assert len(store.list_tasks())==31


def test_prepopulated_draft_task_link_rejected_without_orphan_tasks(tmp_path,monkeypatch):
    store,source=_office(tmp_path,monkeypatch)
    draft=wide.propose(store,source)
    with store._connect() as con:
        con.execute('''UPDATE aiwack_wide_campaign_steps SET task_id=?
            WHERE campaign_id=? AND ordinal=1''',(source,draft['id']))
    with pytest.raises(ValueError,match='이미 업무에 연결'):
        wide.approve(store,draft['id'])
    assert len(store.list_tasks())==1
    assert wide.read(store,draft['id'])['state']=='draft'


def test_rejected_resume_writes_separate_failure_without_mutating_original(tmp_path):
    checkpoint=tmp_path/'full_30_genuine_gguf_checkpoint.json'
    original=b'{"completed_tasks":4,"success":false,"steps":[1,2,3,4]}'
    checkpoint.write_bytes(original)
    path=real30._record_rejected_resume(tmp_path,checkpoint,{
        'completed_tasks':0,'success':True,'failure_kind':'ValueError'})
    assert checkpoint.read_bytes()==original
    report=json.loads(path.read_text(encoding='utf-8'))
    assert report['success'] is False
    assert report['failure_kind']=='ValueError'
    assert report['original_checkpoint_sha256']==hashlib.sha256(original).hexdigest()


def test_legacy_draft_without_seal_fails_closed(tmp_path,monkeypatch):
    store,source=_office(tmp_path,monkeypatch)
    draft=wide.propose(store,source)
    # Simulate a draft created by a pre-migration build; never silently
    # authorize an unsealed plan as if it were genuine current evidence.
    with store._connect() as con:
        con.execute('DROP TRIGGER aiwack_wide_draft_step_no_edit')
        con.execute('''UPDATE aiwack_wide_campaign_steps SET plan_sha256=''
            WHERE campaign_id=? AND ordinal=1''',(draft['id'],))
    with pytest.raises(ValueError,match='변경'):
        wide.approve(store,draft['id'])
    assert len(store.list_tasks())==1