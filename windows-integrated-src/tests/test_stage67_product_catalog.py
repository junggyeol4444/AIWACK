"""Stage67 local product/service information; never real release/sales."""
import socket
import sqlite3
from unittest.mock import patch

import pytest

from desktop.storage import LocalStore


@pytest.fixture
def store(tmp_path):
    s = LocalStore(tmp_path / 'owner.sqlite3')
    s.setup_owner('owner67', 'stage67-long-password')
    return s


def business(s):
    return s.create_business(1, '사업 A', '목표 A')


def make(s, b, **kwargs):
    params = dict(kind='product', name='초안 상품', description='고객 가정 설명',
                  assumed_price_krw=10000, delivery_note='오프라인 제공 계획')
    params.update(kwargs)
    return s.create_catalog_item(b, **params)


def test_two_businesses_multiple_kinds_persistence(store):
    a, b = business(store), store.create_business(2, '사업 B', '목표 B')
    p = make(store, a)
    q = make(store, a, kind='service', name='지원 서비스')
    r = make(store, b, name='다른 사업 상품', assumed_price_krw=0)
    assert [x['id'] for x in store.catalog_items(a)] == [q, p]
    assert [x['id'] for x in store.catalog_items(b)] == [r]
    assert store.catalog_item(p)['price_is_assumption'] is True
    assert store.catalog_item(q)['external_actions_executed'] is False
    assert store.catalog_item(r)['actual_sales_verified'] is False
    store.logout()
    reopened = LocalStore(store.path)
    reopened.login('owner67', 'stage67-long-password')
    assert len(reopened.catalog_items()) == 3


def test_optional_project_belongs_to_business_and_is_not_modified(store):
    a, b = business(store), store.create_business(2, '사업 B', '목표 B')
    project = store.create_business_project(a, '프로젝트 A', '목표')
    before = store.business_project(project)
    p = make(store, a, project_id=project)
    assert store.catalog_item(p)['project_id'] == project
    assert store.business_project(project) == before
    with pytest.raises(ValueError): make(store, b, project_id=project)
    store.set_business_project_state(project, 'cancelled')
    with pytest.raises(ValueError): make(store, a, project_id=project)
    assert store.catalog_item(p)['project_id'] == project


def test_revise_version_history_and_review_workflow(store):
    b = business(store)
    p = make(store, b)
    item = store.revise_catalog_item(p, '개정된 설명', 9000, '제공 방식 가정')
    assert (item['version'], item['assumed_price_krw']) == (2, 9000)
    assert len(store.catalog_item_events(p)) == 2
    with pytest.raises(ValueError, match='변경된'): store.revise_catalog_item(p, '개정된 설명', 9000, '제공 방식 가정')
    assert store.set_catalog_item_state(p, 'review_pending')['state'] == 'review_pending'
    with pytest.raises(ValueError): store.revise_catalog_item(p, '추가 수정', 5000, '제공 계획')
    with pytest.raises(ValueError): store.set_catalog_item_state(p, 'review_pending')
    assert store.set_catalog_item_state(p, 'draft')['state'] == 'draft'
    assert store.set_catalog_item_state(p, 'archived')['state'] == 'archived'
    with pytest.raises(ValueError): store.set_catalog_item_state(p, 'draft')
    assert len(store.catalog_item_events(p)) == 5


@pytest.mark.parametrize('bad', [0, -1, True, '1', None, 999999])
def test_invalid_business(store, bad):
    with pytest.raises(ValueError): make(store, bad)


@pytest.mark.parametrize('kwargs', [
    {'kind': 'payment'}, {'kind': 1}, {'name': ''}, {'name': 'x'*121},
    {'description': ''}, {'description': 'x'*1001}, {'delivery_note': ''},
    {'delivery_note': 'x'*401}, {'assumed_price_krw': -1},
    {'assumed_price_krw': 10**13}, {'assumed_price_krw': True},
    {'assumed_price_krw': 1.2}, {'name': 'password=secret'},
    {'description': 'authorization: bearer secret'}, {'delivery_note': 'api_key:secret'},
    {'name': 'newline\ninjection'}, {'delivery_note': 'tab\tinjection'},
])
def test_invalid_fields_do_not_write(store, kwargs):
    b = business(store)
    with pytest.raises(ValueError): make(store, b, **kwargs)
    assert store.catalog_items() == []


