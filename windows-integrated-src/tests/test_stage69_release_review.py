"""Stage69 release is always blocked; only local owner checklist claims are stored."""
from pathlib import Path
import socket
import sqlite3
from unittest.mock import patch

import pytest

from desktop.storage import LocalStore, AuthenticationError
from desktop.product_release_review import CHECKS, ANSWERS, DECISIONS


@pytest.fixture
def store(tmp_path):
    s = LocalStore(tmp_path / 'owner.sqlite3')
    s.setup_owner('owner69', 'stage69-long-password')
    return s


def ready(store):
    b = store.create_business(1, '사업', '목표')
    c = store.create_catalog_item(b, 'product', '상품', '가정', 1000, '계획')
    p = store.create_product_prototype(c)
    store.set_product_prototype_state(p, 'review_requested')
    return p, c


def checks():
    return {k: 'unverified' for k in CHECKS}


def test_initial_summary_no_release(store):
    p, _ = ready(store)
    s = store.product_release_review_summary(p)
    assert s['review_count'] == 0 and s['decision'] == 'HOLD_NO_RELEASE'
    assert s['artifact_integrity_checked'] is True
    assert not s['release_approved'] and not s['quality_verified']
    assert not s['deployment_performed'] and not s['sales_performed']


def test_record_and_append_history(store):
    p, _ = ready(store)
    c = checks(); c['description_matches_intent'] = 'owner_reports_checked'
    first = store.record_product_release_review(p, c, '자체 확인 주장')
    second = store.record_product_release_review(p, checks(), '보류', 'REJECTED_NO_RELEASE')
    assert first['revision'] == 1 and second['revision'] == 2
    assert second['previous_digest'] == first['digest']
    assert len(store.product_release_review_history(p)) == 2
    assert store.product_release_review_summary(p)['decision'] == 'REJECTED_NO_RELEASE'
    assert not second['quality_verified'] and not second['release_approved']


@pytest.mark.parametrize('state', ('prototype', 'withdrawn'))
def test_review_requires_requested(store, state):
    b = store.create_business(1, '사업', '목표')
    c = store.create_catalog_item(b, 'product', '상품', '설명', 0, '계획')
    p = store.create_product_prototype(c)
    if state == 'withdrawn':
        store.set_product_prototype_state(p, 'withdrawn')
    with pytest.raises(ValueError, match='검토 요청'):
        store.record_product_release_review(p, checks(), '')


def test_catalog_changed_blocks_new_record(store):
    p, c = ready(store)
    store.revise_catalog_item(c, '변경', 2000, '계획')
    with pytest.raises(ValueError, match='카탈로그'):
        store.record_product_release_review(p, checks(), '')
    assert store.product_release_review_summary(p)['catalog_changed_since_build']


def test_existing_history_still_readable_after_catalog_edit(store):
    p, c = ready(store)
    store.record_product_release_review(p, checks(), '')
    store.revise_catalog_item(c, '변경', 2000, '계획')
    assert len(store.product_release_review_history(p)) == 1


@pytest.mark.parametrize('decision', ('approved', 'RELEASED', 'DEPLOY', '', None, 12))
def test_no_approval_decisions(store, decision):
    p, _ = ready(store)
    with pytest.raises(ValueError, match='출시'):
        store.record_product_release_review(p, checks(), '', decision)


@pytest.mark.parametrize('bad', [None, [], {}, {'x': 'unverified'}, 123])
def test_invalid_checklist_structure(store, bad):
    p, _ = ready(store)
    with pytest.raises(ValueError, match='항목'):
        store.record_product_release_review(p, bad, '')


@pytest.mark.parametrize('bad', ['passed', 'approved', 'verified', '', 0, True])
def test_invalid_checklist_answer(store, bad):
    p, _ = ready(store)
    c = checks(); c[CHECKS[0]] = bad
    with pytest.raises(ValueError, match='검수 상태'):
        store.record_product_release_review(p, c, '')


@pytest.mark.parametrize('note', [None, 5, 'x'*1001])
def test_note_limits(store, note):
    p, _ = ready(store)
    with pytest.raises(ValueError, match='메모'):
        store.record_product_release_review(p, checks(), note)


