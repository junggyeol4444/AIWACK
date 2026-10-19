"""Stage 26: local prerequisite DAG, status gating, audit, owner access and upgrade."""
import sqlite3
import pytest

from desktop.storage import AuthenticationError, LocalStore


def ready(tmp_path):
    store = LocalStore(tmp_path / 'company.sqlite3')
    store.setup_owner('dependency_owner', 'local-password-long-enough')
    return store


def test_chain_readiness_and_status_guards(tmp_path):
    store = ready(tmp_path)
    a, b, c = (store.add_task(x) for x in ('기획', '제작', '검수'))
    assert store.add_task_dependency(b, a)
    assert store.add_task_dependency(c, b)
    assert store.task_dependency_readiness(b) == {'ready': False, 'pending_ids': [a], 'total': 1}
    with pytest.raises(ValueError, match='선행 업무'):
        store.set_task_status(b, 'in_progress')
    assert store.read_task(b)['status'] == 'todo'
    assert len(store.list_task_status_events(b)) == 1
    store.set_task_status(a, 'in_progress')
    store.set_task_status(a, 'done')
    assert store.task_dependency_readiness(b)['ready']
    store.set_task_status(b, 'in_progress')
    with pytest.raises(ValueError, match='후속 업무'):
        store.set_task_status(a, 'todo')
    store.set_task_status(b, 'done')
    assert store.task_dependency_readiness(c)['ready']
    store.set_task_status(c, 'in_progress')
    store.set_task_status(c, 'done')
    with pytest.raises(ValueError, match='후속 업무'):
        store.set_task_status(b, 'todo')
    assert store.read_task(a)['status'] == 'done'
    assert store.read_task(c)['status'] == 'done'


def test_multi_prerequisite_gate_and_unblock(tmp_path):
    store = ready(tmp_path)
    first, second, child = (store.add_task(x) for x in ('A', 'B', 'C'))
    assert store.add_task_dependency(child, first)
    assert store.add_task_dependency(child, second)
    store.set_task_status(first, 'in_progress')
    store.set_task_status(first, 'done')
    assert store.task_dependency_readiness(child)['pending_ids'] == [second]
    store.set_task_status(child, 'blocked')
    with pytest.raises(ValueError):
        store.set_task_status(child, 'in_progress')
    store.set_task_status(second, 'in_progress')
    store.set_task_status(second, 'done')
    store.set_task_status(child, 'in_progress')
    assert store.read_task(child)['status'] == 'in_progress'


def test_self_cycle_transitive_and_duplicate(tmp_path):
    store = ready(tmp_path)
    a, b, c, d = (store.add_task(x) for x in 'ABCD')
    with pytest.raises(ValueError, match='자기 자신'):
        store.add_task_dependency(a, a)
    assert store.add_task_dependency(b, a)
    assert store.add_task_dependency(c, b)
    assert store.add_task_dependency(d, c)
    with pytest.raises(ValueError, match='순환'):
        store.add_task_dependency(a, d)
    with pytest.raises(ValueError, match='순환'):
        store.add_task_dependency(a, b)
    assert not store.add_task_dependency(b, a)
    assert len(store.list_task_dependency_events(b)) == 1
    assert store.list_task_dependencies(a) == []


def test_delete_guard_unlink_and_audit(tmp_path):
    store = ready(tmp_path)
    parent, child = store.add_task('선행'), store.add_task('후속')
    store.add_task_dependency(child, parent)
    with pytest.raises(ValueError, match='후속 업무'):
        store.delete_task(parent)
    assert store.remove_task_dependency(child, parent)
    assert not store.remove_task_dependency(child, parent)
    assert [(x['prerequisite_id'], x['action']) for x in store.list_task_dependency_events(child)] == [
        (parent, 'added'), (parent, 'removed')]
    store.delete_task(parent)
    assert len(store.list_task_dependency_events(child)) == 2
    store.delete_task(child)
    with sqlite3.connect(store.path) as con:
        assert con.execute('SELECT COUNT(*) FROM company_task_dependencies').fetchone()[0] == 0
        assert con.execute('SELECT COUNT(*) FROM company_task_dependency_events').fetchone()[0] == 0


