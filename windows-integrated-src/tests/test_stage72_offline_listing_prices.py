"""Stage72 offline unpublished listing/price drafts; no actual publication."""
import socket
import sqlite3
from unittest.mock import patch

import pytest

from desktop.storage import LocalStore, AuthenticationError
from desktop.product_release_review import CHECKS as RELEASE_CHECKS
from desktop.service_operations_plan import CHECKS as OPS_CHECKS
from desktop.sales_channel_contracts import CHECKS as CHANNEL_CHECKS
from desktop.offline_listing_prices import CURRENCIES, MAX_PRICE


@pytest.fixture
def store(tmp_path):
    s = LocalStore(tmp_path / 'stage72.sqlite3')
    s.setup_owner('owner72', 'stage72-long-password')
    return s


def prepared(store, *, review=True, scopes=None):
    business = store.create_business(1, '사업', '목표')
    item = store.create_catalog_item(business, 'product', '카탈로그 상품', '설명', 1234, '계획')
    prototype = store.create_product_prototype(item)
    store.set_product_prototype_state(prototype, 'review_requested')
    store.record_product_release_review(prototype, {k: 'unverified' for k in RELEASE_CHECKS}, '보류')
    plan = store.create_service_operations_plan(prototype, 'local_desktop_future',
                                                '담당', '백업', '롤백', '모니터')
    store.record_service_readiness(plan['id'], {k: 'unverified' for k in OPS_CHECKS}, '')
    contract = store.create_sales_channel_contract(
        plan['id'], 'marketplace_future', '계획 채널', 'KR_future', 'manual_future',
        scopes if scopes is not None else ['listing_draft_future'], '매핑 계획', '법무 계획')
    if review:
        store.review_sales_channel_contract(contract['id'],
            {k: 'unverified' for k in CHANNEL_CHECKS}, '검토 기록')
    return item, contract['id'], plan['id'], prototype


def make(store, item, contract, *, currency='KRW', price=1234):
    return store.create_unpublished_listing(contract, item, '미게시 상품', '로컬 설명',
                                            currency, price, '검증되지 않은 가격 가정')


def test_create_unpublished_and_chain(store):
    item, contract, _, _ = prepared(store)
    row = make(store, item, contract)
    assert row['state'] == 'DRAFT_UNPUBLISHED' and not row['stale_source']
    assert row['catalog_version'] == 1 and row['currency_minor_unit'] == '원'
    assert row['price_is_assumption']
    assert not any(row[k] for k in ('published', 'connected', 'price_synced',
                                    'orders_received', 'payments_received'))
    assert store.unpublished_listing_history(row['id'])[0]['action'] == 'created'
    assert len(store.unpublished_listings()) == 1


def test_revision_review_retire_and_history(store):
    item, contract, _, _ = prepared(store)
    ident = make(store, item, contract)['id']
    revised = store.revise_unpublished_listing(ident, '미게시 개정', '변경 설명', 'USD', 999, '센트 가격 가정')
    assert revised['revision'] == 2 and revised['currency_minor_unit'] == '센트'
    reviewed = store.review_unpublished_listing(ident, '관리자 주장 검토')
    assert reviewed['state'] == 'REVIEWED_UNPUBLISHED' and not reviewed['published']
    with pytest.raises(ValueError, match='초안'):
        store.revise_unpublished_listing(ident, '새 상품', '설명', 'KRW', 1, '가정')
    retired = store.retire_unpublished_listing(ident, '계획 폐기')
    assert retired['state'] == 'RETIRED_UNPUBLISHED'
    with pytest.raises(ValueError, match='이미 폐기'):
        store.retire_unpublished_listing(ident, '재폐기')
    events = store.unpublished_listing_history(ident)
    assert [e['action'] for e in events] == ['created','revised','owner_reviewed','retired']
    assert all(events[i]['previous_digest'] == events[i-1]['digest'] for i in range(1,4))
    assert make(store, item, contract)['state'] == 'DRAFT_UNPUBLISHED'


def test_duplicate_active_rejected(store):
    item, contract, _, _ = prepared(store)
    make(store, item, contract)
    with pytest.raises(ValueError, match='이미'):
        make(store, item, contract)


def test_contract_review_and_scope_required(store):
    item, contract, _, _ = prepared(store, review=False)
    with pytest.raises(ValueError, match='Stage71'):
        make(store, item, contract)
    store.review_sales_channel_contract(contract, {k: 'unverified' for k in CHANNEL_CHECKS}, '')
    assert make(store, item, contract)['state'] == 'DRAFT_UNPUBLISHED'


def test_scope_missing_rejected(store):
    item, contract, _, _ = prepared(store, scopes=['catalog_metadata_future'])
    with pytest.raises(ValueError, match='Stage71'):
        make(store, item, contract)


def test_wrong_catalog_rejected(store):
    item, contract, _, _ = prepared(store)
    b = store.create_business(1, '다른 사업', '목표')
    wrong = store.create_catalog_item(b, 'product', '다른 상품', '설명', 0, '계획')
    with pytest.raises(ValueError, match='동일한'):
        make(store, wrong, contract)


