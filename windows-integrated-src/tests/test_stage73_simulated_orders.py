"""Stage73 offline simulated order lifecycle; never real commerce."""
import sqlite3
import socket
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

import pytest

from desktop.storage import LocalStore, AuthenticationError
from desktop.product_release_review import CHECKS as RELEASE_CHECKS
from desktop.service_operations_plan import CHECKS as OPS_CHECKS
from desktop.sales_channel_contracts import CHECKS as CHANNEL_CHECKS
from desktop.offline_order_simulations import MAX_QUANTITY, MAX_TOTAL, STATES


@pytest.fixture
def store(tmp_path):
    s = LocalStore(tmp_path / 'stage73.sqlite3')
    s.setup_owner('owner73', 'stage73-long-password')
    return s


def prepared(store, *, price=1234, currency='KRW', reviewed=True):
    b = store.create_business(1, '사업', '목표')
    item = store.create_catalog_item(b, 'product', '상품', '설명', 1234, '계획')
    prototype = store.create_product_prototype(item)
    store.set_product_prototype_state(prototype, 'review_requested')
    store.record_product_release_review(prototype, {k:'unverified' for k in RELEASE_CHECKS}, '보류')
    plan = store.create_service_operations_plan(prototype, 'local_desktop_future',
                                                '담당', '백업', '롤백', '모니터')
    store.record_service_readiness(plan['id'], {k:'unverified' for k in OPS_CHECKS}, '')
    contract = store.create_sales_channel_contract(plan['id'], 'marketplace_future',
        '채널 계획', 'KR_future', 'manual_future', ['listing_draft_future'], '매핑', '법무')
    store.review_sales_channel_contract(contract['id'],
        {k:'unverified' for k in CHANNEL_CHECKS}, '관리자 자체 검토')
    listing = store.create_unpublished_listing(contract['id'], item, '상품', '설명',
                                               currency, price, '미검증 가격 가정')
    if reviewed:
        store.review_unpublished_listing(listing['id'], '관리자 자체 검토')
    return listing['id']


def create(store, listing, token='test_local_0001', qty=2):
    return store.create_simulated_order(listing, token, qty)


def test_creation_and_snapshot(store):
    listing = prepared(store)
    order = create(store, listing)
    assert order['state'] == 'RECEIVED_SIMULATED'
    assert order['total_minor'] == 2468
    assert order['currency'] == 'KRW' and order['listing_revision'] == 2
    assert order['simulation_only']
    assert not any(order[k] for k in ('real_order','customer_recorded','payment_received',
               'inventory_reserved','delivery_performed','revenue_recognized',
               'external_channel_connected','stale_source'))
    assert store.simulated_order_history(order['id'])[0]['action'] == 'created'
    assert len(store.simulated_orders()) == 1


def test_review_then_close(store):
    listing = prepared(store)
    order = create(store, listing)
    review = store.transition_simulated_order(order['id'], 'owner_reviewed', '검토 완료 모의')
    assert review['state'] == 'REVIEWED_SIMULATED'
    closed = store.transition_simulated_order(order['id'], 'closed', '종료 모의, 배송 없음')
    assert closed['state'] == 'CLOSED_SIMULATED' and not closed['delivery_performed']
    assert [e['revision'] for e in store.simulated_order_history(order['id'])] == [1,2,3]
    with pytest.raises(ValueError):
        store.transition_simulated_order(order['id'], 'cancelled', '종료 뒤 취소 금지')


def test_cancel_from_received_and_reviewed(store):
    listing = prepared(store)
    first = create(store, listing, 'test_local_0002')
    second = create(store, listing, 'test_local_0003')
    assert store.transition_simulated_order(first['id'], 'cancelled', '모의 취소')['state'] == 'CANCELLED_SIMULATED'
    store.transition_simulated_order(second['id'], 'owner_reviewed', '모의 검토')
    assert store.transition_simulated_order(second['id'], 'cancelled', '모의 취소')['state'] == 'CANCELLED_SIMULATED'
    assert not store.simulated_order(first['id'])['payment_received']


def test_idempotency_and_conflicts(store):
    listing = prepared(store)
    first = create(store, listing)
    again = create(store, listing)
    assert again['id'] == first['id'] and len(store.simulated_order_history(first['id'])) == 1
    with pytest.raises(ValueError, match='중복'):
        create(store, listing, qty=3)
    assert len(store.simulated_orders()) == 1


@pytest.mark.parametrize('token', ['', 'short', 'a'*49, 'name@example.com',
                                  'https://example.com', '고객이름12345', 'bad space token',
                                  'abc/defghi', None, 123, 'api_key_secret'])
def test_bad_token(store, token):
    listing = prepared(store)
    with pytest.raises(ValueError):
        create(store, listing, token)


@pytest.mark.parametrize('qty', [0, -1, MAX_QUANTITY+1, 1.5, True, '2', None])
def test_bad_quantity(store, qty):
    listing = prepared(store)
    with pytest.raises(ValueError):
        create(store, listing, qty=qty)


def test_unreviewed_listing_blocked(store):
    listing = prepared(store, reviewed=False)
    with pytest.raises(ValueError, match='관리자'):
        create(store, listing)


