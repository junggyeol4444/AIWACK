import pytest
from desktop.storage import LocalStore,AuthenticationError

@pytest.fixture
def store(tmp_path):
    s=LocalStore(tmp_path/'q.sqlite3')
    s.setup_owner('owner','secure-local-password-123')
    return s

def test_queue_claim_retry_restart(store):
    task=store.add_task('queued work')
    q=store.enqueue_task(task,max_attempts=2)
    assert store.enqueue_task(task)==q
    assert store.claim_queued_task(now=100)=={'id':q,'task_id':task}
    assert store.resolve_queued_task(q,False,'temporary',now=100)=='pending'
    assert store.claim_queued_task(now=159) is None
    again=LocalStore(store.path)
    again.login('owner','secure-local-password-123')
    assert again.claim_queued_task(now=160)['id']==q
    assert again.resolve_queued_task(q,False,'again',now=160)=='failed'
    assert again.claim_queued_task(now=9999) is None
    assert len(again.list_queue_events(q))==5

def test_success_and_auth(store):
    t=store.add_task('ready')
    q=store.enqueue_task(t)
    assert store.claim_queued_task(now=1)['id']==q
    assert store.resolve_queued_task(q,True,now=2)=='done'
    with pytest.raises(ValueError): store.resolve_queued_task(q,True)
    store.logout()
    with pytest.raises(AuthenticationError): store.list_queued_tasks()

def test_dependencies_priority_and_validation(store):
    first=store.add_task('first')
    second=store.add_task('second')
    store.add_task_dependency(second,first)
    store.enqueue_task(second)
    assert store.claim_queued_task(now=1) is None
    q=store.enqueue_task(first)
    assert store.claim_queued_task(now=1)['id']==q
    with pytest.raises(ValueError): store.enqueue_task(first,max_attempts=0)
    with pytest.raises(ValueError): store.resolve_queued_task(q,False)