def test_catalog_revision_stales_listing(store):
    item, contract, _, _ = prepared(store)
    ident = make(store, item, contract)['id']
    store.revise_catalog_item(item, '변경 설명', 8888, '변경 계획')
    assert store.unpublished_listing(ident)['stale_source']
    with pytest.raises(ValueError, match='원본 변경'):
        store.review_unpublished_listing(ident, '확인')
    assert store.retire_unpublished_listing(ident, '원본 변경')['state'] == 'RETIRED_UNPUBLISHED'


def test_channel_review_stales_listing(store):
    item, contract, _, _ = prepared(store)
    ident = make(store, item, contract)['id']
    store.review_sales_channel_contract(contract, {k: 'unverified' for k in CHANNEL_CHECKS}, '재검토')
    assert store.unpublished_listing(ident)['stale_source']


def test_channel_retire_stales_listing(store):
    item, contract, _, _ = prepared(store)
    ident = make(store, item, contract)['id']
    store.retire_sales_channel_contract(contract, '폐기')
    assert store.unpublished_listing(ident)['stale_source']


@pytest.mark.parametrize('bad', ['CNY','krw','',None,3,True])
def test_invalid_currency(store, bad):
    item, contract, _, _ = prepared(store)
    with pytest.raises(ValueError, match='통화'):
        make(store, item, contract, currency=bad)


@pytest.mark.parametrize('bad', [-1,MAX_PRICE+1,1.5,'100',True,None])
def test_invalid_price(store, bad):
    item, contract, _, _ = prepared(store)
    with pytest.raises(ValueError, match='가격'):
        make(store, item, contract, price=bad)


@pytest.mark.parametrize('currency', CURRENCIES)
def test_currency_minor_unit_explicit(store, currency):
    item, contract, _, _ = prepared(store)
    row = make(store, item, contract, currency=currency, price=0)
    assert row['currency'] == currency and row['price_minor'] == 0


@pytest.mark.parametrize('bad', ['', ' ', 'x'*121, 'https://example.com',
                                 'owner@example.com', 'api_key abc', None, 12])
def test_invalid_title_or_sensitive(store, bad):
    item, contract, _, _ = prepared(store)
    with pytest.raises(ValueError, match='상품명'):
        store.create_unpublished_listing(contract, item, bad, '설명', 'KRW', 1, '가정')


def test_no_change_revision_rejected(store):
    item, contract, _, _ = prepared(store)
    ident = make(store, item, contract)['id']
    with pytest.raises(ValueError, match='변경된'):
        store.revise_unpublished_listing(ident, '미게시 상품', '로컬 설명', 'KRW', 1234,
                                         '검증되지 않은 가격 가정')


def test_integrity_tampering_detected(store):
    item, contract, _, _ = prepared(store)
    ident = make(store, item, contract)['id']
    with sqlite3.connect(store.path) as con:
        con.execute('DROP TRIGGER local_unpublished_listing_events_no_update')
        con.execute('UPDATE local_unpublished_listing_events SET snapshot_json=? WHERE listing_id=?',
                    ('{}', ident))
    with pytest.raises(ValueError, match='손상'):
        store.unpublished_listing(ident)


def test_append_only_triggers(store):
    item, contract, _, _ = prepared(store)
    ident = make(store, item, contract)['id']
    with sqlite3.connect(store.path) as con:
        with pytest.raises(sqlite3.IntegrityError):
            con.execute('DELETE FROM local_unpublished_listings WHERE id=?', (ident,))
        with pytest.raises(sqlite3.IntegrityError):
            con.execute('UPDATE local_unpublished_listing_events SET note=? WHERE listing_id=?', ('tamper',ident))


def test_auth_required(tmp_path):
    s = LocalStore(tmp_path / 'unauth.sqlite3')
    for method,args in (
        (s.create_unpublished_listing, (1,1,'a','b','KRW',1,'c')),
        (s.unpublished_listing,(1,)), (s.unpublished_listings,()),
        (s.unpublished_listing_history,(1,)),
        (s.revise_unpublished_listing,(1,'a','b','KRW',1,'c')),
        (s.review_unpublished_listing,(1,'note')),
        (s.retire_unpublished_listing,(1,'note')),
    ):
        with pytest.raises((PermissionError, AuthenticationError)):
            method(*args)


def test_network_and_dns_blocked(store):
    item, contract, _, _ = prepared(store)
    with patch.object(socket,'socket',side_effect=AssertionError('network')), \
         patch.object(socket,'getaddrinfo',side_effect=AssertionError('dns')):
        ident = make(store, item, contract)['id']
        store.revise_unpublished_listing(ident, '개정', '설명', 'JPY', 200, '가정')
        store.review_unpublished_listing(ident, '검토')
        store.retire_unpublished_listing(ident, '폐기')
        assert store.unpublished_listing(ident)['state'] == 'RETIRED_UNPUBLISHED'


def test_persists_across_restart(store):
    item, contract, _, _ = prepared(store)
    ident = make(store, item, contract)['id']
    s2 = LocalStore(store.path)
    s2.login('owner72','stage72-long-password')
    assert s2.unpublished_listing(ident)['price_minor'] == 1234