def test_active_task_cannot_gain_prerequisite_and_unlink_is_allowed(tmp_path):
    store = ready(tmp_path)
    parent, child = store.add_task('선행'), store.add_task('후속')
    store.set_task_status(child, 'in_progress')
    with pytest.raises(ValueError, match='진행'):
        store.add_task_dependency(child, parent)
    store.set_task_status(child, 'blocked')
    store.add_task_dependency(child, parent)
    with pytest.raises(ValueError):
        store.set_task_status(child, 'in_progress')
    assert store.remove_task_dependency(child, parent)
    store.set_task_status(child, 'in_progress')
    assert store.task_dependency_readiness(child)['ready']


def test_auth_validation_and_missing(tmp_path):
    store = ready(tmp_path)
    a, b = store.add_task('A'), store.add_task('B')
    for bad in (None, True, False, '1', 0, -1, 1.0):
        with pytest.raises(ValueError):
            store.add_task_dependency(a, bad)
    for operation in (lambda: store.add_task_dependency(a, 9999),
                      lambda: store.remove_task_dependency(a, 9999),
                      lambda: store.list_task_dependencies(9999),
                      lambda: store.list_task_dependency_events(9999),
                      lambda: store.task_dependency_readiness(9999)):
        with pytest.raises(ValueError):
            operation()
    store.logout()
    for operation in (lambda: store.add_task_dependency(b, a),
                      lambda: store.remove_task_dependency(b, a),
                      lambda: store.list_task_dependencies(b),
                      lambda: store.list_task_dependency_events(b),
                      lambda: store.task_dependency_readiness(b)):
        with pytest.raises(AuthenticationError):
            operation()
    store.login('dependency_owner', 'local-password-long-enough')
    assert store.list_task_dependencies(b) == []


def test_audit_failure_rolls_back_edge_and_removal(tmp_path):
    store = ready(tmp_path)
    a, b = store.add_task('A'), store.add_task('B')
    with sqlite3.connect(store.path) as con:
        con.execute("""CREATE TRIGGER fail_add BEFORE INSERT ON company_task_dependency_events
            WHEN NEW.action='added' BEGIN SELECT RAISE(ABORT,'audit failed'); END""")
    with pytest.raises(sqlite3.IntegrityError):
        store.add_task_dependency(b, a)
    assert store.list_task_dependencies(b) == []
    with sqlite3.connect(store.path) as con:
        con.execute('DROP TRIGGER fail_add')
    store.add_task_dependency(b, a)
    with sqlite3.connect(store.path) as con:
        con.execute("""CREATE TRIGGER fail_remove BEFORE INSERT ON company_task_dependency_events
            WHEN NEW.action='removed' BEGIN SELECT RAISE(ABORT,'audit failed'); END""")
    with pytest.raises(sqlite3.IntegrityError):
        store.remove_task_dependency(b, a)
    assert len(store.list_task_dependencies(b)) == 1
    assert [r['action'] for r in store.list_task_dependency_events(b)] == ['added']


def test_existing_stage25_database_migrates_without_rewrite(tmp_path):
    path = tmp_path / 'legacy.sqlite3'
    with sqlite3.connect(path) as con:
        con.execute('''CREATE TABLE company_tasks (id INTEGER PRIMARY KEY AUTOINCREMENT,
            plan_id INTEGER, title TEXT NOT NULL, description TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'todo', created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP, completed_at DATETIME)''')
        con.execute("INSERT INTO company_tasks(id,title) VALUES(42,'예전 업무')")
    store = LocalStore(path)
    store.setup_owner('dependency_owner', 'local-password-long-enough')
    assert store.read_task(42)['title'] == '예전 업무'
    assert store.task_dependency_readiness(42) == {'ready': True, 'pending_ids': [], 'total': 0}
    new = store.add_task('신규 업무')
    store.add_task_dependency(new, 42)
    store.logout()
    store = LocalStore(path)
    store.login('dependency_owner', 'local-password-long-enough')
    assert store.list_task_dependencies(new)[0]['prerequisite_id'] == 42
    assert store.read_task(42)['title'] == '예전 업무'


def test_dependency_does_not_modify_priority_plan_assignment(tmp_path):
    store = ready(tmp_path)
    goal = store.add_goal('목표')
    plan = store.add_work_plan(goal, '계획', '', ['검토'], 'draft')
    a = store.add_task('A', plan_id=plan)
    b = store.add_task('B', plan_id=plan)
    store.set_task_priority(b, 'urgent')
    store.add_task_dependency(b, a)
    assert store.read_task(b)['plan_id'] == plan
    assert store.read_task(b)['priority'] == 'urgent'
    assert store.read_task_routing(b)['employee_id'] is None
    assert len(store.list_task_status_events(b)) == 1
