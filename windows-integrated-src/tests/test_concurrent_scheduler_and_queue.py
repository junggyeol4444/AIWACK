"""Two independent Windows owner sessions must not double-dispatch scheduled tasks."""
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
import pytest

from desktop.storage import LocalStore


def two_owners(tmp_path):
    db = tmp_path / 'shared-company.sqlite3'
    first = LocalStore(db)
    first.setup_owner('two_window_owner', 'two-window-check-password-2026')
    second = LocalStore(db)
    second.login('two_window_owner', 'two-window-check-password-2026')
    return first, second


def parallel(owner_a, owner_b, function):
    barrier = Barrier(2)
    def worker(store):
        barrier.wait(timeout=10)
        return function(store)
    with ThreadPoolExecutor(max_workers=2) as pool:
        a = pool.submit(worker, owner_a)
        b = pool.submit(worker, owner_b)
        return a.result(timeout=20), b.result(timeout=20)


def test_two_windows_create_one_recurring_occurrence_without_backlog(tmp_path):
    owner_a, owner_b = two_owners(tmp_path)
    sid = owner_a.add_recurring_schedule('24h offline scheduled draft', interval_minutes=5)
    owner_a.set_recurring_schedule_enabled(sid, True)
    due = owner_a.list_recurring_schedules()[0]['next_due']
    left, right = parallel(owner_a, owner_b, lambda store: store.run_due_recurring_schedules(now=due))
    assert len(left) + len(right) == 1
    task_id = (left + right)[0]
    assert len(owner_a.list_recurring_occurrences()) == 1
    assert owner_a.list_recurring_occurrences()[0]['task_id'] == task_id
    assert owner_a.read_task(task_id)['status'] == 'todo'
    assert owner_a.list_task_runs() == []
    assert owner_b.run_due_recurring_schedules(now=due) == []
    owner_a.logout()
    owner_b.logout()
    restarted = LocalStore(owner_a.path)
    restarted.login('two_window_owner', 'two-window-check-password-2026')
    assert len(restarted.list_recurring_occurrences()) == 1


def test_two_windows_claim_one_work_item_once(tmp_path):
    owner_a, owner_b = two_owners(tmp_path)
    tid = owner_a.add_task('Manual owner-side queue claim')
    qid = owner_a.enqueue_task(tid)
    left, right = parallel(owner_a, owner_b, lambda store: store.claim_queued_task(now=100))
    assert [left, right].count(None) == 1
    assert next(x for x in (left, right) if x is not None) == {'id': qid, 'task_id': tid}
    row = next(x for x in owner_a.list_queued_tasks() if x['id'] == qid)
    assert row['attempts'] == 1 and row['state'] == 'claimed'
    assert [x['action'] for x in owner_a.list_queue_events(qid)] == ['enqueued', 'claimed']
    assert owner_a.list_task_runs() == []


def test_two_windows_cannot_both_resolve_same_claim(tmp_path):
    a, b = two_owners(tmp_path)
    tid = a.add_task('one final audit')
    qid = a.enqueue_task(tid)
    assert a.claim_queued_task(now=1) is not None
    def resolve(store):
        try:
            return store.resolve_queued_task(qid, True, now=2)
        except ValueError:
            return 'already-resolved'
    x, y = parallel(a, b, resolve)
    assert sorted([x, y]) == ['already-resolved', 'done']
    assert [v['action'] for v in a.list_queue_events(qid)] == ['enqueued', 'claimed', 'done']


def test_bool_now_and_limit_not_accepted(tmp_path):
    from desktop.recurring_scheduler import dispatch
    a, _ = two_owners(tmp_path)
    with a._connect() as con:
        for kwargs in ({'now': True}, {'now': 10, 'limit': True}):
            with pytest.raises(ValueError):
                dispatch(con, **kwargs)


def test_simulated_24h_recurrence_creates_288_unique_unassigned_tasks(tmp_path):
    a, b = two_owners(tmp_path)
    sid = a.add_recurring_schedule('Five-minute local draft', interval_minutes=5)
    a.set_recurring_schedule_enabled(sid, True)
    due = a.list_recurring_schedules()[0]['next_due']
    created = []
    for tick in range(288):
        now = due + tick * 300
        left, right = (a, b) if tick % 2 == 0 else (b, a)
        current = left.run_due_recurring_schedules(now=now)
        assert len(current) == 1
        assert right.run_due_recurring_schedules(now=now) == []
        created.extend(current)
    assert len(created) == len(set(created)) == 288
    assert len(a.list_recurring_occurrences()) == 288
    assert a.list_task_runs() == []
    assert all(a.read_task(tid)['status'] == 'todo' for tid in created)


def test_emergency_stop_blocks_schedule_and_manual_claim_until_owner_resumes(tmp_path):
    a, b = two_owners(tmp_path)
    sid = a.add_recurring_schedule('Owner-controlled tick', interval_minutes=5)
    a.set_recurring_schedule_enabled(sid, True)
    due = a.list_recurring_schedules()[0]['next_due']
    task = a.add_task('Manual queued task')
    qid = a.enqueue_task(task)
    a.emergency_stop_local(True, 'Owner suspended all operations')
    assert a.run_due_recurring_schedules(now=due) == []
    assert b.claim_queued_task(now=due) is None
    assert a.list_recurring_occurrences() == []
    a.emergency_stop_local(False, 'Owner resumed local work')
    assert len(b.run_due_recurring_schedules(now=due)) == 1
    assert a.claim_queued_task(now=due) == {'id': qid, 'task_id': task}
