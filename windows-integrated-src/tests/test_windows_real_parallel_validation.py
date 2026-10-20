"""Regression for the Windows real-GGUF validator's DB lifetime and overlap proof."""
from __future__ import annotations

from pathlib import Path
import sqlite3
import pytest

import sys
# The validator lives at repository root; desktop must stay the native app.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from validation.windows_real_parallel_company_e2e import (
    verify_sqlite_integrity, actual_overlap_seconds,
)


def test_integrity_check_closes_database_before_file_cleanup(tmp_path):
    db = tmp_path / 'company.sqlite3'
    con = sqlite3.connect(db)
    try:
        con.execute('CREATE TABLE test_data (id INTEGER PRIMARY KEY)')
        con.execute('INSERT INTO test_data VALUES (1)')
        con.commit()
    finally:
        con.close()
    verify_sqlite_integrity(db)
    db.unlink()
    assert not db.exists()


def test_integrity_check_refuses_invalid_foreign_key_and_closes_connection(tmp_path):
    db = tmp_path / 'invalid_foreign_key.sqlite3'
    con = sqlite3.connect(db)
    try:
        con.execute('PRAGMA foreign_keys = OFF')
        con.execute('CREATE TABLE parent (id INTEGER PRIMARY KEY)')
        con.execute('CREATE TABLE child (parent_id INTEGER REFERENCES parent(id))')
        con.execute('INSERT INTO child VALUES (99)')
        con.commit()
    finally:
        con.close()
    with pytest.raises(AssertionError, match='foreign-key'):
        verify_sqlite_integrity(db)
    db.unlink()
    assert not db.exists()


def test_inference_overlap_requires_actual_intersection():
    assert actual_overlap_seconds([(1.0, 3.0), (2.0, 4.0)]) == 1.0
    assert actual_overlap_seconds([(1.0, 2.0), (2.0, 3.0)]) == 0.0
    assert actual_overlap_seconds([(1.0, 2.0), (3.0, 4.0)]) < 0


@pytest.mark.parametrize('invalid', [[], [(1.0, 2.0)], [(2.0, 1.0), (1.0, 3.0)]])
def test_inference_overlap_refuses_bad_or_missing_measurements(invalid):
    with pytest.raises(AssertionError):
        actual_overlap_seconds(invalid)


def test_department_chain_owner_approval_and_real_sqlite(tmp_path,monkeypatch):
    from test_company_department_collaboration import _office
    from desktop import company_department_collaboration as chain
    from desktop import company_operations as ops
    db,seed,staff2=_office(tmp_path,monkeypatch)
    draft=chain.propose(db,seed)
    assert draft['state']=='draft' and len(db.list_tasks())==1
    plan=chain.approve(db,draft['id'])
    tasks=[step['task_id'] for step in plan['steps']]
    assert len(tasks)==2 and db.read_chief_task_order(tasks[0])
    assert not db.task_dependency_readiness(tasks[1])['ready']
    monkeypatch.setattr('desktop.task_runtime.run_local_model',
                        lambda *a,**k:'부서 직원 모델 검토 결과')
    monkeypatch.setattr('desktop.chief_task_runtime.collect_chief_task_result',
                        lambda *a,**k:'총괄 AI 검토 결과')
    result=ops.execute_approved_chief_cycle(db,tasks[0])
    assert db.read_task_artifact(result['artifact_id'])['review_status']=='pending'
    db.review_task_artifact(result['artifact_id'],'approved')
    with pytest.raises(ValueError, match='총괄 보고서'):
        ops.finalize_approved_artifact(db,result['artifact_id'])
    db.review_chief_task_report(result['report_id'],'accepted')
    ops.finalize_approved_artifact(db,result['artifact_id'])
    assert db.task_dependency_readiness(tasks[1])['ready']
    assert ops.execute_approved_chief_cycle(db,tasks[1])['owner_approval_required']


def test_department_chain_atomic_missing_model_rollback(tmp_path,monkeypatch):
    from test_company_department_collaboration import _office
    from desktop import company_department_collaboration as chain
    db,seed,staff2=_office(tmp_path,monkeypatch)
    draft=chain.propose(db,seed)
    db.set_employee_model(staff2,None)
    with pytest.raises(ValueError):
        chain.approve(db,draft['id'])
    assert len(db.list_tasks())==1
    assert chain.read_plan(db,draft['id'])['state']=='draft'


def test_department_chain_rejects_stale_owner_approval(tmp_path,monkeypatch):
    from test_company_department_collaboration import _office
    from desktop import company_department_collaboration as chain
    db,seed,staff2=_office(tmp_path,monkeypatch)
    draft=chain.propose(db,seed)
    db.update_task(seed,'기준 변경','재확인 필요')
    with pytest.raises(ValueError):
        chain.approve(db,draft['id'])
    assert len(db.list_tasks())==1
