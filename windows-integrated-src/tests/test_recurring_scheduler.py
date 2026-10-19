import sqlite3
import pytest
from desktop.storage import LocalStore, AuthenticationError

@pytest.fixture
def store(tmp_path):
    s=LocalStore(tmp_path/'test.sqlite3')
    s.setup_owner('scheduler_owner','long-local-scheduler-password')
    return s

def test_disabled_and_due_idempotent(store):
    sid=store.add_recurring_schedule('Daily review', interval_minutes=5)
    due=store.list_recurring_schedules()[0]['next_due']
    assert store.run_due_recurring_schedules(now=due+1000)==[]
    store.set_recurring_schedule_enabled(sid,True)
    due=store.list_recurring_schedules()[0]['next_due']
    assert store.run_due_recurring_schedules(now=due-1)==[]
    created=store.run_due_recurring_schedules(now=due)
    assert len(created)==1
    assert store.run_due_recurring_schedules(now=due)==[]
    assert store.read_task(created[0])['status']=='todo'
    assert len(store.list_task_status_events(created[0]))==1
    assert len(store.list_recurring_occurrences())==1
    assert store.list_task_runs()==[]

def test_restart_and_skipped_slots(store):
    sid=store.add_recurring_schedule('Recurring',interval_minutes=5)
    store.set_recurring_schedule_enabled(sid,True)
    due=store.list_recurring_schedules()[0]['next_due']
    created=store.run_due_recurring_schedules(now=due+300*500)
    assert len(created)==1
    store.logout()
    reopened=LocalStore(store.path)
    with pytest.raises(AuthenticationError): reopened.list_recurring_schedules()
    reopened.login('scheduler_owner','long-local-scheduler-password')
    assert reopened.run_due_recurring_schedules(now=due+300*500)==[]
    assert len(reopened.list_recurring_occurrences())==1
    with sqlite3.connect(store.path) as con:
        assert con.execute('PRAGMA foreign_key_check').fetchall()==[]

def test_input_and_disable(store):
    for value in (0,4,10081,True):
        with pytest.raises(ValueError): store.add_recurring_schedule('bad',interval_minutes=value)
    sid=store.add_recurring_schedule('valid')
    with pytest.raises(ValueError): store.set_recurring_schedule_enabled(sid,1)
    store.set_recurring_schedule_enabled(sid,True)
    store.set_recurring_schedule_enabled(sid,False)
    assert store.run_due_recurring_schedules(now=2**31)==[]