def test_closed_business_rejects_new_items(store):
    b = business(store)
    store.set_business_state(b, 'closed')
    with pytest.raises(ValueError): make(store, b)


def test_invalid_id_limit_and_state(store):
    b = business(store)
    p = make(store, b)
    for bad in (0, -1, True, '1', 999999):
        with pytest.raises(ValueError): store.catalog_item(bad)
    for bad in (0, True, 201, '2'):
        with pytest.raises(ValueError): store.catalog_items(limit=bad)
    for bad in ('published', 'live', 'sold', 'active', 1):
        with pytest.raises(ValueError): store.set_catalog_item_state(p, bad)
    with pytest.raises(ValueError): store.catalog_items(business_id=999999)


def test_append_only_audit_and_tamper_detection(store):
    b = business(store)
    p = make(store, b)
    with store._connect() as con:
        for sql in (
            'DELETE FROM local_catalog_items',
            "UPDATE local_catalog_items SET name='fake'",
            'DELETE FROM local_catalog_events',
            "UPDATE local_catalog_events SET snapshot_json='{}'",
        ):
            with pytest.raises(sqlite3.DatabaseError): con.execute(sql)
        con.execute('DROP TRIGGER local_catalog_events_no_update')
        con.execute("UPDATE local_catalog_events SET snapshot_json='{}' WHERE item_id=?", (p,))
    with pytest.raises(ValueError, match='감사'):
        store.catalog_item(p)


def test_current_snapshot_tamper_detection(store):
    b = business(store)
    p = make(store, b)
    with store._connect() as con:
        con.execute('UPDATE local_catalog_items SET assumed_price_krw=42 WHERE id=?', (p,))
    with pytest.raises(ValueError, match='불일치'):
        store.catalog_item(p)


def test_event_failure_rolls_back_create_and_revise(store):
    b = business(store)
    with store._connect() as con:
        con.execute('''CREATE TRIGGER fail67 BEFORE INSERT ON local_catalog_events
                       BEGIN SELECT RAISE(ABORT,'forced'); END''')
    with pytest.raises(sqlite3.DatabaseError): make(store, b)
    assert store.catalog_items() == []
    with store._connect() as con: con.execute('DROP TRIGGER fail67')
    p = make(store, b)
    with store._connect() as con:
        con.execute('''CREATE TRIGGER fail67 BEFORE INSERT ON local_catalog_events
                       BEGIN SELECT RAISE(ABORT,'forced'); END''')
    with pytest.raises(sqlite3.DatabaseError): store.revise_catalog_item(p, '수정', 1, '제공')
    assert store.catalog_item(p)['version'] == 1


def test_auth_and_socket_dns_block(store):
    b = business(store)
    def forbidden(*args, **kwargs): raise AssertionError('network forbidden')
    with patch.object(socket, 'socket', side_effect=forbidden), \
         patch.object(socket, 'getaddrinfo', side_effect=forbidden):
        p = make(store, b)
        store.revise_catalog_item(p, '수정', 0, '수정된 제공')
        store.set_catalog_item_state(p, 'review_pending')
        assert store.catalog_items()[0]['id'] == p
        assert len(store.catalog_item_events(p)) == 3
    store.logout()
    for call in (
        lambda: make(store, b), lambda: store.catalog_item(p),
        lambda: store.catalog_items(), lambda: store.revise_catalog_item(p, 'x', 1, 'y'),
        lambda: store.set_catalog_item_state(p, 'archived'),
        lambda: store.catalog_item_events(p),
    ):
        with pytest.raises(PermissionError): call()
