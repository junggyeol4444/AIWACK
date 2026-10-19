"""Stage70 offline service operations plans are never real deployments."""
from pathlib import Path
import socket
import sqlite3
from unittest.mock import patch

import pytest

from desktop.storage import LocalStore, AuthenticationError
from desktop.product_release_review import CHECKS as RELEASE_CHECKS
from desktop.service_operations_plan import CHECKS, ANSWERS, ENVIRONMENTS


@pytest.fixture
def store(tmp_path):
    s = LocalStore(tmp_path / 'owner.sqlite3')
    s.setup_owner('owner70', 'stage70-long-password')
    return s


def ready(store):
    b = store.create_business(1, '사업', '목표')
    c = store.create_catalog_item(b, 'service', '서비스 초안', '설명', 3000, '제공 계획')
    p = store.create_product_prototype(c)
    store.set_product_prototype_state(p, 'review_requested')
    store.record_product_release_review(p, {k: 'unverified' for k in RELEASE_CHECKS}, '보류')
    return p, c


def make(store, p):
    return store.create_service_operations_plan(
        p, 'local_desktop_future', '담당자 계획', '백업/복원 검토', '롤백 절차 초안', '모니터링 초안')


def checks():
    return {k: 'unverified' for k in CHECKS}


def test_create_and_never_deploy(store):
    p, _ = ready(store)
    row = make(store, p)
    assert row['state'] == 'DRAFT_NO_DEPLOY'
    assert row['event_count'] == 1
    assert not row['deployment_performed'] and not row['service_running']
    assert not row['release_approved'] and not row['sales_performed']
    assert not row['stale_source']
    assert store.service_operations_events(row['id'])[0]['action'] == 'created'


def test_readiness_owner_claim_only(store):
    p, _ = ready(store)
    plan = make(store, p)
    c = {k: 'owner_reports_prepared' for k in CHECKS}
    row = store.record_service_readiness(plan['id'], c, '관리자 주장')
    assert row['state'] == 'REVIEWED_NO_DEPLOY'
    assert row['latest_checklist'] == c
    assert not row['deployment_performed']
    events = store.service_operations_events(plan['id'])
    assert events[1]['previous_digest'] == events[0]['digest']


def test_retire_is_terminal(store):
    p, _ = ready(store)
    ident = make(store, p)['id']
    row = store.retire_service_operations_plan(ident, '계획 변경')
    assert row['state'] == 'RETIRED_NO_DEPLOY'
    with pytest.raises(ValueError, match='폐기'):
        store.record_service_readiness(ident, checks(), '')
    with pytest.raises(ValueError, match='이미 폐기'):
        store.retire_service_operations_plan(ident, '재시도')
    assert len(store.service_operations_events(ident)) == 2


def test_source_requires_stage69_review(store):
    b = store.create_business(1, '사업', '목표')
    c = store.create_catalog_item(b, 'product', '제품', '설명', 0, '제공')
    p = store.create_product_prototype(c)
    store.set_product_prototype_state(p, 'review_requested')
    with pytest.raises(ValueError, match='Stage69'):
        make(store, p)


@pytest.mark.parametrize('state', ('prototype', 'withdrawn'))
def test_source_requires_review_requested(store, state):
    b = store.create_business(1, '사업', '목표')
    c = store.create_catalog_item(b, 'product', '제품', '설명', 0, '제공')
    p = store.create_product_prototype(c)
    if state == 'withdrawn':
        store.set_product_prototype_state(p, 'withdrawn')
    with pytest.raises(ValueError, match='검토 요청'):
        make(store, p)


def test_catalog_edit_blocks_new_plan(store):
    p, c = ready(store)
    store.revise_catalog_item(c, '새 설명', 500, '계획')
    with pytest.raises(ValueError, match='카탈로그'):
        make(store, p)


def test_catalog_edit_stales_existing_plan(store):
    p, c = ready(store)
    ident = make(store, p)['id']
    store.revise_catalog_item(c, '새 설명', 500, '계획')
    assert store.service_operations_plan(ident)['stale_source']
    with pytest.raises(ValueError, match='원본 변경'):
        store.record_service_readiness(ident, checks(), '')
    assert store.retire_service_operations_plan(ident, '원본 변경')['state'] == 'RETIRED_NO_DEPLOY'


def test_new_release_review_stales_plan(store):
    p, _ = ready(store)
    ident = make(store, p)['id']
    store.record_product_release_review(p, {k: 'unverified' for k in RELEASE_CHECKS}, '추가 검토')
    assert store.service_operations_plan(ident)['stale_source']
    with pytest.raises(ValueError, match='원본 변경'):
        store.record_service_readiness(ident, checks(), '')


def test_withdrawal_stales_plan(store):
    p, _ = ready(store)
    ident = make(store, p)['id']
    store.set_product_prototype_state(p, 'withdrawn')
    assert store.service_operations_plan(ident)['stale_source']


@pytest.mark.parametrize('bad', ('live', 'approved', 'deploy', '', None, 1))
def test_environment_restricted(store, bad):
    p, _ = ready(store)
    with pytest.raises(ValueError, match='환경'):
        store.create_service_operations_plan(p, bad, 'a', 'b', 'c', 'd')


