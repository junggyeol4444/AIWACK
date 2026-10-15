"""Real SQLite owner approval boundaries for company planning UI and chief draft."""
from __future__ import annotations

import json
import threading
import pytest
from desktop.storage import LocalStore, AuthenticationError
from desktop import company_operations as ops


@pytest.fixture
def owner(tmp_path):
    s=LocalStore(tmp_path/'ai-company.sqlite3')
    s.setup_owner('planning_owner','planning-owner-password-2026')
    return s


def active_goal(s,title='Grow useful local products'):
    goal=s.add_goal(title)
    s.update_goal(goal,title,'','active')
    return goal


def test_first_company_screen_never_fabricates_chief_proposals(owner):
    data=ops.company_snapshot(owner)
    assert data['pending_proposals']==0
    assert ops.planning_proposals(owner)==[]
    assert owner.list_tasks()==[]


def test_owner_visible_rule_scanner_never_invokes_an_ai_model(owner,monkeypatch):
    active_goal(owner)
    def forbidden(*args,**kwargs):
        raise AssertionError('rule scan must not call a model')
    monkeypatch.setattr(ops,'invoke_chief_model',forbidden)
    response=ops.scan_planning_proposals(owner)
    assert response['pending_count']==1
    assert len(response['created_ids'])==1
    assert len(ops.planning_proposals(owner))==1
    row=ops.planning_proposals(owner)[0]
    assert row['origin']=='rule' and row['status']=='pending'
    assert owner.list_tasks()==[]
    assert ops.scan_planning_proposals(owner)['created_ids']==[]


def test_manual_approval_creates_exactly_one_inert_task(owner):
    active_goal(owner)
    row_id=ops.scan_planning_proposals(owner)['created_ids'][0]
    task_id=ops.approve_planning_proposal(owner,row_id)
    assert task_id>0
    assert owner.read_task(task_id)['status']=='todo'
    assert owner.list_task_runs(task_id)==[]
    assert ops.company_snapshot(owner)['pending_proposals']==0
    assert ops.planning_proposals(owner)[0]['approved_task_id']==task_id
    with pytest.raises(ValueError):ops.approve_planning_proposal(owner,row_id)


def test_rejection_does_not_create_any_task(owner):
    active_goal(owner)
    pid=ops.scan_planning_proposals(owner)['created_ids'][0]
    ops.reject_planning_proposal(owner,pid)
    assert owner.list_tasks()==[]
    assert ops.planning_proposals(owner)[0]['status']=='rejected'
    with pytest.raises(ValueError):ops.reject_planning_proposal(owner,pid)


def test_chief_refines_a_draft_but_never_auto_approves(owner,monkeypatch):
    active_goal(owner)
    pid=ops.scan_planning_proposals(owner)['created_ids'][0]
    calls=[]
    def model(*args,**kwargs):
        calls.append((args,kwargs))
        return json.dumps({'title':'실제 AI 제품 조사 준비',
                           'description':'가격과 수요는 확인 전입니다. 공개 근거를 조사하고 검수받으세요.'},ensure_ascii=False)
    monkeypatch.setattr(ops,'invoke_chief_model',model)
    result=ops.refine_planning_proposal(owner,pid)
    assert len(calls)==1 and calls[0][1]['timeout']==60
    assert result['chief_model_called'] and result['state']=='awaiting_owner_approval'
    assert result['task_created'] is False
    assert owner.list_tasks()==[]
    row=ops.planning_proposals(owner)[0]
    assert row['origin']=='local_ai'
    assert row['title']==result['title']
    with pytest.raises(ValueError):ops.refine_planning_proposal(owner,pid)
    task=ops.approve_planning_proposal(owner,pid)
    assert owner.read_task(task)['title']==result['title']
    assert owner.list_task_runs(task)==[]


@pytest.mark.parametrize('reply',[
    'not-json', '{}', '[]', '"hello"',
    '{"title":"", "description":"test"}',
    '{"title":"ok", "description":""}',
    '{"title":"ok", "description":"detail", "execute":true}',
    '{"title":null, "description":"detail"}',
])
def test_malformed_chief_text_is_not_saved(owner,monkeypatch,reply):
    active_goal(owner)
    pid=ops.scan_planning_proposals(owner)['created_ids'][0]
    monkeypatch.setattr(ops,'invoke_chief_model',lambda *a,**k:reply)
    with pytest.raises(ValueError):ops.refine_planning_proposal(owner,pid)
    row=ops.planning_proposals(owner)[0]
    assert row['status']=='pending' and row['origin']=='rule'
    assert owner.list_tasks()==[]


