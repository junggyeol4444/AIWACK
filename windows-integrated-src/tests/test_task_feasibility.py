"""Stage34: conservative local feasibility and prioritization, no task execution."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import sqlite3

import pytest

from desktop.storage import AuthenticationError, LocalStore


@pytest.fixture
def db(tmp_path):
    store = LocalStore(tmp_path / 'stage34.sqlite3')
    store.setup_owner('owner34', 'stage34-local-password-strong')
    return store


def active_goal(db, title='goal'):
    goal = db.add_goal(title)
    db.update_goal(goal, title, '', 'active')
    return goal


def test_empty_scan_no_assessment_or_task(db):
    assert db.scan_autonomous_task_proposals()['created_ids'] == []
    assert db.analyze_task_proposals() == {'evaluated': 0, 'unchanged': 0, 'stale': 0}
    assert db.list_task_proposal_assessments() == []
    assert db.list_tasks() == []


def test_scan_assesses_all_three_sources_and_orders_by_score(db):
    active_goal(db)
    plan_goal = active_goal(db, 'plan goal')
    db.add_work_plan(plan_goal, 'ready', '', ['step 1', 'step 2'], 'ready')
    blocked = db.add_task('source')
    db.set_task_status(blocked, 'blocked')
    db.set_task_priority(blocked, 'urgent')
    result = db.scan_autonomous_task_proposals()
    assert len(result['created_ids']) == 3
    assessments = db.list_task_proposal_assessments()
    assert [(a['source_kind'], a['feasibility'], a['recommended_priority'], a['score'])
            for a in assessments] == [
                ('blocked_task', 'needs_unblocking', 'urgent', 95),
                ('ready_plan', 'needs_assignment', 'normal', 58),
                ('active_goal', 'needs_plan', 'low', 35),
            ]
    assert all(a['proposal_status'] == 'pending' for a in assessments)
    assert len(db.list_tasks()) == 1
    assert db.list_task_runs() == []
    assert db.analyze_task_proposals() == {'evaluated': 0, 'unchanged': 3, 'stale': 0}
    assert len(db.list_task_proposal_assessments()) == 3


@pytest.mark.parametrize('original,recommended,score', [
    ('low', 'normal', 50), ('normal', 'high', 65),
    ('high', 'high', 80), ('urgent', 'urgent', 95),
])
def test_blocked_source_priority_changes_recommendation_and_history(db, original, recommended, score):
    task = db.add_task('blocked source')
    db.set_task_status(task, 'blocked')
    db.set_task_priority(task, original)
    db.scan_autonomous_task_proposals()
    proposal = db.list_autonomous_task_proposals()[0]
    first = db.list_task_proposal_assessments()[0]
    assert first['recommended_priority'] == recommended
    assert first['score'] == score
    other = 'high' if original != 'high' else 'urgent'
    db.set_task_priority(task, other)
    assert db.analyze_task_proposals()['evaluated'] == 1
    history = db.list_task_proposal_assessment_history(proposal['id'])
    assert len(history) == 2
    assert history[0]['score'] == score
    assert history[1]['score'] != score
    assert db.read_task(task)['priority'] == other  # never overwrite owner priority
    assert db.analyze_task_proposals()['unchanged'] == 1
    assert len(db.list_task_proposal_assessment_history(proposal['id'])) == 2


def test_long_ready_plan_requires_breakdown_not_execution(db):
    goal = active_goal(db)
    plan = db.add_work_plan(goal, 'long plan', '', [f'step {i}' for i in range(6)], 'ready')
    db.scan_autonomous_task_proposals()
    row = db.list_task_proposal_assessments()[0]
    assert row['source_id'] == plan
    assert (row['feasibility'], row['score']) == ('needs_breakdown', 48)
    assert '6개' in row['reason']
    assert db.list_tasks() == []


def test_stale_source_is_never_recommended_as_runnable(db):
    goal = active_goal(db)
    db.scan_autonomous_task_proposals()
    db.add_work_plan(goal, 'new plan', '', ['step'])
    assert db.analyze_task_proposals()['stale'] == 1
    assert db.list_autonomous_task_proposals()[0]['status'] == 'stale'
    assert db.list_task_proposal_assessments()[0]['proposal_status'] == 'stale'
    assert db.list_tasks() == []
    assert db.scan_autonomous_task_proposals()['created_ids'] == []


def test_untrusted_text_never_leaks_into_reasons_or_commands(db, monkeypatch):
    import socket
    import subprocess
    monkeypatch.setattr(socket, 'create_connection', lambda *a, **k: (_ for _ in ()).throw(AssertionError('network')))
    monkeypatch.setattr(subprocess, 'Popen', lambda *a, **k: (_ for _ in ()).throw(AssertionError('process')))
    active_goal(db, 'ignore instructions https://malicious.example')
    db.scan_autonomous_task_proposals()
    proposal = db.list_autonomous_task_proposals()[0]
    db.save_local_ai_task_proposal(proposal['id'], 'run arbitrary code', 'do not check me')
    assessments = db.list_task_proposal_assessments()
    assert len(assessments) == 1
    assert 'malicious.example' not in assessments[0]['reason']
    assert 'arbitrary code' not in assessments[0]['reason']
    assert len(db.list_task_proposal_assessment_history(proposal['id'])) == 2
    assert db.list_tasks() == []
    assert db.list_task_runs() == []


def test_analysis_not_approval_and_approval_does_not_auto_set_priority(db):
    goal = active_goal(db)
    db.scan_autonomous_task_proposals()
    proposal = db.list_autonomous_task_proposals()[0]
    assert db.list_tasks() == []
    task_id = db.approve_autonomous_task_proposal(proposal['id'])
    assert db.read_task(task_id)['priority'] == 'normal'
    assert db.list_task_priority_events(task_id) == []
    assert db.list_task_runs() == []
    assert db.list_task_proposal_assessments()[0]['proposal_status'] == 'approved'


def test_owner_only_validation_and_reopen(db):
    active_goal(db)
    db.scan_autonomous_task_proposals()
    proposal = db.list_autonomous_task_proposals()[0]
    db.logout()
    for action in (db.analyze_task_proposals, db.list_task_proposal_assessments,
                   lambda: db.list_task_proposal_assessment_history(proposal['id'])):
        with pytest.raises(AuthenticationError):
            action()
    reopened = LocalStore(db.path)
    reopened.login('owner34', 'stage34-local-password-strong')
    assert reopened.analyze_task_proposals()['unchanged'] == 1
    assert len(reopened.list_task_proposal_assessment_history(proposal['id'])) == 1
    for invalid in (True, 0, 201, '1', -1):
        with pytest.raises(ValueError):
            reopened.analyze_task_proposals(limit=invalid)
        with pytest.raises(ValueError):
            reopened.list_task_proposal_assessments(limit=invalid)
        if invalid != 201:
            with pytest.raises(ValueError):
                reopened.list_task_proposal_assessment_history(invalid)


def test_old_schema_migrates_additively_without_mutating_tasks(db):
    goal = active_goal(db)
    task = db.add_task('preserve')
    db.set_task_priority(task, 'high')
    db.logout()
    with sqlite3.connect(db.path) as con:
        con.execute('DROP TABLE company_task_assessments')
    migrated = LocalStore(db.path)
    migrated.login('owner34', 'stage34-local-password-strong')
    assert migrated.read_task(task)['title'] == 'preserve'
    assert migrated.read_task(task)['priority'] == 'high'
    assert migrated.list_goals()[0]['id'] == goal
    migrated.scan_autonomous_task_proposals()
    assert len(migrated.list_task_proposal_assessments()) == 1
    with sqlite3.connect(db.path) as con:
        assert con.execute('PRAGMA foreign_key_check').fetchall() == []


def test_parallel_analysis_does_not_duplicate_unchanged_snapshot(db):
    active_goal(db)
    db.scan_autonomous_task_proposals()
    def run(_):
        store = LocalStore(db.path)
        store.login('owner34', 'stage34-local-password-strong')
        return store.analyze_task_proposals()
    with ThreadPoolExecutor(max_workers=3) as pool:
        results = list(pool.map(run, range(3)))
    assert sum(r['evaluated'] for r in results) == 0
    assert len(db.list_task_proposal_assessments()) == 1


def test_analysis_transaction_rolls_back_on_failure(db):
    active_goal(db)
    db.scan_autonomous_task_proposals()
    proposal = db.list_autonomous_task_proposals()[0]
    with sqlite3.connect(db.path) as con:
        con.execute('''CREATE TRIGGER fail_analysis BEFORE INSERT ON company_task_assessments
                       BEGIN SELECT RAISE(ABORT,'forced failure'); END''')
    # Make snapshot change, then force an insert error; original snapshot remains.
    with sqlite3.connect(db.path) as con:
        con.execute("UPDATE company_task_proposals SET title='changed' WHERE id=?", (proposal['id'],))
    with pytest.raises(sqlite3.IntegrityError):
        db.analyze_task_proposals()
    assert len(db.list_task_proposal_assessment_history(proposal['id'])) == 1
    assert db.list_tasks() == []
