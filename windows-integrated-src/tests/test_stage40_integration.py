"""Stage40: offline integration of event dispatch, durable queue, restart and recovery."""
from desktop.storage import LocalStore


def test_event_to_queue_restart_and_manual_recovery(tmp_path):
    path = tmp_path / 'integration.sqlite3'
    store = LocalStore(path)
    store.setup_owner('owner', 'secure-local-password-123')
    event_id = store.submit_local_event('unique-40', 'manual_alert', 'Investigate event')
    assert store.submit_local_event('unique-40', 'manual_alert', 'Investigate event') == event_id
    created = store.dispatch_local_events()
    assert len(created) == 1
    assert store.dispatch_local_events() == []
    queue_id = store.enqueue_task(created[0], max_attempts=2)
    assert store.claim_queued_task(now=100)['id'] == queue_id
    reopened = LocalStore(path)
    reopened.login('owner', 'secure-local-password-123')
    assert reopened.claim_queued_task(now=101) is None
    assert reopened.recover_queued_task(queue_id, now=200) == 'pending'
    assert reopened.claim_queued_task(now=259) is None
    assert reopened.claim_queued_task(now=260)['id'] == queue_id
    assert reopened.resolve_queued_task(queue_id, True, now=261) == 'done'
    assert reopened.claim_queued_task(now=999) is None
    assert any(item['action'] == 'recovered' for item in reopened.list_queue_events(queue_id))