def test_markdown_fenced_json_accepted_as_data_only(owner,monkeypatch):
    active_goal(owner)
    pid=ops.scan_planning_proposals(owner)['created_ids'][0]
    monkeypatch.setattr(ops,'invoke_chief_model',lambda *a,**k:'```json\n{"title":"draft", "description":"check facts"}\n```')
    assert ops.refine_planning_proposal(owner,pid)['title']=='draft'
    assert owner.list_tasks()==[]


def test_concurrent_source_change_prevents_model_draft_persistence(owner,monkeypatch):
    goal=active_goal(owner)
    pid=ops.scan_planning_proposals(owner)['created_ids'][0]
    def model(*args,**kwargs):
        owner.add_work_plan(goal,'Owner new plan','',['step'],'draft')
        return '{"title":"old draft", "description":"obsolete"}'
    monkeypatch.setattr(ops,'invoke_chief_model',model)
    with pytest.raises(ValueError,match='변경'):ops.refine_planning_proposal(owner,pid)
    assert owner.list_tasks()==[]
    assert ops.planning_proposals(owner)[0]['status']=='stale'


def test_emergency_stop_blocks_real_chief_model_call(owner,monkeypatch):
    active_goal(owner)
    pid=ops.scan_planning_proposals(owner)['created_ids'][0]
    owner.emergency_stop_local(True,'operator paused')
    monkeypatch.setattr(ops,'invoke_chief_model',lambda *a,**k:pytest.fail('not allowed'))
    with pytest.raises(PermissionError):ops.refine_planning_proposal(owner,pid)
    assert ops.planning_proposals(owner)[0]['origin']=='rule'
    # local non-executing proposals may still be read during emergency stop
    assert len(ops.planning_proposals(owner))==1


def test_logout_and_cancellation_never_store_model_draft(owner,monkeypatch):
    active_goal(owner)
    pid=ops.scan_planning_proposals(owner)['created_ids'][0]
    cancel=threading.Event()
    def model(*args,**kwargs):
        cancel.set()
        return '{"title":"late result", "description":"not persisted"}'
    monkeypatch.setattr(ops,'invoke_chief_model',model)
    with pytest.raises(InterruptedError):ops.refine_planning_proposal(owner,pid,cancel=cancel)
    assert ops.planning_proposals(owner)[0]['origin']=='rule'
    owner.logout()
    for call in (lambda:ops.company_snapshot(owner),lambda:ops.scan_planning_proposals(owner),
                 lambda:ops.planning_proposals(owner),lambda:ops.approve_planning_proposal(owner,pid),
                 lambda:ops.reject_planning_proposal(owner,pid),lambda:ops.refine_planning_proposal(owner,pid)):
        with pytest.raises(AuthenticationError):call()


def test_reopen_persisted_proposals_and_owner_approval(owner):
    active_goal(owner)
    pid=ops.scan_planning_proposals(owner)['created_ids'][0]
    owner.logout()
    fresh=LocalStore(owner.path)
    fresh.login('planning_owner','planning-owner-password-2026')
    assert ops.planning_proposals(fresh)[0]['id']==pid
    task=ops.approve_planning_proposal(fresh,pid)
    assert fresh.read_task(task)['status']=='todo'


def test_strict_output_limits_and_parameter_guards(owner):
    for text in ('', 'hello', '[]', '```not json```'):
        with pytest.raises(ValueError):ops._parse_chief_proposal(text)
    for field in ({'title':'a'*121,'description':'ok'},
                  {'title':'ok','description':'x'*1501}):
        with pytest.raises(ValueError):ops._parse_chief_proposal(json.dumps(field))
    for invalid in (True,0,101,-1,'1'):
        with pytest.raises(ValueError):ops.planning_proposals(owner,limit=invalid)


def test_owner_can_create_active_goal_then_approve_proposal_in_one_flow(owner):
    goal=ops.create_active_company_goal(owner,'Ship a useful accessible Windows product')
    assert owner.list_goals()[0]['status']=='active'
    proposal=ops.scan_planning_proposals(owner)['created_ids'][0]
    rows=ops.planning_proposals(owner)
    assert rows[0]['source_id']==goal and rows[0]['origin']=='rule'
    assert owner.list_tasks()==[]
    task=ops.approve_planning_proposal(owner,proposal)
    assert owner.read_task(task)['status']=='todo'
    assert owner.list_task_runs(task)==[]


def test_create_goal_rejects_invalid_titles_and_requires_login(owner):
    for title in ('','  ','a'*121,None,True):
        with pytest.raises(ValueError):ops.create_active_company_goal(owner,title)
    assert owner.list_goals()==[]
    owner.logout()
    with pytest.raises(AuthenticationError):ops.create_active_company_goal(owner,'cannot')