def test_listing_retired_stale_blocks_transitions(store):
    listing = prepared(store)
    order = create(store, listing)
    store.retire_unpublished_listing(listing, '로컬 폐기')
    assert store.simulated_order(order['id'])['stale_source']
    with pytest.raises(ValueError, match='원본'):
        store.transition_simulated_order(order['id'], 'cancelled', '모의 취소')
    assert len(store.simulated_order_history(order['id'])) == 1


@pytest.mark.parametrize('action', ['created','paid','shipped','refunded','',None])
def test_bad_transition(store, action):
    listing = prepared(store)
    order = create(store, listing)
    with pytest.raises(ValueError):
        store.transition_simulated_order(order['id'], action, '모의 상태')


@pytest.mark.parametrize('note', ['', 'https://example.com', 'x'*501, 'a@b.com', None])
def test_bad_note(store, note):
    listing = prepared(store)
    order = create(store, listing)
    with pytest.raises(ValueError):
        store.transition_simulated_order(order['id'], 'owner_reviewed', note)


def test_no_close_directly(store):
    listing = prepared(store)
    order = create(store, listing)
    with pytest.raises(ValueError):
        store.transition_simulated_order(order['id'], 'closed', '단계 건너뛰기')


def test_rollback_no_partial_write(store):
    listing = prepared(store)
    with pytest.raises(ValueError):
        create(store, listing, 'bad token')
    assert store.simulated_orders() == []


def test_append_only_triggers(store):
    listing = prepared(store)
    order = create(store, listing)
    with store._connect() as con:
        for table in ('local_simulated_orders', 'local_simulated_order_events'):
            with pytest.raises(sqlite3.DatabaseError, match='append-only'):
                con.execute(f'UPDATE {table} SET created_at=created_at WHERE id=1')
            with pytest.raises(sqlite3.DatabaseError, match='append-only'):
                con.execute(f'DELETE FROM {table} WHERE id=1')
    assert store.simulated_order(order['id'])['state'] == 'RECEIVED_SIMULATED'


def test_tamper_event_detected(store):
    listing = prepared(store)
    order = create(store, listing)
    with store._connect() as con:
        con.execute('DROP TRIGGER local_simulated_order_events_no_update')
        con.execute("UPDATE local_simulated_order_events SET note='tampered' WHERE order_id=?", (order['id'],))
    with pytest.raises(ValueError):
        store.simulated_order_history(order['id'])


def test_tamper_base_detected(store):
    listing = prepared(store)
    order = create(store, listing)
    with store._connect() as con:
        con.execute('DROP TRIGGER local_simulated_orders_no_update')
        con.execute('UPDATE local_simulated_orders SET quantity=5,total_minor=6170 WHERE id=?', (order['id'],))
    with pytest.raises(ValueError, match='해시'):
        store.simulated_order(order['id'])


def test_no_network_and_no_provider(store):
    listing = prepared(store)
    with patch.object(socket, 'socket', side_effect=AssertionError('socket forbidden')), \
         patch.object(socket, 'getaddrinfo', side_effect=AssertionError('dns forbidden')):
        order = create(store, listing)
        store.transition_simulated_order(order['id'], 'owner_reviewed', '모의 검토')
        assert len(store.simulated_orders()) == 1


def test_logout_denies(store):
    listing = prepared(store)
    order = create(store, listing)
    store.logout()
    for call in (lambda: store.simulated_orders(),
                 lambda: store.simulated_order(order['id']),
                 lambda: store.simulated_order_history(order['id']),
                 lambda: create(store, listing, 'test_local_0004'),
                 lambda: store.transition_simulated_order(order['id'], 'cancelled', '모의 취소')):
        with pytest.raises((AuthenticationError, PermissionError)):
            call()


def test_database_reopen_persistence(store):
    listing = prepared(store)
    order = create(store, listing)
    reopened = LocalStore(store.path)
    reopened.login('owner73', 'stage73-long-password')
    assert reopened.simulated_order(order['id'])['total_minor'] == 2468
    assert len(reopened.simulated_order_history(order['id'])) == 1


def test_unique_token_concurrent(store):
    listing = prepared(store)
    def job(_):
        return create(store, listing)['id']
    with ThreadPoolExecutor(max_workers=2) as executor:
        ids = list(executor.map(job, range(2)))
    assert ids[0] == ids[1]
    assert len(store.simulated_orders()) == 1


def test_max_total_and_zero_price(store):
    listing = prepared(store, price=1_000_000_000_000)
    order = create(store, listing, qty=1000)
    assert order['total_minor'] == MAX_TOTAL


def test_zero_price(store):
    listing = prepared(store, price=0)
    order = create(store, listing)
    assert order['total_minor'] == 0 and not order['revenue_recognized']


def test_bad_id_and_limit(store):
    prepared(store)
    for bad in (0, -1, '1', True, None):
        with pytest.raises(ValueError):
            store.simulated_order(bad)
    for bad in (0, -1, 201, True, '1'):
        with pytest.raises(ValueError):
            store.simulated_orders(bad)


def test_state_constants():
    assert all(state.endswith('_SIMULATED') for state in STATES)
