"""Approved employee-to-employee collaboration and persistent company knowledge."""
import sys
import pytest
from desktop.model_runtime import ModelConfig
from desktop.storage import LocalStore, AuthenticationError
from desktop import company_operations as ops
from desktop import company_handoffs as h
from desktop import company_knowledge as knowledge


@pytest.fixture
def team(tmp_path,monkeypatch):
    store=LocalStore(tmp_path/'handoff.sqlite3')
    store.setup_owner('handoff_owner','handoff-owner-password-2026')
    employees=[store.add_employee_draft('handoff'+str(i),'Staff '+str(i)) for i in range(2)]
    model=store.add_local_model(ModelConfig('SYNTH','llamafile',sys.executable,'',32))
    for emp in employees:store.set_employee_model(emp,model)
    tasks=[]
    for i in range(2):
        tid=ops.create_task(store,'Handoff task '+str(i))
        assert ops.assign_task(store,tid)['employee_id']==employees[i]
        tasks.append(tid)
    store.add_task_dependency(tasks[1],tasks[0])
    prompts=[]
    def fake(config,prompt,*,timeout,cancel):
        prompts.append(prompt)
        return 'FIRST APPROVED WORK CONTENT '*8
    monkeypatch.setattr('desktop.task_runtime.run_local_model',fake)
    return store,tasks,prompts


def test_worker_receives_owner_approved_completed_predecessor_only(team):
    db,(first,second),prompts=team
    with pytest.raises(ValueError,match='선행'):ops.execute_task(db,second)
    assert prompts==[]
    result=ops.execute_task(db,first)
    db.review_task_artifact(result['artifact_id'],'approved')
    db.set_task_status(first,'done')
    next_result=ops.execute_task(db,second)
    assert next_result['artifact_id']>result['artifact_id']
    assert len(prompts)==2
    assert '참고 자료' in prompts[1]
    assert 'FIRST APPROVED WORK CONTENT' in prompts[1]
    assert 'FIRST APPROVED WORK CONTENT' not in prompts[0]
    assert len(prompts[1])<=3000
    assert db.list_task_runs(second)[0]['prompt_chars']==len(prompts[1])


def test_unapproved_predecessor_body_never_shared(team):
    db,(first,second),prompts=team
    ops.execute_task(db,first)
    db.set_task_status(first,'done')
    ops.execute_task(db,second)
    assert 'FIRST APPROVED WORK CONTENT' not in prompts[1]


def test_owner_approved_only_promotion_durable_and_idempotent(team):
    db,(first,second),prompts=team
    aid=ops.execute_task(db,first)['artifact_id']
    with pytest.raises(PermissionError):h.promote_approved(db,aid)
    assert h.list_promotions(db)==[]
    db.review_task_artifact(aid,'approved')
    promoted=h.promote_approved(db,aid)
    assert not promoted['existing'] and promoted['approved_by_owner']
    assert h.promote_approved(db,aid)['existing']
    assert len(h.list_promotions(db))==1
    with db._connect() as con:
        doc=knowledge.read(con,promoted['knowledge_id'])
        assert doc['kind']=='case_study'
        assert 'FIRST APPROVED WORK CONTENT' in doc['content']
    db.logout()
    opened=LocalStore(db.path)
    opened.login('handoff_owner','handoff-owner-password-2026')
    assert h.list_promotions(opened)[0]['knowledge_id']==promoted['knowledge_id']


def test_tampered_approved_body_does_not_become_shared_knowledge(team):
    db,(first,second),prompts=team
    aid=ops.execute_task(db,first)['artifact_id']
    db.review_task_artifact(aid,'approved')
    with db._connect() as con:
        con.execute('UPDATE company_task_artifacts SET body=? WHERE id=?',('TAMPERED',aid))
    with pytest.raises(ValueError,match='SHA256'):h.promote_approved(db,aid)
    assert h.list_promotions(db)==[]


def test_provenance_and_budget_validation(team):
    db,(first,second),prompts=team
    aid=ops.execute_task(db,first)['artifact_id']
    db.review_task_artifact(aid,'approved')
    db.set_task_status(first,'done')
    with db._connect() as con:
        output=h.dependency_context(con,second,budget=350)
        assert 0<len(output)<=350
        assert h.dependency_context(con,second,budget=30)==''
        for bad in (True,0):
            with pytest.raises(ValueError):h.dependency_context(con,bad)
    for bad in (True,0,'1'):
        with pytest.raises(ValueError):h.promote_approved(db,bad)


def test_logged_out_owner_cannot_access_promotion(team):
    db,(first,second),prompts=team
    db.logout()
    with pytest.raises(AuthenticationError):h.list_promotions(db)


def test_only_relevant_owner_promoted_knowledge_used_for_future_employee(team):
    db,(first,second),prompts=team
    aid=ops.execute_task(db,first)['artifact_id']
    db.review_task_artifact(aid,'approved')
    promoted=h.promote_approved(db,aid)
    assert promoted['knowledge_id']>0
    independent=ops.create_task(db,'Handoff task future','Owner-approved followup')
    # Both original workers are still registered; reuse staff 2, not running.
    staff_ids=[x['id'] for x in db.list_employee_records()
               if x['display_name']=='Staff 1']
    assert len(staff_ids)==1
    assigned=ops.assign_task(db,independent)
    assert assigned['employee_id']==staff_ids[0]
    ops.execute_task(db,independent)
    assert '공동 지식' in prompts[-1]
    assert 'FIRST APPROVED WORK CONTENT' in prompts[-1]
    assert len(prompts[-1])<=3000
    assert db.list_task_runs(independent)[0]['prompt_chars']==len(prompts[-1])


def test_irrelevant_or_non_promoted_knowledge_not_injected(team):
    db,(first,second),prompts=team
    aid=ops.execute_task(db,first)['artifact_id']
    db.review_task_artifact(aid,'approved')
    with db._connect() as con:
        assert h.curated_company_context(con,'Handoff task unrelated')==''
    h.promote_approved(db,aid)
    with db._connect() as con:
        assert h.curated_company_context(con,'Something completely unrelated')==''
        assert 0<len(h.curated_company_context(con,'Handoff task 2',budget=350))<=350
    for bad in (True,-1,999):
        with db._connect() as con:
            with pytest.raises(ValueError):
                h.curated_company_context(con,'Handoff task 2',budget=bad)
