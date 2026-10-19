"""Stage77 local-only subscription/refund simulation: never a provider transaction."""
import sqlite3
from concurrent.futures import ThreadPoolExecutor

import pytest

from desktop.offline_order_simulations import initialize as init_orders
from desktop.offline_subscription_refund import (
    initialize, create, transition, get, history, MODES,
)
from desktop.storage import LocalStore, AuthenticationError
from test_stage73_simulated_orders import prepared


def db():
    con = sqlite3.connect(':memory:')
    con.execute('PRAGMA foreign_keys=OFF')  # Only for synthetic fixture without Stage72 pedigree.
    init_orders(con)
    initialize(con)
    con.execute("""INSERT INTO local_simulated_orders(id,listing_id,listing_digest,listing_revision,
        client_token,quantity,currency,unit_price_minor,total_minor)
        VALUES(1,1,?,1,'mock_origin_01',2,'KRW',750,1500)""", ('a'*64,))
    con.execute("""INSERT INTO local_simulated_orders(id,listing_id,listing_digest,listing_revision,
        client_token,quantity,currency,unit_price_minor,total_minor)
        VALUES(2,2,?,1,'mock_origin_02',1,'USD',500,500)""", ('b'*64,))
    return con


def plan(con, order=1, key='mockplan_00001', mode=MODES[0], periods=3):
    return create(con, order, key, mode, periods)


def advance(con, sub, action, key='mockevent_0001', amount=0, note='local only'):
    return transition(con, sub, key, action, note, amount)


def test_plan_snapshot_and_nontransactional_flags():
    con=db(); p=plan(con)
    assert p['assumed_amount_minor']==1500 and p['currency']=='KRW'
    assert p['state']=='PLANNED_SIMULATED' and p['revision']==1
    for field in ('real_subscription','renewal_enabled','real_cancellation','refund_issued',
                  'payment_verified','customer_contacted'):
        assert p[field] is False
    assert len(history(con,p['id']))==1


def test_idempotent_plan():
    con=db(); a=plan(con)
    b=plan(con)
    assert b['id']==a['id'] and b['duplicate'] and len(history(con,a['id']))==1

@pytest.mark.parametrize('mode,months', [(MODES[0],0),(MODES[0],13),(MODES[0],True),
                                            (MODES[1],2),('ACTUAL_SUBSCRIPTION',1),(None,1)])
def test_invalid_plan_construction(mode,months):
    with pytest.raises(ValueError):plan(db(),mode=mode,periods=months)

@pytest.mark.parametrize('key', ['', 'short', 'a'*49,'hello@gmail.com','foo bar 123',
                                  'https://example.com','secret_12345','token_12345',None,77])
def test_invalid_plan_key(key):
    with pytest.raises(ValueError):plan(db(),key=key)


def test_reused_key_different_order_and_different_key_same_order():
    con=db();plan(con)
    with pytest.raises(ValueError,match='충돌'):plan(con,order=2)
    with pytest.raises(ValueError,match='충돌'):plan(con,key='otherplan_002')


def test_two_orders_independent():
    con=db();a=plan(con);b=plan(con,2,'otherplan_002',MODES[1],1)
    assert a['currency']=='KRW' and b['currency']=='USD'
    assert b['periods']==1 and len(history(con,b['id']))==1


def test_cancel_request_and_acknowledge():
    con=db();s=plan(con)
    a=advance(con,s['id'],'cancel_requested')
    assert a['state']=='CANCEL_REQUESTED_SIMULATED' and not a['real_cancellation']
    b=advance(con,s['id'],'cancel_acknowledged','mockevent_0002')
    assert b['state']=='CANCELLED_SIMULATED' and not b['real_cancellation']
    with pytest.raises(ValueError):advance(con,s['id'],'cancel_requested','mockevent_0003')


def test_refund_request_and_rejection_nonfinancial():
    con=db();s=plan(con)
    a=advance(con,s['id'],'refund_requested',amount=800)
    assert a['state']=='REFUND_REQUESTED_SIMULATED' and not a['refund_issued']
    b=advance(con,s['id'],'refund_declined','mockevent_0002')
    assert b['state']=='REFUND_DECLINED_SIMULATED' and not b['refund_issued']
    assert [x['assumed_amount_minor'] for x in history(con,s['id'])]==[0,800,0]


def test_refund_after_cancelled():
    con=db();s=plan(con)
    advance(con,s['id'],'cancel_requested')
    advance(con,s['id'],'cancel_acknowledged','mockevent_0002')
    assert advance(con,s['id'],'refund_requested','mockevent_0003',1500)['state']=='REFUND_REQUESTED_SIMULATED'


def test_idempotent_event_and_conflicting_event_key():
    con=db();s=plan(con)
    a=advance(con,s['id'],'cancel_requested')
    b=advance(con,s['id'],'cancel_requested')
    assert b['duplicate'] and b['revision']==2
    with pytest.raises(ValueError,match='충돌'):
        advance(con,s['id'],'refund_requested',amount=500)
    assert get(con,s['id'])['latest_digest']==a['latest_digest']


