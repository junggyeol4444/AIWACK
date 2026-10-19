"""Stage66 offline multi-business projects; explicit planning only."""
import socket
import sqlite3
from unittest.mock import patch

import pytest

from desktop.storage import LocalStore


@pytest.fixture
def store(tmp_path):
    s = LocalStore(tmp_path / 'owner.sqlite3')
    s.setup_owner('owner66', 'long-password-stage66')
    return s


def two_businesses(s):
    return (s.create_business(1,'사업 A','목표 A'),
            s.create_business(2,'사업 B','목표 B'))


def test_many_businesses_projects_independent_and_persistent(store):
    a,b = two_businesses(store)
    p = store.create_business_project(a,'A 프로젝트','제작 목표',12000)
    q = store.create_business_project(a,'두 번째 프로젝트','다른 목표',300)
    r = store.create_business_project(b,'B 프로젝트','판매 준비',900)
    assert [x['id'] for x in store.business_projects(a)] == [q,p]
    assert [x['id'] for x in store.business_projects(b)] == [r]
    assert len(store.business_projects()) == 3
    store.set_business_project_state(p,'active')
    assert store.business_project(q)['state'] == 'planned'
    assert store.business_project(r)['state'] == 'planned'
    assert store.business_project(p)['planned_budget_krw'] == 12000
    assert store.business_project(p)['external_actions_executed'] is False
    store.logout()
    reopened = LocalStore(store.path)
    reopened.login('owner66', 'long-password-stage66')
    assert reopened.business_project(p)['state'] == 'active'


def test_existing_tasks_link_and_unlink_no_task_mutation(store):
    a,b = two_businesses(store)
    p = store.create_business_project(a,'A','goal')
    q = store.create_business_project(b,'B','goal')
    t = store.add_task('existing work')
    before = store.read_task(t)
    assert store.set_business_project_task(p,t,True)['task_ids'] == [t]
    assert store.read_task(t) == before
    with pytest.raises(ValueError, match='이미'):
        store.set_business_project_task(q,t,True)
    with pytest.raises(ValueError):
        store.set_business_project_task(q,t,False)
    assert store.set_business_project_task(p,t,False)['task_ids'] == []
    assert store.set_business_project_task(q,t,True)['task_ids'] == [t]
    assert store.read_task(t) == before
    assert len(store.business_project_events(p)) == 3


def test_state_transitions_manual_only(store):
    a,_ = two_businesses(store)
    p = store.create_business_project(a,'A','goal')
    with pytest.raises(ValueError): store.set_business_project_state(p,'completed')
    store.set_business_project_state(p,'active')
    store.set_business_project_state(p,'paused')
    store.set_business_project_state(p,'active')
    store.set_business_project_state(p,'completed')
    with pytest.raises(ValueError): store.set_business_project_state(p,'active')
    with pytest.raises(ValueError): store.set_business_project_state(p,'completed')
    assert store.business_project(p)['state'] == 'completed'
    assert len(store.business_project_events(p)) == 5


def test_business_closed_restrictions(store):
    a,_ = two_businesses(store)
    p = store.create_business_project(a,'A','goal')
    store.set_business_state(a,'closed')
    with pytest.raises(ValueError): store.create_business_project(a,'new','goal')
    with pytest.raises(ValueError): store.set_business_project_state(p,'active')
    assert store.business_project(p)['state'] == 'planned'
    assert store.set_business_project_state(p,'cancelled')['state'] == 'cancelled'


def test_employee_must_be_business_participant(store):
    a,b = two_businesses(store)
    with store._connect() as con:
        eid = con.execute("INSERT INTO ai_employee_profiles(employee_key,display_name) VALUES('worker66','Worker')").lastrowid
    with pytest.raises(ValueError): store.create_business_project(a,'A','goal',responsible_employee_id=eid)
    store.set_business_participant(a,eid,True)
    p = store.create_business_project(a,'A','goal',responsible_employee_id=eid)
    assert store.business_project(p)['responsible_employee_id'] == eid
    with pytest.raises(ValueError): store.create_business_project(b,'B','goal',responsible_employee_id=eid)


