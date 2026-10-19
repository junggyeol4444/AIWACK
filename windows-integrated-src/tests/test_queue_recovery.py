import pytest
from desktop.storage import LocalStore, AuthenticationError

@pytest.fixture
def store(tmp_path):
    s = LocalStore(tmp_path / 'recover.sqlite3')
    s.setup_owner('owner', 'secure-local-password-123')
    return s

def test_restart_manual_recovery_and_audit(store):
    task = store.add_task('interrupted')
    q = store.enqueue_task(task, max_attempts=2)
    assert store.claim_queued_task(now=100)['id'] == q
    restarted = LocalStore(store.path)
    restarted.login('owner', 'secure-local-password-123')
    assert restarted.claim_queued_task(now=200) is None
    assert restarted.recover_queued_task(q, now=200) == 'pending'
    assert restarted.claim_queued_task(now=259) is None
    assert restarted.claim_queued_task(now=260)['id'] == q
    assert any(e['action'] == 'recovered' for e in restarted.list_queue_events(q))
    assert restarted.recover_queued_task(q, now=300) == 'failed'
    assert restarted.claim_queued_task(now=1000) is None

def test_recovery_invalid_and_permission(store):
    q = store.enqueue_task(store.add_task('not claimed'))
    with pytest.raises(ValueError):
        store.recover_queued_task(q)
    store.claim_queued_task(now=1)
    store.logout()
    with pytest.raises(AuthenticationError):
        store.recover_queued_task(q)