@pytest.mark.parametrize('bad', ('', ' ', 'x'*501, None, 5, '\x00'))
def test_plan_text_validated(store, bad):
    p, _ = ready(store)
    with pytest.raises(ValueError, match='계획'):
        store.create_service_operations_plan(p, ENVIRONMENTS[0], bad, 'backup', 'rollback', 'monitor')


@pytest.mark.parametrize('bad', (None, [], {}, {'other': 'unverified'}, 5))
def test_bad_checklist_shape(store, bad):
    p, _ = ready(store)
    ident = make(store, p)['id']
    with pytest.raises(ValueError, match='5개'):
        store.record_service_readiness(ident, bad, '')


@pytest.mark.parametrize('bad', ('passed', 'approved', 'deployed', True, 1, ''))
def test_bad_checklist_answer(store, bad):
    p, _ = ready(store)
    ident = make(store, p)['id']
    c = checks(); c[CHECKS[0]] = bad
    with pytest.raises(ValueError, match='상태'):
        store.record_service_readiness(ident, c, '')


def test_no_implicit_network(store):
    p, _ = ready(store)
    def forbidden(*args, **kwargs):
        raise AssertionError('network forbidden')
    with patch.object(socket, 'socket', side_effect=forbidden), \
         patch.object(socket, 'getaddrinfo', side_effect=forbidden):
        plan = make(store, p)
        store.record_service_readiness(plan['id'], checks(), '')
        assert len(store.service_operations_plans()) == 1


def test_auth_required(tmp_path):
    s = LocalStore(tmp_path / 'db.sqlite3')
    with pytest.raises((PermissionError, AuthenticationError)):
        s.service_operations_plans()
    with pytest.raises((PermissionError, AuthenticationError)):
        s.create_service_operations_plan(1, ENVIRONMENTS[0], 'a', 'b', 'c', 'd')
    with pytest.raises((PermissionError, AuthenticationError)):
        s.record_service_readiness(1, checks(), '')
    with pytest.raises((PermissionError, AuthenticationError)):
        s.retire_service_operations_plan(1, 'reason')


def test_append_only_sqlite_guards(store):
    p, _ = ready(store)
    ident = make(store, p)['id']
    with store._connect() as con:
        for table in ('local_service_operations_plans', 'local_service_operations_events'):
            for statement in (f'DELETE FROM {table}', f'UPDATE {table} SET id=id'):
                with pytest.raises(sqlite3.DatabaseError, match='append-only'):
                    con.execute(statement)


def test_tamper_event_digest_detected(store):
    p, _ = ready(store)
    ident = make(store, p)['id']
    with store._connect() as con:
        con.execute('DROP TRIGGER local_service_operations_events_no_update')
        con.execute("UPDATE local_service_operations_events SET note='tampered'")
    with pytest.raises(ValueError, match='해시'):
        store.service_operations_plan(ident)


def test_tamper_plan_note_detected(store):
    p, _ = ready(store)
    ident = make(store, p)['id']
    with store._connect() as con:
        con.execute('DROP TRIGGER local_service_operations_plans_no_update')
        con.execute("UPDATE local_service_operations_plans SET monitoring_plan='tampered'")
    with pytest.raises(ValueError, match='해시'):
        store.service_operations_plan(ident)


def test_tamper_revision_detected(store):
    p, _ = ready(store)
    ident = make(store, p)['id']
    with store._connect() as con:
        con.execute('DROP TRIGGER local_service_operations_events_no_update')
        con.execute('UPDATE local_service_operations_events SET revision=8')
    with pytest.raises(ValueError, match='연속성'):
        store.service_operations_events(ident)


def test_tamper_artifact_detected(store):
    p, _ = ready(store)
    ident = make(store, p)['id']
    Path(store.product_prototype(p)['artifact_path']).write_bytes(b'tamper')
    with pytest.raises(ValueError, match='크기'):
        store.service_operations_plan(ident)


def test_persistence_after_reopen(store):
    p, _ = ready(store)
    ident = make(store, p)['id']
    store.record_service_readiness(ident, checks(), '수동')
    other = LocalStore(store.path)
    other.login('owner70', 'stage70-long-password')
    assert other.service_operations_plan(ident)['event_count'] == 2


def test_list_limit_and_separation(store):
    p, _ = ready(store)
    one = make(store, p)
    two = make(store, p)
    assert [r['id'] for r in store.service_operations_plans()] == [two['id'], one['id']]
    assert len(store.service_operations_plans(1)) == 1
    for bad in (0, 201, '1', True):
        with pytest.raises(ValueError, match='조회'):
            store.service_operations_plans(bad)


def test_no_release_or_deploy_methods(store):
    assert not hasattr(store, 'deploy_service')
    assert not hasattr(store, 'approve_service_release')
    assert set(ANSWERS) == {'unverified','needs_work','owner_reports_prepared'}
    assert set(CHECKS) == {'operator_assigned','backup_restore_plan','rollback_plan',
                           'health_monitoring_plan','incident_response_plan'}
