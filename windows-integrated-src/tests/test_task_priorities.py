"""Stage 25 priority ordering, migration, auth, persistence and transaction safety."""
import sqlite3

import pytest

from desktop.storage import AuthenticationError, LocalStore

USER = "priority_owner"
PASSWORD = "long-local-passphrase-2026"


def ready(tmp_path):
    db = LocalStore(tmp_path / "aiwack.sqlite3")
    db.setup_owner(USER, PASSWORD)
    return db


def test_priority_default_ordering_and_persistence(tmp_path):
    db = ready(tmp_path)
    a, b, c, d, e = [db.add_task(f"업무 {i}") for i in range(5)]
    assert [t["id"] for t in db.list_tasks()] == [a, b, c, d, e]
    assert all(t["priority"] == "normal" for t in db.list_tasks())
    assert db.set_task_priority(d, "urgent") is True
    assert db.set_task_priority(b, "high") is True
    assert db.set_task_priority(e, "low") is True
    assert [t["id"] for t in db.list_tasks()] == [d, b, a, c, e]
    assert db.read_task(d)["priority"] == "urgent"
    db.logout()
    new = LocalStore(db.path)
    with pytest.raises(AuthenticationError):
        new.list_tasks()
    new.login(USER, PASSWORD)
    assert [t["id"] for t in new.list_tasks()] == [d, b, a, c, e]
    assert new.read_task(e)["priority"] == "low"


def test_idempotent_changes_and_immutable_history(tmp_path):
    db = ready(tmp_path)
    task = db.add_task("수동 업무")
    assert not db.set_task_priority(task, "normal")
    assert db.list_task_priority_events(task) == []
    assert db.set_task_priority(task, "high")
    assert not db.set_task_priority(task, "high")
    assert db.set_task_priority(task, "urgent")
    assert db.set_task_priority(task, "normal")
    assert [(e["old_priority"], e["new_priority"]) for e in db.list_task_priority_events(task)] == [
        ("normal", "high"), ("high", "urgent"), ("urgent", "normal")
    ]
    assert db.read_task(task)["priority"] == "normal"
    assert db.list_task_status_events(task)[0]["new_status"] == "todo"


@pytest.mark.parametrize("priority", ["", "URGENT", "critical", "  high", None, 1, True, [], {}])
def test_invalid_priority_rejected_without_writes(tmp_path, priority):
    db = ready(tmp_path)
    task = db.add_task("중요도 검사")
    with pytest.raises(ValueError):
        db.set_task_priority(task, priority)
    assert db.read_task(task)["priority"] == "normal"
    assert db.list_task_priority_events(task) == []


def test_closed_tasks_sort_after_open_without_changing_priority(tmp_path):
    db = ready(tmp_path)
    done = db.add_task("완료")
    open_task = db.add_task("진행")
    cancelled = db.add_task("취소")
    db.set_task_priority(done, "urgent")
    db.set_task_priority(cancelled, "high")
    db.set_task_priority(open_task, "low")
    db.set_task_status(done, "in_progress")
    db.set_task_status(done, "done")
    db.set_task_status(cancelled, "cancelled")
    assert [t["id"] for t in db.list_tasks()] == [open_task, done, cancelled]
    assert db.read_task(done)["priority"] == "urgent"
    db.set_task_status(done, "todo")
    assert [t["id"] for t in db.list_tasks()] == [done, open_task, cancelled]


def test_priority_edit_does_not_change_assignee_status_or_plan(tmp_path):
    db = ready(tmp_path)
    goal = db.add_goal("목표")
    plan = db.add_work_plan(goal, "계획", "", ["검토"], "draft")
    task = db.add_task("작업", plan_id=plan)
    db.set_task_priority(task, "urgent")
    assert db.read_task(task)["plan_id"] == plan
    assert db.read_task(task)["status"] == "todo"
    assert db.read_task_routing(task)["employee_id"] is None
    assert len(db.list_task_status_events(task)) == 1
    assert len(db.list_task_priority_events(task)) == 1
    assert db.list_tasks(plan)[0]["priority"] == "urgent"


def test_deleted_task_cascades_priority_and_history(tmp_path):
    db = ready(tmp_path)
    task = db.add_task("삭제할 업무")
    db.set_task_priority(task, "high")
    db.delete_task(task)
    with sqlite3.connect(db.path) as con:
        assert con.execute("SELECT COUNT(*) FROM company_task_priorities").fetchone()[0] == 0
        assert con.execute("SELECT COUNT(*) FROM company_task_priority_events").fetchone()[0] == 0


def test_unauthorized_and_missing_task(tmp_path):
    db = ready(tmp_path)
    task = db.add_task("권한 검사")
    db.logout()
    for fn in (lambda: db.set_task_priority(task, "urgent"),
               lambda: db.list_task_priority_events(task)):
        with pytest.raises(AuthenticationError):
            fn()
    db.login(USER, PASSWORD)
    for fn in (lambda: db.set_task_priority(999999, "urgent"),
               lambda: db.list_task_priority_events(999999),
               lambda: db.set_task_priority(True, "high"),
               lambda: db.set_task_priority("1", "high")):
        with pytest.raises(ValueError):
            fn()
    assert db.list_task_priority_events(task) == []


def test_history_failure_rolls_back_priority_change(tmp_path):
    db = ready(tmp_path)
    task = db.add_task("원자성")
    with sqlite3.connect(db.path) as con:
        con.execute("""CREATE TRIGGER reject_priority BEFORE INSERT ON company_task_priority_events
            BEGIN SELECT RAISE(ABORT, 'reject audit'); END""")
    with pytest.raises(sqlite3.IntegrityError):
        db.set_task_priority(task, "urgent")
    assert db.read_task(task)["priority"] == "normal"
    assert db.list_task_priority_events(task) == []


def test_upgrade_existing_tasks_without_rewriting(tmp_path):
    path = tmp_path / "old.sqlite3"
    # Simulate a minimal pre-stage-25 DB: task row already exists, no priority tables.
    with sqlite3.connect(path) as con:
        con.execute("""CREATE TABLE company_tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT, plan_id INTEGER, title TEXT NOT NULL,
            description TEXT NOT NULL DEFAULT '', status TEXT NOT NULL DEFAULT 'todo',
            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP, completed_at DATETIME)""")
        con.execute("INSERT INTO company_tasks(id,title) VALUES(42,'이전 단계 업무')")
    db = LocalStore(path)
    db.setup_owner(USER, PASSWORD)
    assert db.read_task(42)["priority"] == "normal"
    assert db.read_task(42)["title"] == "이전 단계 업무"
    db.set_task_priority(42, "high")
    assert db.read_task(42)["priority"] == "high"
    assert db.read_task(42)["title"] == "이전 단계 업무"