def test_sqlite_append_only_guards(store):
    p, _ = ready(store)
    store.record_product_release_review(p, checks(), '')
    with store._connect() as con:
        for sql in ('DELETE FROM local_product_release_reviews',
                    "UPDATE local_product_release_reviews SET decision='REJECTED_NO_RELEASE'"):
            with pytest.raises(sqlite3.DatabaseError, match='append-only'):
                con.execute(sql)


def test_tamper_digest_detection(store):
    p, _ = ready(store)
    store.record_product_release_review(p, checks(), '')
    with store._connect() as con:
        con.execute('DROP TRIGGER local_release_reviews_no_update')
        con.execute("UPDATE local_product_release_reviews SET reviewer_note='changed'")
    with pytest.raises(ValueError, match='해시'):
        store.product_release_review_history(p)


def test_tamper_checklist_detection(store):
    p, _ = ready(store)
    store.record_product_release_review(p, checks(), '')
    with store._connect() as con:
        con.execute('DROP TRIGGER local_release_reviews_no_update')
        con.execute("UPDATE local_product_release_reviews SET checklist_json='{}'")
    with pytest.raises(ValueError, match='체크리스트'):
        store.product_release_review_history(p)


def test_tamper_revision_detection(store):
    p, _ = ready(store)
    store.record_product_release_review(p, checks(), '')
    with store._connect() as con:
        con.execute('DROP TRIGGER local_release_reviews_no_update')
        con.execute('UPDATE local_product_release_reviews SET revision=3')
    with pytest.raises(ValueError, match='연속성'):
        store.product_release_review_history(p)


def test_artifact_tamper_prevents_review(store):
    p, _ = ready(store)
    artifact = Path(store.product_prototype(p)['artifact_path'])
    artifact.write_bytes(b'bad')
    with pytest.raises(ValueError, match='크기'):
        store.record_product_release_review(p, checks(), '')


def test_owner_permission_required(tmp_path):
    s = LocalStore(tmp_path / 'db.sqlite3')
    with pytest.raises((PermissionError, AuthenticationError)):
        s.product_release_review_summary(1)
    with pytest.raises((PermissionError, AuthenticationError)):
        s.record_product_release_review(1, checks(), '')
    with pytest.raises((PermissionError, AuthenticationError)):
        s.product_release_review_history(1)


def test_no_network_on_record(store):
    p, _ = ready(store)
    def forbidden(*args, **kwargs):
        raise AssertionError('network forbidden')
    with patch.object(socket, 'socket', side_effect=forbidden), \
         patch.object(socket, 'getaddrinfo', side_effect=forbidden):
        store.record_product_release_review(p, checks(), '')
        assert store.product_release_review_summary(p)['review_count'] == 1


def test_checklist_has_only_self_reported_states():
    assert len(CHECKS) == 6
    assert set(ANSWERS) == {'unverified','needs_work','owner_reports_checked'}
    assert set(DECISIONS) == {'HOLD_NO_RELEASE','REJECTED_NO_RELEASE'}


def test_all_six_owner_claims_never_approve_release(store):
    p, _ = ready(store)
    claims = {k: 'owner_reports_checked' for k in CHECKS}
    store.record_product_release_review(p, claims, '관리자 주장')
    result = store.product_release_review_summary(p)
    assert result['decision'] == 'HOLD_NO_RELEASE'
    assert result['release_approved'] is False
    assert result['quality_verified'] is False
    assert result['deployment_performed'] is False


def test_history_persists_on_reopen(store):
    p, _ = ready(store)
    first = store.record_product_release_review(p, checks(), '')
    reopened = LocalStore(store.path)
    reopened.login('owner69', 'stage69-long-password')
    assert reopened.product_release_review_history(p)[0]['digest'] == first['digest']


def test_reviews_isolated_by_prototype(store):
    p1, c = ready(store)
    p2 = store.create_product_prototype(c)
    store.set_product_prototype_state(p2, 'review_requested')
    store.record_product_release_review(p1, checks(), '')
    assert store.product_release_review_history(p2) == []
    assert store.product_release_review_summary(p2)['review_count'] == 0


def test_withdrawal_prevents_new_review_but_preserves_history(store):
    p, _ = ready(store)
    store.record_product_release_review(p, checks(), '')
    store.set_product_prototype_state(p, 'withdrawn')
    assert len(store.product_release_review_history(p)) == 1
    with pytest.raises(ValueError, match='검토 요청'):
        store.record_product_release_review(p, checks(), '')
