"""Stage 30: verified chief -> staff order -> owner artifact -> chief report."""
from __future__ import annotations

import hashlib
import os
import sqlite3
import threading

import pytest

from desktop.chief_task_runtime import propose_chief_task_order, collect_chief_task_result
from desktop.model_runtime import ModelConfig
from desktop.storage import AuthenticationError, LocalStore
from desktop.task_runtime import invoke_task_execution


@pytest.fixture
def setup(tmp_path):
    store=LocalStore(tmp_path/'handoff.sqlite3')
    store.setup_owner('owner30','very-secure-stage30-password')
    chief=store.add_employee_draft('chief_stage30','총괄 AI')
    worker=store.add_employee_draft('worker_stage30','담당 AI')
    store.assign_reporting_line(chief,'ceo')
    task=store.add_task('시장 조사','한국어 텍스트 초안 작성')
    assert store.auto_assign_task(task)['employee_id']==worker
    runner=tmp_path/'offline-cli'
    runner.write_text('#!/usr/bin/env python3\nprint("STAGE30_LOCAL_TEXT")\n',encoding='utf-8')
    runner.chmod(0o700)
    if os.name == 'nt':
        runner = __import__('pathlib').Path(__import__('sys').executable)
    gguf=tmp_path/'fixture.gguf';gguf.write_bytes(b'GGUF\x03\x00\x00\x00')
    model=store.add_local_model(ModelConfig('stage30 local','llama_cpp',str(runner),str(gguf),16))
    store.set_employee_model(chief,model)
    store.set_employee_model(worker,model)
    return store,chief,worker,task


def test_full_owner_approved_roundtrip(setup,monkeypatch):
    db,chief,worker,task=setup
    monkeypatch.setattr('desktop.chief_task_runtime.invoke_chief_model',lambda *a,**k:'승인 전 지시 초안')
    assert propose_chief_task_order(db,task,'정확한 시장 정보')=='승인 전 지시 초안'
    assert db.read_chief_task_order(task) is None  # chief does not approve itself
    assert db.list_task_runs(task)==[]
    order=db.approve_chief_task_order(task,'승인 전 지시 초안')
    assert db.read_chief_task_order(task)['id']==order
    captured=[]
    def fake_worker(config,prompt,**kwargs):
        captured.append(prompt)
        return '직원 초안 텍스트'
    monkeypatch.setattr('desktop.task_runtime.run_local_model',fake_worker)
    assert invoke_task_execution(db,task)=='직원 초안 텍스트'
    assert '승인 전 지시 초안' in captured[0]
    assert db.list_task_artifacts(task)==[]  # explicit owner save required
    run=db.list_task_runs(task)[0]
    artifact=db.save_task_artifact(task,run['id'],'검토 초안','직원 초안 텍스트')
    monkeypatch.setattr('desktop.chief_task_runtime.invoke_chief_model',
                        lambda _db,prompt,**kw: '회수 검토 의견' if '직원 초안 텍스트' in prompt else 'ERROR')
    assert collect_chief_task_result(db,artifact)=='회수 검토 의견'
    assert db.find_chief_task_report(artifact) is None  # explicit save required
    report=db.save_chief_task_report(artifact,'회수 검토 의견')
    assert db.read_chief_task_report(report)['sha256']==hashlib.sha256('회수 검토 의견'.encode()).hexdigest()
    db.review_chief_task_report(report,'accepted','관리자 확인')
    assert db.read_chief_task_report(report)['owner_decision']=='accepted'
    assert db.read_task(task)['status']=='in_progress'  # no auto-completion
    db.logout()
    reopened=LocalStore(db.path)
    reopened.login('owner30','very-secure-stage30-password')
    assert reopened.read_chief_task_order(task)['instruction']=='승인 전 지시 초안'
    assert reopened.read_chief_task_report(report)['body']=='회수 검토 의견'
    assert reopened.read_chief_task_report(report)['owner_note']=='관리자 확인'
    with sqlite3.connect(db.path) as con:
        assert con.execute('PRAGMA foreign_key_check').fetchall()==[]
        assert con.execute('SELECT run_id FROM company_chief_task_dispatches WHERE order_id=?',(order,)).fetchone()[0]==run['id']


def test_no_approval_no_dispatch_and_unrelated_tasks_unchanged(setup,monkeypatch):
    db,chief,worker,task=setup
    other=db.add_task('기존 방식')
    assert db.auto_assign_task(other)['employee_id']==worker
    monkeypatch.setattr('desktop.task_runtime.run_local_model',lambda *a,**kw:'OK')
    assert invoke_task_execution(db,other)=='OK'
    assert db.read_chief_task_order(task) is None
    assert db.list_task_runs(task)==[]


