import sqlite3
import pytest
from desktop.storage import LocalStore, AuthenticationError

@pytest.fixture
def store(tmp_path):
    s = LocalStore(tmp_path/'local.sqlite3')
    s.setup_owner('owner37','secure-stage37-local-password')
    return s

def test_event_idempotence_and_dispatch(store):
    event = store.submit_local_event('source:001','manual_alert','Check local operations')
    assert store.submit_local_event('source:001','manual_alert','Check local operations') == event
    assert len(store.list_local_events()) == 1
    tasks = store.dispatch_local_events()
    assert len(tasks) == 1
    assert store.dispatch_local_events() == []
    assert store.read_task(tasks[0])['status'] == 'todo'
    assert store.list_task_runs() == []
    with sqlite3.connect(store.path) as con:
        assert con.execute('PRAGMA foreign_key_check').fetchall() == []

def test_restart_and_auth(store):
    store.submit_local_event('event:2','review_requested','Review')
    store.logout()
    with pytest.raises(AuthenticationError):
        store.dispatch_local_events()
    reopened = LocalStore(store.path)
    reopened.login('owner37','secure-stage37-local-password')
    assert len(reopened.dispatch_local_events()) == 1
    assert len(reopened.list_local_events()) == 1

def test_validation_and_batch(store):
    with pytest.raises(ValueError):
        store.submit_local_event('a','network_webhook','bad')
    with pytest.raises(ValueError):
        store.submit_local_event('a','manual_alert','')
    with pytest.raises(ValueError):
        store.dispatch_local_events(limit=0)
    for i in range(3):
        store.submit_local_event(f'key:{i}', 'local_failure', f'Failure {i}')
    assert len(store.dispatch_local_events(limit=2)) == 2
    assert len(store.dispatch_local_events(limit=2)) == 1
