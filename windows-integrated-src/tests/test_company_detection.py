"""Stage32: local deterministic signals, security, migration, and history."""
from __future__ import annotations

import json
import sqlite3

import pytest

from desktop.storage import AuthenticationError, LocalStore


@pytest.fixture
def store(tmp_path):
    db = LocalStore(tmp_path / 'signals.sqlite3')
    db.setup_owner('signals_owner', 'stage32-local-secure-pass')
    return db


def signal(report, code):
    return next((s for s in report['signals'] if s['code'] == code), None)


def test_empty_is_clean_and_live_read_creates_no_history(store):
    report = store.read_company_signals()
    assert report['severity'] == 'ok'
    assert report['signals'] == []
    assert report['problem_types'] == report['opportunity_types'] == 0
    assert store.list_company_detection_checks() == []


def test_unassigned_blocked_and_urgent_blocked_are_distinct(store):
    task = store.add_task('secret task title never persist')
    store.set_task_priority(task, 'urgent')
    store.set_task_status(task, 'blocked')
    report = store.check_company_signals()
    assert report['severity'] == 'critical'
    assert signal(report, 'urgent_blocked')['count'] == 1
    assert signal(report, 'blocked_tasks')['count'] == 1
    assert signal(report, 'unassigned_tasks')['count'] == 1
    assert report['opportunity_types'] == 0
    with sqlite3.connect(store.path) as con:
        saved = con.execute('SELECT signals_json FROM company_detection_checks').fetchone()[0]
    assert 'secret task' not in saved
    assert 'sample_ids' not in saved
    assert json.loads(saved)[0]['code'] == 'urgent_blocked'
    assert store.read_task(task)['status'] == 'blocked'


def test_active_goal_without_nonarchived_plan_is_only_a_candidate(store):
    goal = store.add_goal('private market concept')
    assert signal(store.read_company_signals(), 'unplanned_active_goals') is None
    store.update_goal(goal, 'private market concept', '', 'active')
    report = store.read_company_signals()
    s = signal(report, 'unplanned_active_goals')
    assert s['kind'] == 'opportunity' and s['severity'] == 'candidate'
    assert s['sample_ids'] == [goal]
    assert report['severity'] == 'ok'  # candidates are not faults
    assert '시장 수요' in report['disclaimer']
    plan = store.add_work_plan(goal, 'private plan', '', ['Step one'], 'draft')
    assert signal(store.read_company_signals(), 'unplanned_active_goals') is None
    store.update_work_plan(plan, goal, 'private plan', '', ['Step one'], 'archived')
    assert signal(store.read_company_signals(), 'unplanned_active_goals')['count'] == 1
    store.update_goal(goal, 'private market concept', '', 'paused')
    assert signal(store.read_company_signals(), 'unplanned_active_goals') is None


def test_ready_plan_without_active_tasks_is_candidate(store):
    goal = store.add_goal('sensitive business goal')
    store.update_goal(goal, 'sensitive business goal', '', 'active')
    plan = store.add_work_plan(goal, 'internal plan', '', ['step'], 'ready')
    report = store.read_company_signals()
    assert signal(report, 'unplanned_active_goals') is None
    assert signal(report, 'ready_plans_without_tasks')['sample_ids'] == [plan]
    task = store.add_task('plan task', plan_id=plan)
    assert signal(store.read_company_signals(), 'ready_plans_without_tasks') is None
    store.set_task_status(task, 'cancelled')
    assert signal(store.read_company_signals(), 'ready_plans_without_tasks')['count'] == 1
    store.update_work_plan(plan, goal, 'internal plan', '', ['step'], 'draft')
    assert signal(store.read_company_signals(), 'ready_plans_without_tasks') is None


def test_history_dedup_force_and_one_hour_refresh(store):
    first = store.check_company_signals()
    assert first['recorded']
    same = store.check_company_signals()
    assert not same['recorded'] and same['check_id'] == first['check_id']
    goal = store.add_goal('sensitive internal goal')
    store.update_goal(goal, 'sensitive internal goal', '', 'active')
    changed = store.check_company_signals()
    assert changed['recorded'] and changed['check_id'] != first['check_id']
    repeated = store.check_company_signals()
    assert not repeated['recorded']
    forced = store.check_company_signals(force=True)
    assert forced['recorded']
    assert len(store.list_company_detection_checks()) == 3
    with sqlite3.connect(store.path) as con:
        con.execute("UPDATE company_detection_checks SET checked_at=datetime('now','-2 hours') WHERE id=?",
                    (forced['check_id'],))
    hourly = store.check_company_signals()
    assert hourly['recorded']
    assert len(store.list_company_detection_checks(limit=2)) == 2
    assert store.list_company_detection_checks()[0]['signals'][0]['code'] == 'unplanned_active_goals'


def test_history_has_only_codes_counts_and_no_ids_or_owner_text(store):
    for i in range(23):
        goal = store.add_goal(f'private-name-{i}')
        store.update_goal(goal, f'private-name-{i}', 'private-description', 'active')
    report = store.check_company_signals()
    s = signal(report, 'unplanned_active_goals')
    assert s['count'] == 23 and len(s['sample_ids']) == 20
    assert s['sample_ids'] == list(range(1, 21))
    with sqlite3.connect(store.path) as con:
        raw = con.execute('SELECT signals_json FROM company_detection_checks').fetchone()[0]
    assert 'private' not in raw and 'sample_ids' not in raw
    assert '"count":23' in raw
    assert len(store.list_goals()) == 23


def test_authentication_validation_and_restart(store):
    store.check_company_signals(force=True)
    for value in (None, 1, 'yes'):
        with pytest.raises(ValueError):
            store.check_company_signals(force=value)
    for value in (True, 0, -1, 101, '30'):
        with pytest.raises(ValueError):
            store.list_company_detection_checks(limit=value)
    store.logout()
    for fn in (store.read_company_signals, store.check_company_signals,
               store.list_company_detection_checks):
        with pytest.raises(AuthenticationError):
            fn()
    reopened = LocalStore(store.path)
    with pytest.raises(AuthenticationError):
        reopened.read_company_signals()
    reopened.login('signals_owner', 'stage32-local-secure-pass')
    assert len(reopened.list_company_detection_checks()) == 1
    assert reopened.read_company_signals()['severity'] == 'ok'


def test_non_destructive_migration_from_pre32_schema(store):
    goal = store.add_goal('keep old goal')
    task = store.add_task('keep old task')
    store.logout()
    with sqlite3.connect(store.path) as con:
        con.execute('DROP TABLE company_detection_checks')
    migrated = LocalStore(store.path)
    migrated.login('signals_owner', 'stage32-local-secure-pass')
    assert migrated.read_task(task)['title'] == 'keep old task'
    assert migrated.list_goals()[0]['id'] == goal
    assert migrated.check_company_signals()['recorded']
    with sqlite3.connect(store.path) as con:
        assert con.execute('PRAGMA foreign_key_check').fetchall() == []


def test_read_and_detection_do_not_create_tasks_or_execute_models(store):
    goal = store.add_goal('not an instruction')
    store.update_goal(goal, 'not an instruction', '', 'active')
    tasks_before = store.list_tasks()
    runs_before = store.list_task_runs()
    for _ in range(3):
        store.read_company_signals()
        store.check_company_signals()
    assert store.list_tasks() == tasks_before
    assert store.list_task_runs() == runs_before
    assert store.list_company_health_checks() == []
