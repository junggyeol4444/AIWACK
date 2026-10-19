"""Stage71 inert offline sales channel contract tests (no real accounts/network)."""
from pathlib import Path
import socket
import sqlite3
from unittest.mock import patch

import pytest

from desktop.storage import LocalStore, AuthenticationError
from desktop.product_release_review import CHECKS as RELEASE_CHECKS
from desktop.service_operations_plan import CHECKS as OPS_CHECKS
from desktop.sales_channel_contracts import CHECKS, KINDS, REGIONS, MODES, SCOPES


@pytest.fixture
def store(tmp_path):
    s = LocalStore(tmp_path / 'owner.sqlite3')
    s.setup_owner('owner71', 'stage71-long-password')
    return s


def prepared(store):
    b = store.create_business(1, '사업', '목표')
    c = store.create_catalog_item(b, 'service', '초안', '설명', 1000, '계획')
    p = store.create_product_prototype(c)
    store.set_product_prototype_state(p, 'review_requested')
    store.record_product_release_review(p, {k: 'unverified' for k in RELEASE_CHECKS}, '보류')
    plan = store.create_service_operations_plan(p, 'local_desktop_future', '담당자',
                                                '백업 계획', '롤백 계획', '모니터링 계획')
    store.record_service_readiness(plan['id'], {k: 'unverified' for k in OPS_CHECKS}, '')
    return plan['id'], p, c


def make(store, plan):
    return store.create_sales_channel_contract(plan, KINDS[0], '예정 채널', REGIONS[0],
                                               MODES[0], [SCOPES[0], SCOPES[1]],
                                               '수동 카탈로그 매핑 계획', '법적 검토 예정')


def checks():
    return {k: 'unverified' for k in CHECKS}


def test_create_inert_and_scope_canonical(store):
    plan, _, _ = prepared(store)
    row = make(store, plan)
    assert row['state'] == 'DRAFT_DISCONNECTED'
    assert row['planned_scopes'] == sorted([SCOPES[0], SCOPES[1]])
    assert row['event_count'] == 1 and not row['stale_source']
    assert all(not row[k] for k in ('connected','credentials_stored','listing_created',
                                   'orders_received','payments_received'))
    assert store.sales_channel_contract_events(row['id'])[0]['action'] == 'created'


def test_owner_review_never_activates(store):
    plan, _, _ = prepared(store)
    ident = make(store, plan)['id']
    claimed = {k: 'owner_reports_prepared' for k in CHECKS}
    row = store.review_sales_channel_contract(ident, claimed, '관리자 주장')
    assert row['state'] == 'REVIEWED_DISCONNECTED' and not row['connected']
    assert row['latest_checks'] == claimed
    events = store.sales_channel_contract_events(ident)
    assert events[1]['previous_digest'] == events[0]['digest']


def test_retire_terminal(store):
    plan, _, _ = prepared(store)
    ident = make(store, plan)['id']
    assert store.retire_sales_channel_contract(ident, '계획 변경')['state'] == 'RETIRED_DISCONNECTED'
    with pytest.raises(ValueError, match='폐기'):
        store.review_sales_channel_contract(ident, checks(), '')
    with pytest.raises(ValueError, match='이미 폐기'):
        store.retire_sales_channel_contract(ident, '다시')


def test_requires_reviewed_stage70(store):
    b = store.create_business(1, '사업', '목표')
    c = store.create_catalog_item(b, 'service', '초안', '설명', 1000, '계획')
    p = store.create_product_prototype(c)
    store.set_product_prototype_state(p, 'review_requested')
    store.record_product_release_review(p, {k: 'unverified' for k in RELEASE_CHECKS}, '보류')
    plan = store.create_service_operations_plan(p, 'local_desktop_future', '담당자',
                                                '백업', '롤백', '모니터')
    with pytest.raises(ValueError, match='Stage70'):
        make(store, plan['id'])


