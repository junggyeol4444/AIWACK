"""Stage31 offline monitor: real SQLite, owner permissions and no side effects."""
from __future__ import annotations

import json
import sqlite3

import pytest

from desktop.model_runtime import ModelConfig
from desktop.storage import AuthenticationError, LocalStore


@pytest.fixture
def store(tmp_path):
    db = LocalStore(tmp_path / 'health.sqlite3')
    db.setup_owner('health_owner', 'stage31-very-secure-password')
    return db


def make_running(db, tmp_path):
    staff = db.add_employee_draft('health_worker', '직원')
    task = db.add_task('오프라인 업무')
    assert db.auto_assign_task(task)['employee_id'] == staff
    runner = tmp_path / 'local-cli'
    runner.write_text('LOCAL FIXTURE', encoding='utf-8')
    if __import__('os').name == 'nt':
        runner = __import__('pathlib').Path(__import__('sys').executable)
    gguf = tmp_path / 'local.gguf'
    gguf.write_bytes(b'GGUF\x03\x00\x00\x00')
    model = db.add_local_model(ModelConfig('health-local', 'llama_cpp', str(runner), str(gguf), 16))
    db.set_employee_model(staff, model)
    run_id, _, _ = db.begin_task_execution(task)
    return task, run_id


def test_empty_database_ok_and_no_implicit_history(store):
    snap = store.read_company_health()
    assert snap['severity'] == 'ok'
    assert snap['metrics']['tasks_total'] == 0
    assert snap['issues'] == []
    assert store.list_company_health_checks() == []
    assert store.list_task_runs() == []


def test_aggregate_alerts_and_no_task_mutation(store):
    todo = store.add_task('민감한 제목: never persist raw')
    blocked = store.add_task('막힌 업무')
    store.set_task_status(blocked, 'blocked')
    completed = store.add_task('완료 업무')
    store.set_task_status(completed, 'in_progress')
    store.set_task_status(completed, 'done')
    before = store.list_tasks()
    report = store.check_company_health()
    assert report['severity'] == 'attention'
    assert report['metrics']['tasks_total'] == 3
    assert report['metrics']['blocked_tasks'] == 1
    assert report['metrics']['unassigned_tasks'] == 2
    assert report['metrics']['done'] == 1
    assert {x['code'] for x in report['issues']} == {'blocked_tasks', 'unassigned_tasks'}
    assert store.list_tasks() == before
    with sqlite3.connect(store.path) as con:
        payload = con.execute('SELECT metrics_json,issues_json FROM company_health_checks').fetchone()
    assert '민감한 제목' not in repr(payload)
    assert json.loads(payload[0])['tasks_total'] == 3
    assert json.loads(payload[1])[0]['count'] == 1
    assert store.list_task_runs() == []


def test_changed_snapshot_saved_and_identical_auto_deduplicated(store):
    first = store.check_company_health()
    assert first['recorded']
    second = store.check_company_health()
    assert not second['recorded']
    assert second['check_id'] == first['check_id']
    store.add_task('업무')
    third = store.check_company_health()
    assert third['recorded'] and third['check_id'] != first['check_id']
    assert len(store.list_company_health_checks()) == 2
    forced = store.check_company_health(force=True)
    assert forced['recorded'] and len(store.list_company_health_checks()) == 3
    assert len(store.list_company_health_checks(limit=1)) == 1
    with pytest.raises(ValueError):
        store.list_company_health_checks(limit=0)
    with pytest.raises(ValueError):
        store.list_company_health_checks(limit=True)
    with pytest.raises(ValueError):
        store.check_company_health(force='yes')


def test_hourly_refresh_without_changed_metrics(store):
    old = store.check_company_health()
    with sqlite3.connect(store.path) as con:
        con.execute("UPDATE company_health_checks SET checked_at=datetime('now','-2 hours')")
    renewed = store.check_company_health()
    assert renewed['recorded'] and renewed['check_id'] > old['check_id']


def test_stale_running_is_critical_and_read_only(store, tmp_path):
    task, run = make_running(store, tmp_path)
    fresh = store.read_company_health()
    assert fresh['metrics']['stale_runs'] == 0
    assert fresh['severity'] == 'ok'
    with sqlite3.connect(store.path) as con:
        con.execute("UPDATE company_task_runs SET started_at=datetime('now','-2 hours') WHERE id=?", (run,))
    critical = store.check_company_health()
    assert critical['severity'] == 'critical'
    assert critical['metrics']['stale_runs'] == 1
    assert store.list_task_runs(task)[0]['status'] == 'running'
    # Monitoring never automatically recovers, retries or cancels the run.
    assert store.read_task(task)['status'] == 'in_progress'
    store.recover_interrupted_task_run(run)
    assert store.read_company_health()['metrics']['stale_runs'] == 0


def test_recent_failure_24h_window(store, tmp_path):
    task, run = make_running(store, tmp_path)
    store.finish_task_execution(run, 'timeout', error_kind='TimeoutError')
    report = store.read_company_health()
    assert report['metrics']['recent_failures'] == 1
    assert report['severity'] == 'attention'
    with sqlite3.connect(store.path) as con:
        con.execute("UPDATE company_task_runs SET started_at=datetime('now','-25 hours') WHERE id=?", (run,))
    report = store.read_company_health()
    assert report['metrics']['recent_failures'] == 0
    assert report['metrics']['blocked_tasks'] == 1


def test_pending_artifact_and_chief_report_counts(store, tmp_path):
    task, run = make_running(store, tmp_path)
    store.finish_task_execution(run, 'success', output_chars=6)
    artifact = store.save_task_artifact(task, run, '보고서', '로컬 본문')
    assert store.read_company_health()['metrics']['pending_artifacts'] == 1
    store.review_task_artifact(artifact, 'approved')
    assert store.read_company_health()['metrics']['pending_artifacts'] == 0
    # Reports are checked by their own pending state; no model execution.
    chief = store.add_employee_draft('health_ceo', '총괄')
    store.assign_reporting_line(chief, 'ceo')
    with sqlite3.connect(store.path) as con:
        order = con.execute('''INSERT INTO company_chief_task_orders
            (task_id,chief_employee_id,worker_employee_id,instruction,task_fingerprint)
            SELECT ?,?,employee_id,'로컬 승인','0' || substr(hex(zeroblob(32)),2)
            FROM company_task_assignments WHERE task_id=?''', (task, chief, task)).lastrowid
        con.execute('''INSERT INTO company_chief_task_reports
            (order_id,artifact_id,chief_employee_id,body,sha256)
            VALUES (?,?,?,'검토 대기',?)''', (order, artifact, chief, '0'*64))
    assert store.read_company_health()['metrics']['pending_chief_reports'] == 1
    with sqlite3.connect(store.path) as con:
        con.execute("UPDATE company_chief_task_reports SET owner_decision='accepted'")
    assert store.read_company_health()['metrics']['pending_chief_reports'] == 0


def test_authentication_and_restart_preserves_history(store):
    store.check_company_health(force=True)
    store.logout()
    for action in (store.read_company_health, store.check_company_health,
                   store.list_company_health_checks):
        with pytest.raises(AuthenticationError):
            action()
    reopened = LocalStore(store.path)
    with pytest.raises(AuthenticationError):
        reopened.list_company_health_checks()
    reopened.login('health_owner', 'stage31-very-secure-password')
    assert reopened.list_company_health_checks()[0]['severity'] == 'ok'
    assert reopened.read_company_health()['metrics']['tasks_total'] == 0
    with sqlite3.connect(store.path) as con:
        assert con.execute('PRAGMA foreign_key_check').fetchall() == []
