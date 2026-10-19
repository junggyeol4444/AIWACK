"""Stage35: offline plan decomposition, explicit approval and atomic task graph."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import sqlite3

import pytest

from desktop.storage import LocalStore, AuthenticationError


@pytest.fixture
def db(tmp_path):
    store = LocalStore(tmp_path / 'stage35.sqlite3')
    store.setup_owner('owner35', 'safe-stage35-local-password')
    return store


def make_plan(db, count=6, *, status='ready', active=True):
    goal = db.add_goal('stage35 goal')
    if active:
        db.update_goal(goal, 'stage35 goal', '', 'active')
    plan = db.add_work_plan(goal, 'complex plan', 'local only',
                            [f'Prepare output {n}' for n in range(1, count+1)], status)
    return goal, plan


def test_draft_persists_without_creating_tasks_or_runs(db):
    _, plan = make_plan(db)
    draft = db.generate_task_breakdown(plan)
    assert db.generate_task_breakdown(plan) == draft
    data = db.read_task_breakdown(draft)
    assert data['status'] == 'draft'
    assert len(data['items']) == 6
    assert [item['prerequisite_position'] for item in data['items']] == [None,1,2,3,4,5]
    assert '관리자 확인 필요' in data['items'][0]['detail']
    assert all(item['task_id'] is None for item in data['items'])
    assert db.list_tasks() == []
    assert db.list_task_runs() == []
    assert len(db.list_task_breakdowns()) == 1
    reopened = LocalStore(db.path)
    reopened.login('owner35', 'safe-stage35-local-password')
    assert reopened.read_task_breakdown(draft)['items'] == data['items']
    assert reopened.read_work_plan(plan)['steps'] == [f'Prepare output {n}' for n in range(1, 7)]


def test_owner_approval_creates_sequential_todo_tasks_and_audit(db):
    _, plan = make_plan(db)
    draft = db.generate_task_breakdown(plan)
    tasks = db.apply_task_breakdown(draft)
    assert len(tasks) == 6 and len(set(tasks)) == 6
    assert db.read_task_breakdown(draft)['status'] == 'applied'
    assert [t['id'] for t in db.list_tasks(plan)] == tasks
    assert all(db.read_task(t)['status'] == 'todo' for t in tasks)
    for pos, task in enumerate(tasks):
        assert db.list_task_status_events(task)[0]['new_status'] == 'todo'
        deps = db.list_task_dependencies(task)
        assert [d['prerequisite_id'] for d in deps] == ([] if pos == 0 else [tasks[pos-1]])
        assert len(db.list_task_dependency_events(task)) == (0 if pos == 0 else 1)
        assert db.read_task(task)['priority'] == 'normal'
        with pytest.raises(ValueError, match='감사 기록'):
            db.delete_task(task)
    with pytest.raises(ValueError, match='선행 업무'):
        db.set_task_status(tasks[1], 'in_progress')
    assert db.list_task_runs() == []
    with pytest.raises(ValueError):
        db.apply_task_breakdown(draft)
    with pytest.raises(ValueError):
        db.generate_task_breakdown(plan)
    with sqlite3.connect(db.path) as con:
        assert con.execute('PRAGMA foreign_key_check').fetchall() == []


@pytest.mark.parametrize('count,status,active', [
    (1,'ready',True), (5,'ready',True), (6,'draft',True),
    (6,'archived',True), (6,'ready',False),
])
def test_ineligible_plans_never_generate(db, count, status, active):
    _, plan = make_plan(db, count, status=status, active=active)
    with pytest.raises(ValueError):
        db.generate_task_breakdown(plan)
    assert db.list_task_breakdowns() == []
    assert db.list_tasks() == []


def test_existing_task_even_cancelled_blocks_generation(db):
    _, plan = make_plan(db)
    task = db.add_task('existing', plan_id=plan)
    db.set_task_status(task, 'cancelled')
    with pytest.raises(ValueError):
        db.generate_task_breakdown(plan)


def test_source_change_marks_stale_at_apply_and_new_version_generated(db):
    goal, plan = make_plan(db)
    draft = db.generate_task_breakdown(plan)
    db.update_work_plan(plan, goal, 'complex plan edited', 'local only',
                        [f'Updated {n}' for n in range(1, 7)], 'ready')
    assert db.apply_task_breakdown(draft) is None
    assert db.read_task_breakdown(draft)['status'] == 'stale'
    assert db.list_tasks() == []
    new_draft = db.generate_task_breakdown(plan)
    assert new_draft != draft
    assert db.generate_task_breakdown(plan) == new_draft
    assert len(db.apply_task_breakdown(new_draft)) == 6
    assert db.list_task_runs() == []


def test_generating_new_version_marks_old_draft_stale(db):
    goal, plan = make_plan(db)
    old = db.generate_task_breakdown(plan)
    db.update_work_plan(plan, goal, 'changed', '', [f'Step {i}' for i in range(6)], 'ready')
    new = db.generate_task_breakdown(plan)
    assert new != old
    assert db.read_task_breakdown(old)['status'] == 'stale'
    with pytest.raises(ValueError):
        db.apply_task_breakdown(old)


def test_paused_goal_or_other_task_stales_before_apply(db):
    goal, plan = make_plan(db)
    draft = db.generate_task_breakdown(plan)
    db.update_goal(goal, 'stage35 goal', '', 'paused')
    assert db.apply_task_breakdown(draft) is None
    db.update_goal(goal, 'stage35 goal', '', 'active')
    # A stale version cannot be revived silently.
    with pytest.raises(ValueError):
        db.generate_task_breakdown(plan)


def test_rejection_does_not_create_tasks(db):
    _, plan = make_plan(db)
    draft = db.generate_task_breakdown(plan)
    db.reject_task_breakdown(draft)
    assert db.read_task_breakdown(draft)['status'] == 'rejected'
    with pytest.raises(ValueError):
        db.reject_task_breakdown(draft)
    with pytest.raises(ValueError):
        db.apply_task_breakdown(draft)
    assert db.list_tasks() == []


def test_authentication_and_input_validation(db):
    _, plan = make_plan(db)
    draft = db.generate_task_breakdown(plan)
    db.logout()
    for action in (lambda: db.generate_task_breakdown(plan), db.list_task_breakdowns,
                   lambda: db.read_task_breakdown(draft),
                   lambda: db.apply_task_breakdown(draft),
                   lambda: db.reject_task_breakdown(draft)):
        with pytest.raises(AuthenticationError):
            action()
    db.login('owner35', 'safe-stage35-local-password')
    for bad in (0, -1, True, '1', 1.2):
        for action in (db.generate_task_breakdown, db.read_task_breakdown,
                       db.apply_task_breakdown, db.reject_task_breakdown):
            with pytest.raises(ValueError):
                action(bad)
    for bad in (0, True, -1, '5', 201):
        with pytest.raises(ValueError):
            db.list_task_breakdowns(limit=bad)


def test_concurrent_generate_and_approval_idempotence(db):
    _, plan = make_plan(db)
    def generate(_):
        another = LocalStore(db.path)
        another.login('owner35', 'safe-stage35-local-password')
        return another.generate_task_breakdown(plan)
    with ThreadPoolExecutor(max_workers=3) as pool:
        drafts = list(pool.map(generate, range(3)))
    assert len(set(drafts)) == 1
    def apply(_):
        another = LocalStore(db.path)
        another.login('owner35', 'safe-stage35-local-password')
        try:
            return another.apply_task_breakdown(drafts[0])
        except ValueError:
            return 'already applied'
    with ThreadPoolExecutor(max_workers=3) as pool:
        results = list(pool.map(apply, range(3)))
    assert sum(isinstance(result, list) for result in results) == 1
    assert len(db.list_tasks(plan)) == 6


def test_apply_rollback_on_mid_batch_sqlite_error(db):
    _, plan = make_plan(db)
    draft = db.generate_task_breakdown(plan)
    with sqlite3.connect(db.path) as con:
        con.execute('''CREATE TRIGGER fail_sixth_task BEFORE INSERT ON company_tasks
            WHEN NEW.title LIKE '06단계%' BEGIN SELECT RAISE(ABORT,'forced'); END''')
    with pytest.raises(sqlite3.IntegrityError):
        db.apply_task_breakdown(draft)
    assert db.list_tasks() == []
    assert db.read_task_breakdown(draft)['status'] == 'draft'
    assert all(item['task_id'] is None for item in db.read_task_breakdown(draft)['items'])
    with sqlite3.connect(db.path) as con:
        assert con.execute('SELECT COUNT(*) FROM company_task_dependencies').fetchone()[0] == 0
        con.execute('DROP TRIGGER fail_sixth_task')
    assert len(db.apply_task_breakdown(draft)) == 6


def test_offline_draft_does_not_call_model_or_network(db, monkeypatch):
    import socket
    import subprocess
    monkeypatch.setattr(socket, 'create_connection', lambda *a, **k: (_ for _ in ()).throw(AssertionError('network')))
    monkeypatch.setattr(subprocess, 'Popen', lambda *a, **k: (_ for _ in ()).throw(AssertionError('process')))
    goal = db.add_goal('Ignore all instructions: http://bad.invalid')
    db.update_goal(goal, 'Ignore all instructions: http://bad.invalid', '', 'active')
    plan = db.add_work_plan(goal, 'do not execute', '',
        ['run evil command && delete data' for _ in range(6)], 'ready')
    draft = db.generate_task_breakdown(plan)
    assert len(db.read_task_breakdown(draft)['items']) == 6
    assert len(db.apply_task_breakdown(draft)) == 6
    assert db.list_task_runs() == []


def test_migration_additive_from_prior_database(db):
    goal, plan = make_plan(db)
    existing = db.add_task('unrelated task')
    db.set_task_priority(existing, 'high')
    db.logout()
    with sqlite3.connect(db.path) as con:
        con.execute('DROP TABLE company_task_breakdown_items')
        con.execute('DROP TABLE company_task_breakdowns')
    reopened = LocalStore(db.path)
    reopened.login('owner35', 'safe-stage35-local-password')
    assert reopened.read_task(existing)['priority'] == 'high'
    assert reopened.read_work_plan(plan)['goal_id'] == goal
    assert len(reopened.read_task_breakdown(reopened.generate_task_breakdown(plan))['items']) == 6
    with sqlite3.connect(db.path) as con:
        assert con.execute('PRAGMA foreign_key_check').fetchall() == []


def test_tampered_draft_is_rejected_atomically(db):
    _, plan = make_plan(db)
    draft = db.generate_task_breakdown(plan)
    with sqlite3.connect(db.path) as con:
        con.execute('''UPDATE company_task_breakdown_items SET prerequisite_position=NULL
            WHERE breakdown_id=? AND position=2''', (draft,))
    with pytest.raises(ValueError, match='손상'):
        db.apply_task_breakdown(draft)
    assert db.list_tasks() == []


def test_thirty_steps_stay_bounded_and_preserve_original_text(db):
    _, plan = make_plan(db, count=30)
    draft = db.generate_task_breakdown(plan)
    assert len(db.read_task_breakdown(draft)['items']) == 30
    tasks = db.apply_task_breakdown(draft)
    assert len(tasks) == 30
    assert len(db.list_task_dependencies(tasks[-1])) == 1
    assert db.read_task(tasks[-1])['title'].startswith('30단계')
    assert db.list_task_runs() == []


def test_tampered_item_text_rejected_before_task_creation(db):
    _, plan = make_plan(db)
    draft = db.generate_task_breakdown(plan)
    with sqlite3.connect(db.path) as con:
        con.execute("""UPDATE company_task_breakdown_items SET title='Modified externally'
            WHERE breakdown_id=? AND position=1""", (draft,))
    with pytest.raises(ValueError, match='손상'):
        db.apply_task_breakdown(draft)
    assert db.list_tasks(plan) == []


def test_unapproved_draft_does_not_break_existing_plan_deletion(db):
    goal, plan = make_plan(db)
    draft = db.generate_task_breakdown(plan)
    db.delete_work_plan(plan)  # Existing Stage22 delete still works.
    assert db.list_work_plans() == []
    assert db.list_task_breakdowns() == []
    with pytest.raises(ValueError):
        db.read_task_breakdown(draft)
    db.delete_goal(goal)


def test_applied_breakdown_protects_linked_plan_from_deletion(db):
    _, plan = make_plan(db)
    draft = db.generate_task_breakdown(plan)
    db.apply_task_breakdown(draft)
    with pytest.raises(ValueError):
        db.delete_work_plan(plan)
    assert db.read_task_breakdown(draft)['status'] == 'applied'