def test_duplicate_and_wrong_state_denied(setup,monkeypatch):
    db,chief,worker,task=setup
    db.approve_chief_task_order(task,'첫 지시')
    with pytest.raises(ValueError,match='이미 승인'):
        db.approve_chief_task_order(task,'둘째 지시')
    monkeypatch.setattr('desktop.task_runtime.run_local_model',lambda *a,**kw:'OK')
    invoke_task_execution(db,task)
    db.set_task_status(task,'blocked')
    db.set_task_status(task,'todo')
    with pytest.raises(ValueError,match='이미 실행'):
        invoke_task_execution(db,task)
    with pytest.raises(ValueError,match='할 일|이미 실행'):
        db.approve_chief_task_order(task,'새 지시')


def test_stale_task_or_assignment_denied(setup):
    db,chief,worker,task=setup
    db.approve_chief_task_order(task,'고정된 지시')
    db.update_task(task,'변경된 제목','다른 내용')
    with pytest.raises(ValueError,match='업무 내용'):
        db.begin_task_execution(task)
    assert db.list_task_runs(task)==[]
    db.update_task(task,'시장 조사','한국어 텍스트 초안 작성')
    db.clear_task_assignment(task)
    with pytest.raises(ValueError,match='담당'):
        db.begin_task_execution(task)
    assert db.list_task_runs(task)==[]


def test_chief_revocation_denies_dispatch_and_collect(setup,monkeypatch):
    db,chief,worker,task=setup
    db.approve_chief_task_order(task,'지시')
    db.unassign_reporting_line(chief)
    with pytest.raises(ValueError,match='총괄 AI'):
        db.begin_task_execution(task)
    assert db.list_task_runs(task)==[]


def test_invalid_input_and_authentication(setup,monkeypatch):
    db,chief,worker,task=setup
    for objective in ('',' '*3,'x'*501,'bad\x00input'):
        with pytest.raises(ValueError):
            propose_chief_task_order(db,task,objective)
    for instruction in ('',' '*3,'x'*601,'bad\x00input'):
        with pytest.raises(ValueError):
            db.approve_chief_task_order(task,instruction)
    db.logout()
    for op in (lambda:db.approve_chief_task_order(task,'지시'),
               lambda:db.read_chief_task_order(task),
               lambda:db.chief_task_report_context(1),
               lambda:db.save_chief_task_report(1,'본문'),
               lambda:db.find_chief_task_report(1)):
        with pytest.raises(AuthenticationError):
            op()


def test_non_chief_artifact_cannot_be_collected(setup,monkeypatch):
    db,chief,worker,task=setup
    monkeypatch.setattr('desktop.task_runtime.run_local_model',lambda *a,**kw:'worker output')
    invoke_task_execution(db,task)
    run=db.list_task_runs(task)[0]
    artifact=db.save_task_artifact(task,run['id'],'제목','worker output')
    with pytest.raises(ValueError,match='총괄 AI 지시'):
        collect_chief_task_result(db,artifact)
    with pytest.raises(ValueError,match='승인된 지시'):
        db.save_chief_task_report(artifact,'report')


def test_chief_result_length_and_report_immutability(setup,monkeypatch):
    db,chief,worker,task=setup
    db.approve_chief_task_order(task,'승인 지시')
    monkeypatch.setattr('desktop.task_runtime.run_local_model',lambda *a,**kw:'output')
    invoke_task_execution(db,task)
    run=db.list_task_runs(task)[0]
    artifact=db.save_task_artifact(task,run['id'],'제목','x'*1601)
    with pytest.raises(ValueError,match='1600'):
        collect_chief_task_result(db,artifact)
    report=db.save_chief_task_report(artifact,'회수 보고서')
    with pytest.raises(ValueError,match='이미 저장'):
        db.save_chief_task_report(artifact,'다른 보고서')
    with pytest.raises(ValueError):
        db.review_chief_task_report(report,'bad')
    db.review_chief_task_report(report,'rejected')
    with pytest.raises(ValueError,match='이미 검토'):
        db.review_chief_task_report(report,'accepted')
    assert db.read_task(task)['status']=='in_progress'


@pytest.mark.skipif(os.name=='nt',reason='POSIX CLI fixture; Windows real EXE untested')
def test_real_local_chief_worker_cli_no_network(setup,monkeypatch):
    db,chief,worker,task=setup
    monkeypatch.setattr('socket.socket.connect',lambda *a,**kw: (_ for _ in ()).throw(AssertionError('network')))
    assert 'STAGE30_LOCAL_TEXT' in propose_chief_task_order(db,task,'로컬만')
    db.approve_chief_task_order(task,'로컬 직원 지시')
    assert 'STAGE30_LOCAL_TEXT' in invoke_task_execution(db,task)
    run=db.list_task_runs(task)[0]
    artifact=db.save_task_artifact(task,run['id'],'결과','로컬 결과')
    assert 'STAGE30_LOCAL_TEXT' in collect_chief_task_result(db,artifact)
    assert len(db.list_employee_model_calls(chief))==2
    assert len(db.list_employee_model_calls(worker))==1