def test_new_stage70_review_stales_contract(store):
    plan, _, _ = prepared(store)
    ident = make(store, plan)['id']
    store.record_service_readiness(plan, {k: 'unverified' for k in OPS_CHECKS}, '재검토')
    assert store.sales_channel_contract(ident)['stale_source']
    with pytest.raises(ValueError, match='원본 변경'):
        store.review_sales_channel_contract(ident, checks(), '')
    assert store.retire_sales_channel_contract(ident, '원본 변경')['state'] == 'RETIRED_DISCONNECTED'


def test_catalog_revision_stales_contract(store):
    plan, _, c = prepared(store)
    ident = make(store, plan)['id']
    store.revise_catalog_item(c, '변경 설명', 1500, '변경 계획')
    assert store.sales_channel_contract(ident)['stale_source']


def test_release_review_revision_stales_contract(store):
    plan, p, _ = prepared(store)
    ident = make(store, plan)['id']
    store.record_product_release_review(p, {k: 'unverified' for k in RELEASE_CHECKS}, '재검토')
    assert store.sales_channel_contract(ident)['stale_source']


def test_retired_stage70_stales_contract(store):
    plan, _, _ = prepared(store)
    ident = make(store, plan)['id']
    store.retire_service_operations_plan(plan, '중단')
    assert store.sales_channel_contract(ident)['stale_source']


@pytest.mark.parametrize('field,bad', [('kind','live'),('kind',None),('region','US'),
    ('region',None),('mode','live'),('mode','connected'),('mode',None)])
def test_invalid_enums(store, field, bad):
    plan, _, _ = prepared(store)
    data = dict(channel_kind=KINDS[0], region=REGIONS[0], integration_mode=MODES[0])
    data[field if field != 'kind' else 'channel_kind'] = bad
    if field == 'mode': data['integration_mode'] = bad
    with pytest.raises(ValueError):
        store.create_sales_channel_contract(plan, data['channel_kind'], '별칭', data['region'],
                                            data['integration_mode'], [SCOPES[0]], '매핑', '규정')


@pytest.mark.parametrize('bad', [[], ['unknown'], [SCOPES[0],SCOPES[0]],
    None, 1, 'catalog_metadata_future', [True], list(SCOPES)+[SCOPES[0]]])
def test_invalid_scopes(store, bad):
    plan, _, _ = prepared(store)
    with pytest.raises(ValueError, match='권한'):
        store.create_sales_channel_contract(plan, KINDS[0], '별칭', REGIONS[0], MODES[0],
                                            bad, '매핑', '규정')


@pytest.mark.parametrize('bad', ['', ' ', 'x'*81, 'https://example.com',
                                 'owner@example.com', 'api_key=hello', 'password hello',
                                 'Bearer abc', 'sk-abcdefg', None, 123, '\x00'])
def test_disallow_credentials_urls_and_invalid_names(store, bad):
    plan, _, _ = prepared(store)
    with pytest.raises(ValueError, match='별칭'):
        store.create_sales_channel_contract(plan, KINDS[0], bad, REGIONS[0], MODES[0],
                                            [SCOPES[0]], '매핑', '규정')


@pytest.mark.parametrize('bad', ['', ' ', 'x'*501, 'https://store.example.com',
                                 'client_secret=foo', None, 7])
def test_disallow_sensitive_notes(store, bad):
    plan, _, _ = prepared(store)
    with pytest.raises(ValueError, match='계획'):
        store.create_sales_channel_contract(plan, KINDS[0], '별칭', REGIONS[0], MODES[0],
                                            [SCOPES[0]], bad, '규정')


@pytest.mark.parametrize('bad', [None, [], {}, {'other':'unverified'}, 5])
def test_checklist_shape(store, bad):
    plan, _, _ = prepared(store)
    ident = make(store, plan)['id']
    with pytest.raises(ValueError, match='5개'):
        store.review_sales_channel_contract(ident, bad, '')


@pytest.mark.parametrize('bad', ['approved', 'connected', True, 1, None, ''])
def test_checklist_status(store, bad):
    plan, _, _ = prepared(store)
    ident = make(store, plan)['id']
    c = checks(); c[CHECKS[0]] = bad
    with pytest.raises(ValueError, match='상태'):
        store.review_sales_channel_contract(ident, c, '')