def test_key_conflict_across_subscriptions():
    con=db();a=plan(con);b=plan(con,2,'otherplan_002',MODES[1],1)
    advance(con,a['id'],'cancel_requested')
    with pytest.raises(ValueError,match='충돌'):
        advance(con,b['id'],'cancel_requested')

@pytest.mark.parametrize('action', ['refunded','paid','renewed','payment_succeeded',
                                    'plan_created','',None,'CANCELLED'])
def test_forbidden_action(action):
    con=db();s=plan(con)
    with pytest.raises(ValueError):advance(con,s['id'],action)

@pytest.mark.parametrize('amount', [-1,1501,True,1.0,None,'50'])
def test_invalid_refund_amount(amount):
    con=db();s=plan(con)
    with pytest.raises(ValueError):advance(con,s['id'],'refund_requested',amount=amount)

@pytest.mark.parametrize('amount', [0,1,1500])
def test_refund_limits(amount):
    con=db();s=plan(con)
    if amount == 0:
        with pytest.raises(ValueError):advance(con,s['id'],'refund_requested',amount=amount)
    else:
        assert advance(con,s['id'],'refund_requested',amount=amount)['state']=='REFUND_REQUESTED_SIMULATED'

@pytest.mark.parametrize('action,amount', [('cancel_requested',1),('cancel_acknowledged',1),('refund_declined',1)])
def test_no_money_for_other_events(action,amount):
    con=db();s=plan(con)
    with pytest.raises(ValueError):advance(con,s['id'],action,amount=amount)

@pytest.mark.parametrize('note',['x'*241,'email@address.test','https://example.com','\0',None])
def test_reject_pii_urls_and_oversized_notes(note):
    con=db();s=plan(con)
    with pytest.raises(ValueError):advance(con,s['id'],'cancel_requested',note=note)


def test_append_only_sqlite():
    con=db();s=plan(con)
    with pytest.raises(sqlite3.DatabaseError):
        con.execute('DELETE FROM local_mock_subscriptions')
    with pytest.raises(sqlite3.DatabaseError):
        con.execute('UPDATE local_mock_subscription_events SET digest=?',('x'*64,))
    assert get(con,s['id'])['state']=='PLANNED_SIMULATED'


def test_tampered_audit_detected_even_if_trigger_bypassed():
    con=db();s=plan(con)
    con.execute('DROP TRIGGER local_mock_subscription_events_no_update')
    con.execute("UPDATE local_mock_subscription_events SET note='corrupted' WHERE subscription_id=?",(s['id'],))
    with pytest.raises(ValueError,match='감사'):
        get(con,s['id'])


def test_no_unknown_order_or_subscription():
    con=db()
    with pytest.raises(ValueError):plan(con,order=17)
    with pytest.raises(ValueError):get(con,9)


def test_initialize_is_idempotent():
    con=db();initialize(con);initialize(con)
    assert plan(con)['state']=='PLANNED_SIMULATED'


@pytest.fixture
def store(tmp_path):
    s=LocalStore(tmp_path/'stage77.sqlite3')
    s.setup_owner('owner77','secure-password-77')
    return s


def test_owner_gate_and_provenance(store):
    store.logout()
    with pytest.raises(AuthenticationError):store.create_mock_subscription(1,'mockplan_00001',MODES[0],2)
    with pytest.raises(AuthenticationError):store.mock_subscription(1)
    store.login('owner77','secure-password-77')
    listing=prepared(store)
    order=store.create_simulated_order(listing,'test_order_000077',2)
    row=store.create_mock_subscription(order['id'],'mockplan_00001',MODES[0],2)
    assert row['state']=='PLANNED_SIMULATED' and not row['payment_verified']
    assert store.mock_subscription_history(row['id'])[0]['action']=='plan_created'
    assert store.transition_mock_subscription(row['id'],'mockevent_0001','cancel_requested')['state']=='CANCEL_REQUESTED_SIMULATED'
    store.logout()
    with pytest.raises(AuthenticationError):store.mock_subscription(row['id'])
    with pytest.raises(AuthenticationError):store.transition_mock_subscription(row['id'],'mockevent_0002','cancel_acknowledged')


def test_stale_listing_rejected_in_store(store):
    listing=prepared(store)
    order=store.create_simulated_order(listing,'test_order_000078',1)
    sub=store.create_mock_subscription(order['id'],'mockplan_00001',MODES[0],1)
    store.retire_unpublished_listing(listing,'로컬 폐기')
    with pytest.raises(ValueError,match='원본'):
        store.transition_mock_subscription(sub['id'],'mockevent_0001','cancel_requested')


def test_persistence_and_no_real_payment(store):
    listing=prepared(store)
    order=store.create_simulated_order(listing,'test_order_000079',1)
    sub=store.create_mock_subscription(order['id'],'mockplan_00001',MODES[0],1)
    store.transition_mock_subscription(sub['id'],'mockevent_0001','refund_requested',amount_minor=order['total_minor'])
    later=LocalStore(store.path)
    later.login('owner77','secure-password-77')
    assert later.mock_subscription(sub['id'])['state']=='REFUND_REQUESTED_SIMULATED'
    assert not later.mock_subscription(sub['id'])['refund_issued']
