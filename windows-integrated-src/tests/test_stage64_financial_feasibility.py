"""Stage64: offline, owner-entered what-if arithmetic; no actual sales."""
from pathlib import Path
import socket
import sqlite3
from unittest.mock import patch

import pytest

from desktop.storage import LocalStore
from desktop.financial_feasibility import calculate, BREAK_EVEN_CAP


@pytest.fixture
def store(tmp_path):
    s = LocalStore(tmp_path / 'owner64.sqlite3')
    s.setup_owner('owner64', 'long-password-for-stage64')
    return s


@pytest.fixture
def assumption():
    return {'unit_price_krw': 10_000, 'monthly_units': 10,
            'unit_cost_krw': 3_000, 'monthly_fixed_krw': 20_000,
            'monthly_marketing_krw': 10_000, 'setup_cost_krw': 50_000,
            'refund_bps': 0, 'payment_fee_bps': 300, 'months': 6}


def candidate(store):
    return store.generate_business_candidates('고객', '문제', 1)['created_ids'][0]


def test_exact_scenario_and_break_even(assumption):
    result = calculate(assumption)
    low = result['scenarios']['downside_25pct_units']
    base = result['scenarios']['base_owner_assumption']
    high = result['scenarios']['upside_25pct_units']
    assert (low['units'], base['units'], high['units']) == (7, 10, 13)
    assert base['gross_assumed_krw'] == 100_000
    assert base['payment_fees_assumed_krw'] == 3_000
    assert base['monthly_net_assumed_krw'] == 37_000
    assert (low['horizon_net_after_setup_assumed_krw'],
            base['horizon_net_after_setup_assumed_krw'],
            high['horizon_net_after_setup_assumed_krw']) == (51_400, 172_000, 292_600)
    assert result['break_even_monthly_units_assumed'] == 6
    assert result['actual_revenue_krw'] is None
    assert result['actual_profit_krw'] is None
    assert result['sales_verified'] is False
    assert result['external_actions_executed'] is False


def test_zero_margin_and_no_break_even(assumption):
    assumption.update(unit_price_krw=0, unit_cost_krw=0)
    result = calculate(assumption)
    assert result['break_even_monthly_units_assumed'] is None
    assert result['scenarios']['base_owner_assumption']['horizon_net_after_setup_assumed_krw'] < 0
    assumption.update(monthly_fixed_krw=0, monthly_marketing_krw=0, setup_cost_krw=0)
    assert calculate(assumption)['break_even_monthly_units_assumed'] == 0


def test_refunds_and_fees_are_integer_rounding(assumption):
    assumption.update(unit_price_krw=101, monthly_units=1, refund_bps=1000,
                      payment_fee_bps=500, unit_cost_krw=0, monthly_fixed_krw=0,
                      monthly_marketing_krw=0, setup_cost_krw=0, months=1)
    result = calculate(assumption)['scenarios']['base_owner_assumption']
    assert result['refunds_assumed_krw'] == 10
    assert result['payment_fees_assumed_krw'] == 5
    assert result['monthly_net_assumed_krw'] == 86


@pytest.mark.parametrize('field,value', [
    ('unit_price_krw', -1), ('unit_price_krw', True), ('unit_price_krw', '100'),
    ('unit_price_krw', 1_000_000_000_001), ('monthly_units', 1_000_001),
    ('monthly_units', 2.0), ('monthly_fixed_krw', -1), ('months', 0),
    ('months', 121), ('months', True), ('refund_bps', 10_001),
    ('payment_fee_bps', -1),
])
def test_invalid_numbers_rejected(assumption, field, value):
    assumption[field] = value
    with pytest.raises(ValueError):
        calculate(assumption)


def test_missing_extra_fields_and_bad_rate_sum(assumption):
    del assumption['months']
    with pytest.raises(ValueError):
        calculate(assumption)
    assumption['months'] = 6
    assumption['extra'] = 0
    with pytest.raises(ValueError):
        calculate(assumption)
    del assumption['extra']
    assumption.update(refund_bps=6000, payment_fee_bps=5000)
    with pytest.raises(ValueError, match='100%'):
        calculate(assumption)


def test_candidate_persistence_and_no_real_revenue(store, assumption):
    cid = candidate(store)
    ident = store.evaluate_financial_scenario('candidate', cid, assumption, '수동 가정')
    report = store.financial_scenario_report(ident)
    assert report['subject_kind'] == 'candidate' and report['subject_id'] == cid
    assert report['assumptions'] == assumption
    assert len(store.financial_scenario_history('candidate', cid)) == 1
    reopened = LocalStore(store.path)
    reopened.login('owner64', 'long-password-for-stage64')
    assert reopened.financial_scenario_report(ident) == report
    assert reopened.list_businesses() == []
    assert reopened.business_candidates()[0]['state'] == 'draft'
    assert reopened.financial_scenario_report(ident)['result']['market_demand_verified'] is False


def test_existing_business_persistence(store, assumption):
    b = store.create_business(1, '가상 서비스', '가정 검토', 20_000)
    ident = store.evaluate_financial_scenario('business', b, assumption, '수동 예산 가정')
    assert store.financial_scenario_report(ident)['subject_kind'] == 'business'
    assert store.financial_scenario_history('business', b)[0]['id'] == ident
    assert store.list_businesses()[0]['budget_krw'] == 20_000