def test_no_network_dns_or_external_effect(store):
    plan, _, _ = prepared(store)
    def forbidden(*a, **kw):
        raise AssertionError('network forbidden')
    with patch.object(socket, 'socket', side_effect=forbidden), \
         patch.object(socket, 'getaddrinfo', side_effect=forbidden):
        ident = make(store, plan)['id']
        store.review_sales_channel_contract(ident, checks(), '')
        store.retire_sales_channel_contract(ident, '폐기')
        assert len(store.sales_channel_contracts()) == 1


def test_auth_required(tmp_path):
    s = LocalStore(tmp_path / 'db.sqlite3')
    for fn, args in (
        (s.sales_channel_contracts, ()), (s.sales_channel_contract, (1,)),
        (s.sales_channel_contract_events, (1,)),
        (s.create_sales_channel_contract, (1, KINDS[0], '별칭', REGIONS[0], MODES[0], [SCOPES[0]], '매핑', '규정')),
        (s.review_sales_channel_contract, (1, checks(), '')),
        (s.retire_sales_channel_contract, (1, '폐기')),
    ):
        with pytest.raises((PermissionError, AuthenticationError)):
            fn(*args)


def test_append_only_sqlite_guards(store):
    plan, _, _ = prepared(store)
    make(store, plan)
    with store._connect() as con:
        for table in ('local_sales_channel_contracts', 'local_sales_channel_contract_events'):
            for sql in (f'DELETE FROM {table}', f'UPDATE {table} SET id=id'):
                with pytest.raises(sqlite3.DatabaseError, match='append-only'):
                    con.execute(sql)


def test_tamper_event_detected(store):
    plan, _, _ = prepared(store)
    ident = make(store, plan)['id']
    with store._connect() as con:
        con.execute('DROP TRIGGER local_sales_channel_contract_events_no_update')
        con.execute("UPDATE local_sales_channel_contract_events SET note='changed'")
    with pytest.raises(ValueError, match='해시'):
        store.sales_channel_contract(ident)


def test_tamper_row_detected(store):
    plan, _, _ = prepared(store)
    ident = make(store, plan)['id']
    with store._connect() as con:
        con.execute('DROP TRIGGER local_sales_channel_contracts_no_update')
        con.execute("UPDATE local_sales_channel_contracts SET mapping_note='changed'")
    with pytest.raises(ValueError, match='해시'):
        store.sales_channel_contract(ident)


def test_tamper_revision_detected(store):
    plan, _, _ = prepared(store)
    ident = make(store, plan)['id']
    with store._connect() as con:
        con.execute('DROP TRIGGER local_sales_channel_contract_events_no_update')
        con.execute('UPDATE local_sales_channel_contract_events SET revision=8')
    with pytest.raises(ValueError, match='연속성'):
        store.sales_channel_contract_events(ident)


def test_tamper_source_detected(store):
    plan, p, _ = prepared(store)
    ident = make(store, plan)['id']
    Path(store.product_prototype(p)['artifact_path']).write_bytes(b'tamper')
    with pytest.raises(ValueError, match='크기'):
        store.sales_channel_contract(ident)


def test_persistence_after_reopen(store):
    plan, _, _ = prepared(store)
    ident = make(store, plan)['id']
    store.review_sales_channel_contract(ident, checks(), '')
    other = LocalStore(store.path)
    other.login('owner71', 'stage71-long-password')
    assert other.sales_channel_contract(ident)['event_count'] == 2


def test_list_limit_and_separation(store):
    plan, _, _ = prepared(store)
    first = make(store, plan)
    second = make(store, plan)
    assert [r['id'] for r in store.sales_channel_contracts(limit=1)] == [second['id']]
    assert len(store.sales_channel_contracts()) == 2
    assert len(store.sales_channel_contract_events(first['id'])) == 1
    for bad in (0, 201, True, None):
        with pytest.raises(ValueError, match='조회'):
            store.sales_channel_contracts(limit=bad)