@pytest.mark.parametrize('bad', [0,-1,True,'1',99999,None])
def test_invalid_business_ids(store,bad):
    with pytest.raises(ValueError): store.create_business_project(bad,'A','goal')


@pytest.mark.parametrize('title,objective,budget', [('', 'goal', 0),('A','',0),
    ('A'*121,'goal',0),('A','G'*501,0),('A','goal',-1),('A','goal',True),
    ('A','goal',1.5),('A','goal',10**13),('password=secret','goal',0),
    ('A','api_key:secret',0),('A','goal\nline',0)])
def test_invalid_fields(store,title,objective,budget):
    a,_ = two_businesses(store)
    with pytest.raises(ValueError): store.create_business_project(a,title,objective,budget)
    assert store.business_projects() == []


def test_invalid_task_and_limit_inputs(store):
    a,_ = two_businesses(store)
    p = store.create_business_project(a,'A','goal')
    for bad in (0,-1,True,'1',99999):
        with pytest.raises(ValueError): store.set_business_project_task(p,bad,True)
        with pytest.raises(ValueError): store.business_project(bad)
    for bad in (0,True,201,'2'):
        with pytest.raises(ValueError): store.business_projects(limit=bad)
    with pytest.raises(ValueError): store.set_business_project_task(p,1,'yes')
    with pytest.raises(ValueError): store.set_business_project_state(p,'invalid')


def test_project_immutable_and_audit_tamper_detected(store):
    a,_ = two_businesses(store)
    p = store.create_business_project(a,'A','goal')
    with store._connect() as con:
        for sql in (
            'DELETE FROM managed_business_projects',
            "UPDATE managed_business_projects SET title='tampered'",
            'DELETE FROM managed_project_events',
            "UPDATE managed_project_events SET detail_json='{}'",
        ):
            with pytest.raises(sqlite3.DatabaseError): con.execute(sql)
        con.execute('DROP TRIGGER managed_project_events_no_update')
        con.execute("UPDATE managed_project_events SET detail_json='{}' WHERE project_id=?",(p,))
    with pytest.raises(ValueError,match='감사'):
        store.business_project(p)


def test_task_link_tamper_detected(store):
    a,_ = two_businesses(store)
    p = store.create_business_project(a,'A','goal')
    t = store.add_task('task')
    store.set_business_project_task(p,t,True)
    with store._connect() as con:
        con.execute('DELETE FROM managed_project_task_links WHERE task_id=?',(t,))
    with pytest.raises(ValueError,match='감사'):
        store.business_project(p)


def test_failed_audit_transaction_rolls_back(store):
    a,_ = two_businesses(store)
    with store._connect() as con:
        con.execute("""CREATE TRIGGER fail66 BEFORE INSERT ON managed_project_events
            BEGIN SELECT RAISE(ABORT,'forced'); END""")
    with pytest.raises(sqlite3.DatabaseError):
        store.create_business_project(a,'A','goal')
    assert store.business_projects() == []


def test_auth_and_offline_no_sockets(store):
    a,_ = two_businesses(store)
    def forbidden(*args, **kwargs): raise AssertionError('network forbidden')
    with patch.object(socket,'socket',side_effect=forbidden), \
         patch.object(socket,'getaddrinfo',side_effect=forbidden):
        p = store.create_business_project(a,'A','goal')
        t = store.add_task('task')
        store.set_business_project_task(p,t,True)
        store.set_business_project_state(p,'active')
        assert store.business_projects()[0]['task_ids'] == [t]
    store.logout()
    for call in (lambda: store.create_business_project(a,'B','goal'),
                 lambda: store.business_project(p), lambda: store.business_projects(),
                 lambda: store.set_business_project_state(p,'paused'),
                 lambda: store.set_business_project_task(p,t,False),
                 lambda: store.business_project_events(p)):
        with pytest.raises(PermissionError): call()


def test_stage43_chat_rooms_not_reinterpreted(store):
    a,_ = two_businesses(store)
    room = store.create_project_room('chat room','collaboration')
    assert store.business_projects() == []
    p = store.create_business_project(a,'Business Project','goal')
    assert store.business_project(p)['title'] == 'Business Project'
    assert store.list_project_rooms()[0]['id'] == room