@pytest.mark.parametrize('kind,ident', [
    ('unknown', 1), ('candidate', 0), ('candidate', -1), ('candidate', True),
    ('candidate', '1'), ('business', 999_999), ('candidate', 999_999),
])
def test_invalid_subject_does_not_insert(store, assumption, kind, ident):
    with pytest.raises(ValueError):
        store.evaluate_financial_scenario(kind, ident, assumption, '수동 가정')
    with store._connect() as con:
        assert con.execute('SELECT COUNT(*) FROM financial_assumption_evaluations').fetchone()[0] == 0


@pytest.mark.parametrize('note', ['', 'password=abc', 'a\nsecret', 'x'*201])
def test_invalid_notes_rejected(store, assumption, note):
    with pytest.raises(ValueError):
        store.evaluate_financial_scenario('candidate', candidate(store), assumption, note)


def test_logout_denies_all_operations(store, assumption):
    cid = candidate(store)
    ident = store.evaluate_financial_scenario('candidate', cid, assumption, '수동 가정')
    store.logout()
    for fn in (lambda: store.evaluate_financial_scenario('candidate', cid, assumption, '수동 가정'),
               lambda: store.financial_scenario_report(ident),
               lambda: store.financial_scenario_history('candidate', cid)):
        with pytest.raises(PermissionError):
            fn()


def test_append_only_and_detects_audit_tampering(store, assumption):
    ident = store.evaluate_financial_scenario('candidate', candidate(store), assumption, '수동 가정')
    with store._connect() as con:
        for query in ('DELETE FROM financial_assumption_evaluations',
                      'UPDATE financial_assumption_evaluations SET monthly_units=900',
                      'DELETE FROM financial_assumption_events',
                      "UPDATE financial_assumption_events SET detail='{}'"):
            with pytest.raises(sqlite3.DatabaseError):
                con.execute(query)
        con.execute('DROP TRIGGER financial_assumption_events_no_update')
        con.execute("UPDATE financial_assumption_events SET detail='{}'")
    with pytest.raises(ValueError, match='감사'):
        store.financial_scenario_report(ident)


def test_input_and_result_tamper_detection(store, assumption):
    ident = store.evaluate_financial_scenario('candidate', candidate(store), assumption, '수동 가정')
    with store._connect() as con:
        con.execute('DROP TRIGGER financial_assumption_evaluations_no_update')
        con.execute('UPDATE financial_assumption_evaluations SET monthly_units=100 WHERE id=?', (ident,))
    with pytest.raises(ValueError, match='입력 무결성'):
        store.financial_scenario_report(ident)


def test_atomic_rollback_when_event_insert_fails(store, assumption):
    cid = candidate(store)
    with store._connect() as con:
        con.execute('''CREATE TRIGGER fail_financial_event BEFORE INSERT ON financial_assumption_events
          BEGIN SELECT RAISE(ABORT,'forced'); END''')
    with pytest.raises(sqlite3.DatabaseError):
        store.evaluate_financial_scenario('candidate', cid, assumption, '수동 가정')
    assert store.financial_scenario_history('candidate', cid) == []


def test_no_network_and_no_business_state_change(store, assumption):
    cid = candidate(store)
    def forbidden(*args, **kwargs):
        raise AssertionError('No socket or DNS allowed')
    with patch.object(socket, 'socket', side_effect=forbidden), \
         patch.object(socket, 'getaddrinfo', side_effect=forbidden):
        ident = store.evaluate_financial_scenario('candidate', cid, assumption, '수동 가정')
        assert store.financial_scenario_report(ident)['result']['sales_verified'] is False
    assert store.business_candidates()[0]['state'] == 'draft'
    assert store.list_businesses() == []


def test_no_unbounded_history_or_invalid_lookup(store, assumption):
    cid = candidate(store)
    for invalid in (0, 101, True, '2'):
        with pytest.raises(ValueError):
            store.financial_scenario_history('candidate', cid, invalid)
    with pytest.raises(ValueError):
        store.financial_scenario_history('candidate', 999_999)
    with pytest.raises(ValueError):
        store.financial_scenario_report(999_999)
    assert BREAK_EVEN_CAP == 1_000_000_000


def test_combined_rounding_keeps_break_even_monotonic(assumption):
    # Independent rounding of refunds and fees can make adjacent-unit proceeds
    # go backwards. Combined rounding keeps the binary-search predicate valid.
    assumption.update(unit_price_krw=1, unit_cost_krw=0, monthly_units=5,
                      refund_bps=1000, payment_fee_bps=1000,
                      monthly_fixed_krw=0, monthly_marketing_krw=0,
                      setup_cost_krw=5, months=1)
    result = calculate(assumption)
    assert result['break_even_monthly_units_assumed'] == 6
    assert result['scenarios']['base_owner_assumption']['horizon_net_after_setup_assumed_krw'] == -1


def test_extreme_valid_values_use_exact_integers(assumption):
    assumption.update(unit_price_krw=1_000_000_000_000, monthly_units=1_000_000,
                      unit_cost_krw=0, monthly_fixed_krw=0, monthly_marketing_krw=0,
                      setup_cost_krw=0, refund_bps=0, payment_fee_bps=0, months=120)
    result = calculate(assumption)
    assert result['scenarios']['base_owner_assumption']['horizon_net_after_setup_assumed_krw'] == 120_000_000_000_000_000_000
    assert result['break_even_monthly_units_assumed'] == 0
