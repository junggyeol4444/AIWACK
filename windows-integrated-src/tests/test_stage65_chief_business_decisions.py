"""Stage65: offline review briefs, no actual chief AI or business execution."""
from __future__ import annotations

import socket
import sqlite3
from unittest.mock import patch

import pytest

from desktop.chief_business_decisions import build_snapshot
from desktop.storage import LocalStore


@pytest.fixture
def store(tmp_path):
    store = LocalStore(tmp_path / 'stage65.sqlite3')
    store.setup_owner('owner65', 'stage65-strong-password')
    return store


@pytest.fixture
def assumptions():
    return {'unit_price_krw': 10000, 'monthly_units': 10, 'unit_cost_krw': 3000,
            'monthly_fixed_krw': 20000, 'monthly_marketing_krw': 10000,
            'setup_cost_krw': 50000, 'refund_bps': 0, 'payment_fee_bps': 300, 'months': 6}


def evaluations(store, assumptions, n=2):
    result = []
    for i in range(n):
        cid = store.generate_business_candidates('고객'+str(i), '문제'+str(i), 1)['created_ids'][0]
        params = {**assumptions, 'monthly_units': 10+i}
        result.append(store.evaluate_financial_scenario('candidate', cid, params, '수동 가정'))
    return result


def test_create_compare_no_execution(store, assumptions):
    ids = evaluations(store, assumptions)
    brief = store.create_chief_business_brief(ids, '관리자 검토')
    item = store.chief_business_brief(brief)
    snap = item['snapshot']
    assert snap['comparison_count'] == 2
    assert [r['evaluation_id'] for r in snap['items']] == list(reversed(ids))
    assert snap['execution_decision'] == 'HOLD_NO_EXECUTION'
    assert snap['chief_ai_inference_performed'] is False
    assert snap['external_actions_executed'] is False
    assert snap['market_demand_verified'] is False
    assert item['review_status'] == 'pending'
    assert all(row['state'] == 'draft' for row in store.business_candidates())
    assert store.list_businesses() == []


def test_review_is_not_execution_permission(store, assumptions):
    brief = store.create_chief_business_brief(evaluations(store, assumptions), '검토만')
    assert store.review_chief_business_brief(brief, 'acknowledged')['review_status'] == 'acknowledged'
    assert store.chief_business_brief(brief)['external_actions_executed'] is False
    with pytest.raises(ValueError):
        store.review_chief_business_brief(brief, 'acknowledged')
    with pytest.raises(ValueError):
        store.review_chief_business_brief(brief, 'approved')
    assert all(r['state'] == 'draft' for r in store.business_candidates())


def test_reject_and_reopen(store, assumptions):
    brief = store.create_chief_business_brief(evaluations(store, assumptions), '검토만')
    store.review_chief_business_brief(brief, 'rejected')
    reopened = LocalStore(store.path)
    reopened.login('owner65', 'stage65-strong-password')
    assert reopened.chief_business_brief(brief)['review_status'] == 'rejected'
    assert len(reopened.chief_business_brief_history()) == 1


@pytest.mark.parametrize('bad', [[], [0], [True], ['1'], [1,1], list(range(1,12)), 1, None])
def test_invalid_ids_rejected(store, bad):
    with pytest.raises(ValueError):
        store.create_chief_business_brief(bad, '검토만')
    assert store.chief_business_brief_history() == []


@pytest.mark.parametrize('bad', ['', 'password=foo', 'x\nline', 'x'*301])
def test_invalid_notes_rejected(store, assumptions, bad):
    with pytest.raises(ValueError):
        store.create_chief_business_brief(evaluations(store, assumptions), bad)


def test_unknown_and_duplicate_subject(store, assumptions):
    ids = evaluations(store, assumptions)
    with pytest.raises(ValueError):
        store.create_chief_business_brief([ids[0], 99999], '검토만')
    cid = store.financial_scenario_report(ids[0])['subject_id']
    second = store.evaluate_financial_scenario('candidate', cid, assumptions, '재가정')
    with pytest.raises(ValueError, match='중복 평가'):
        store.create_chief_business_brief([ids[0], second], '검토만')


def test_mismatched_horizons_rejected(store, assumptions):
    ids = evaluations(store, assumptions, 1)
    cid = store.generate_business_candidates('별도 고객', '별도 문제', 1)['created_ids'][0]
    other = store.evaluate_financial_scenario('candidate', cid, {**assumptions, 'months': 12}, '수동 가정')
    with pytest.raises(ValueError, match='기간'):
        store.create_chief_business_brief(ids+[other], '검토만')


def test_immutable_audit_and_tamper_detection(store, assumptions):
    brief = store.create_chief_business_brief(evaluations(store, assumptions), '검토만')
    with store._connect() as con:
        for statement in ('DELETE FROM chief_business_briefs',
                          "UPDATE chief_business_briefs SET owner_note='x'",
                          'DELETE FROM chief_business_brief_events',
                          "UPDATE chief_business_brief_events SET action='rejected'"):
            with pytest.raises(sqlite3.DatabaseError):
                con.execute(statement)
        con.execute('DROP TRIGGER chief_business_brief_events_no_update')
        con.execute("UPDATE chief_business_brief_events SET action='rejected'")
    with pytest.raises(ValueError, match='감사'):
        store.chief_business_brief(brief)


def test_snapshot_tamper_detection(store, assumptions):
    brief = store.create_chief_business_brief(evaluations(store, assumptions), '검토만')
    with store._connect() as con:
        con.execute('DROP TRIGGER chief_business_briefs_no_update')
        con.execute("UPDATE chief_business_briefs SET snapshot_json='{}'")
    with pytest.raises(ValueError, match='무결성'):
        store.chief_business_brief(brief)


def test_event_failure_rolls_back(store, assumptions):
    ids = evaluations(store, assumptions)
    with store._connect() as con:
        con.execute('''CREATE TRIGGER fail65 BEFORE INSERT ON chief_business_brief_events
                       BEGIN SELECT RAISE(ABORT, 'forced'); END''')
    with pytest.raises(sqlite3.DatabaseError):
        store.create_chief_business_brief(ids, '검토만')
    assert store.chief_business_brief_history() == []


def test_logout_and_no_network(store, assumptions):
    ids = evaluations(store, assumptions)
    def blocked(*args, **kwargs):
        raise AssertionError('network access forbidden')
    with patch.object(socket, 'socket', side_effect=blocked), patch.object(socket, 'getaddrinfo', side_effect=blocked):
        brief = store.create_chief_business_brief(ids, '검토만')
        assert store.chief_business_brief(brief)['snapshot']['execution_decision'] == 'HOLD_NO_EXECUTION'
        assert store.review_chief_business_brief(brief, 'rejected')['review_status'] == 'rejected'
    store.logout()
    for action in (lambda: store.create_chief_business_brief(ids, '검토만'),
                   lambda: store.chief_business_brief(brief),
                   lambda: store.review_chief_business_brief(brief, 'acknowledged'),
                   lambda: store.chief_business_brief_history()):
        with pytest.raises(PermissionError):
            action()


def test_invalid_lookup_and_limits(store, assumptions):
    ids = evaluations(store, assumptions)
    brief = store.create_chief_business_brief(ids, '검토만')
    for value in (0, -1, True, '1', 99999):
        with pytest.raises(ValueError):
            store.chief_business_brief(value)
    for value in (0, True, 101, '2'):
        with pytest.raises(ValueError):
            store.chief_business_brief_history(value)
    assert store.chief_business_brief(brief)['snapshot']['months'] == 6
