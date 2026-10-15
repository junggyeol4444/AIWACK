"""Owner-gated real chief→worker handoff, no fake autonomous workflow.

POSIX test executable is a synthetic subprocess. Windows uses a separately
built native Windows EXE in the CI integration workflow.
"""
from __future__ import annotations

import os
import threading

import pytest
from desktop.model_runtime import ModelConfig
from desktop.storage import AuthenticationError, LocalStore
from desktop import company_operations as ops


@pytest.fixture
def company(tmp_path):
    store=LocalStore(tmp_path/'chief_company.sqlite3')
    store.setup_owner('chief_owner','chief-owner-test-password-2026')
    chief=store.add_employee_draft('chief_runtime','총괄 AI')
    staff=store.add_employee_draft('staff_runtime','실무 직원')
    store.assign_reporting_line(chief,'ceo')
    task=ops.create_task(store,'실제 직원 보고서','총괄 AI의 작업 지시가 선행되어야 합니다.')
    assert ops.assign_task(store,task)['employee_id']==staff
    return store,chief,staff,task


def test_chief_draft_is_not_an_approved_task(company,monkeypatch):
    store,chief,staff,task=company
    prompts=[]
    def responder(_store,prompt,**kwargs):
        prompts.append(prompt)
        return '담당 직원에게 시장 조사를 요청하세요.'
    monkeypatch.setattr('desktop.chief_task_runtime.invoke_chief_model',responder)
    draft=ops.draft_chief_order(store,task,'조사 업무 계획 수립')
    assert draft['task_id']==task and draft['chief_model_called']
    assert draft['owner_approved'] is False and draft['worker_executed'] is False
    assert len(prompts)==1 and '조사 업무 계획 수립' in prompts[0]
    assert store.read_chief_task_order(task) is None
    assert store.list_task_runs(task)==[]
    assert store.list_task_artifacts(task)==[]


def test_owner_explicitly_approves_then_worker_executes_and_saves(company,monkeypatch):
    store,chief,staff,task=company
    runner=__import__('pathlib').Path(__import__('sys').executable)
    mid=store.add_local_model(ModelConfig('Synthetic chief/worker','llamafile',str(runner),'',32))
    store.set_employee_model(chief,mid)
    store.set_employee_model(staff,mid)
    monkeypatch.setattr('desktop.chief_task_runtime.invoke_chief_model',
                        lambda *a,**kw:'직원에게 실제 조사 업무를 지시합니다.')
    proposal=ops.draft_chief_order(store,task,'시장 정보 검증')
    assert store.read_chief_task_order(task) is None
    order=ops.approve_chief_order(store,task,proposal['instruction'])
    assert store.read_chief_task_order(task)['id']==order
    executed=[]
    def staff_response(_config,prompt,**kwargs):
        executed.append(prompt)
        return 'SYNTHETIC WORKER OUTPUT, NOT A GGUF RESULT'
    monkeypatch.setattr('desktop.task_runtime.run_local_model',staff_response)
    response=ops.execute_task(store,task)
    assert response['status']=='awaiting_owner_review'
    assert '직원에게 실제 조사 업무' in executed[0]
    assert store.read_task_artifact(response['artifact_id'])['review_status']=='pending'
    assert store.read_task(task)['status']=='in_progress'
    store.review_task_artifact(response['artifact_id'],'approved')
    ops.finalize_approved_artifact(store,response['artifact_id'])
    assert store.read_task(task)['status']=='done'
    store.logout()
    reopened=LocalStore(store.path)
    reopened.login('chief_owner','chief-owner-test-password-2026')
    assert reopened.read_chief_task_order(task)['instruction']==proposal['instruction']
    assert reopened.read_task(task)['status']=='done'
    assert not ops.company_snapshot(reopened)['actual_sales_verified']


def test_invalid_or_cancelled_chief_draft_is_not_persisted(company,monkeypatch):
    store,chief,staff,task=company
    for bad in (True,0,-1,'1'):
        with pytest.raises(ValueError):ops.draft_chief_order(store,bad,'목표')
    for bad in ('',' ','x'*501,'bad\x00input'):
        with pytest.raises(ValueError):ops.draft_chief_order(store,task,bad)
    cancelled=threading.Event();cancelled.set()
    with pytest.raises(InterruptedError):ops.draft_chief_order(store,task,'목표',cancel=cancelled)
    assert store.read_chief_task_order(task) is None
    monkeypatch.setattr('desktop.chief_task_runtime.invoke_chief_model',lambda *a,**kw:'X'*601)
    with pytest.raises(ValueError,match='600'):
        ops.draft_chief_order(store,task,'목표')
    assert store.read_chief_task_order(task) is None


def test_duplicate_approval_and_emergency_stop_rejected(company,monkeypatch):
    store,chief,staff,task=company
    with pytest.raises(ValueError):ops.approve_chief_order(store,task,'모델 미배정 지시')
    mid=store.add_local_model(ModelConfig('stub','llamafile',__import__('sys').executable,'',24))
    store.set_employee_model(chief,mid)
    store.set_employee_model(staff,mid)
    order=ops.approve_chief_order(store,task,'관리자가 지정한 직원 지시')
    assert store.read_chief_task_order(task)['id']==order
    with pytest.raises(ValueError,match='이미 승인'):
        ops.approve_chief_order(store,task,'새로운 지시')
    store.emergency_stop_local(True,'수동 비상 정지')
    with pytest.raises(PermissionError,match='비상'):
        ops.draft_chief_order(store,task,'목표')
    with pytest.raises(PermissionError,match='비상'):
        ops.approve_chief_order(store,task,'취소된 지시')


def test_chief_order_owner_authentication(company):
    store,chief,staff,task=company
    store.logout()
    with pytest.raises(AuthenticationError):ops.draft_chief_order(store,task,'목표')
    with pytest.raises(AuthenticationError):ops.approve_chief_order(store,task,'지시')


@pytest.mark.skipif(os.name=='nt',reason='POSIX helper; Windows-native model stub validated by workflow')
def test_real_chief_and_worker_subprocess_without_network(company,tmp_path):
    store,chief,staff,task=company
    runner=tmp_path/'native-stub'
    runner.write_text('#!/usr/bin/env python3\nprint("ACTUAL_OS_SUBPROCESS_NOT_REAL_AI")\n',encoding='utf-8')
    runner.chmod(0o700)
    gguf=tmp_path/'dummy.gguf'
    gguf.write_bytes(b'GGUF\x03\x00\x00\x00')
    mid=store.add_local_model(ModelConfig('POSIX stub','llama_cpp',str(runner),str(gguf),24))
    store.set_employee_model(chief,mid)
    store.set_employee_model(staff,mid)
    draft=ops.draft_chief_order(store,task,'직원에게 업무 위임')
    assert 'ACTUAL_OS_SUBPROCESS_NOT_REAL_AI' in draft['instruction']
    assert store.read_chief_task_order(task) is None
    ops.approve_chief_order(store,task,draft['instruction'])
    result=ops.execute_task(store,task)
    assert 'ACTUAL_OS_SUBPROCESS_NOT_REAL_AI' in result['response']
    assert len(store.list_employee_model_calls(chief))==1
    assert len(store.list_employee_model_calls(staff))==1
