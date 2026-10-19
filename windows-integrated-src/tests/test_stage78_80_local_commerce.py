"""Stages 78-80: synthetic-only support, hypothetical ledger, budget; no network."""
import sqlite3
from concurrent.futures import ThreadPoolExecutor
import pytest

from desktop.storage import LocalStore, AuthenticationError
from desktop.local_synthetic_support import initialize as init78, create as create78, transition as change78, history as history78, get as get78
from desktop.local_hypothetical_finance import initialize as init79, record as record79, history as history79
from desktop.local_budget_scenarios import initialize as init80, calculate as calculate80, save as save80, snapshots
from desktop.offline_order_simulations import initialize as init_orders
from test_stage73_simulated_orders import prepared

@pytest.fixture
def synthetic():
    con=sqlite3.connect(':memory:')
    con.execute('PRAGMA foreign_keys=OFF')
    init_orders(con);init78(con);init79(con);init80(con)
    con.execute("""INSERT INTO local_simulated_orders(id,listing_id,listing_digest,listing_revision,client_token,quantity,currency,unit_price_minor,total_minor)
      VALUES(1,1,?,1,'order_78_demo1',2,'KRW',500,1000)""",('a'*64,))
    con.execute("""INSERT INTO local_simulated_orders(id,listing_id,listing_digest,listing_revision,client_token,quantity,currency,unit_price_minor,total_minor)
      VALUES(2,2,?,1,'order_78_demo2',2,'USD',500,1000)""",('b'*64,))
    con.execute("CREATE TABLE managed_businesses(id INTEGER PRIMARY KEY, name TEXT, budget_krw INTEGER)")
    con.execute("INSERT INTO managed_businesses VALUES (1,'offline demo',800)")
    return con

def ticket(con,order=1,key='ticket_mock_01'):
    return create78(con,order,key,'SIMCUST_abc123','QUESTION_SIMULATED','Example synthetic question')

def test_78_no_real_customer(synthetic):
    a=ticket(synthetic)
    assert a['simulation_only'] and not a['real_customer'] and not a['message_sent']
    assert len(history78(synthetic,a['id']))==1
    assert ticket(synthetic)['duplicate']
    assert change78(synthetic,a['id'],'evt_78_test001','reviewed','Local review')['state']=='REVIEW_SIMULATED'
    assert change78(synthetic,a['id'],'evt_78_test002','resolved','Simulated resolution')['state']=='RESOLVED_SIMULATED'
    assert change78(synthetic,a['id'],'evt_78_test003','closed','Closed locally')['state']=='CLOSED_SIMULATED'
    assert len(history78(synthetic,a['id']))==4

def test_78_event_idempotency_and_conflict(synthetic):
    a=ticket(synthetic)
    change78(synthetic,a['id'],'evt_78_test001','reviewed','Local review')
    assert change78(synthetic,a['id'],'evt_78_test001','reviewed','Local review')['duplicate']
    with pytest.raises(ValueError,match='conflict'):
        change78(synthetic,a['id'],'evt_78_test001','closed','Local review')
    with pytest.raises(ValueError,match='allowed simulated action'):
        change78(synthetic,a['id'],'evt_78_test004','opened','Bad')

def test_78_alias_and_pii_restriction(synthetic):
    for alias in ('john@example.com','John Smith','SIMCUST_a','SIMCUST_some@one',None):
        with pytest.raises(ValueError):create78(synthetic,1,'ticket_mock_01',alias,'QUESTION_SIMULATED','Example synthetic question')
    for text in ('contact me@example.com','https://example.org','password:123','bad\nline'):
        with pytest.raises(ValueError):create78(synthetic,1,'ticket_mock_01','SIMCUST_abc123','QUESTION_SIMULATED',text)

def test_78_key_collision_and_cross_ticket(synthetic):
    ticket(synthetic)
    with pytest.raises(ValueError,match='conflict'):ticket(synthetic,2)
    b=ticket(synthetic,2,'ticket_mock_02')
    change78(synthetic,1,'evt_78_test001','reviewed','Local review')
    with pytest.raises(ValueError,match='conflict'):
        change78(synthetic,b['id'],'evt_78_test001','reviewed','Local review')

def test_78_audit_triggers_and_tamper(synthetic):
    a=ticket(synthetic)
    with pytest.raises(sqlite3.DatabaseError): synthetic.execute('DELETE FROM local_support_tickets')
    with pytest.raises(sqlite3.DatabaseError): synthetic.execute('UPDATE local_support_ticket_events SET digest=?',('bad',))
    synthetic.execute('DROP TRIGGER local_support_ticket_events_no_update')
    synthetic.execute("UPDATE local_support_ticket_events SET digest='changed' WHERE ticket_id=?",(a['id'],))
    with pytest.raises(ValueError,match='checksum'):history78(synthetic,a['id'])

def test_79_expense_and_idempotency(synthetic):
    entry=record79(synthetic,1,'expense_000001','ASSUMED_EXPENSE','KRW',350,'Local example expense')
    assert not entry['real_spend'] and not entry['verified_revenue']
    assert record79(synthetic,1,'expense_000001','ASSUMED_EXPENSE','KRW',350,'Local example expense')['duplicate']
    with pytest.raises(ValueError,match='conflict'):
        record79(synthetic,1,'expense_000001','ASSUMED_EXPENSE','KRW',351,'Local example expense')
    assert len(history79(synthetic))==1

@pytest.mark.parametrize('kind',('ASSUMED_REVENUE','ASSUMED_REFUND','ASSUMED_SETTLEMENT_REFERENCE'))
def test_79_missing_order_for_revenue_settlement_refund(synthetic,kind):
    with pytest.raises(ValueError,match='order required'):
        record79(synthetic,1,'fake_order_0001',kind,'KRW',100,'Synthetic evidence')

@pytest.mark.parametrize('value',(-1,True,1.0,10**16))
def test_79_reject_invalid_money(synthetic,value):
    with pytest.raises(ValueError):record79(synthetic,1,'expense_000001','ASSUMED_EXPENSE','KRW',value,'Local example expense')

def test_79_nonverified_and_chain(synthetic):
    record79(synthetic,1,'expense_000001','ASSUMED_EXPENSE','KRW',100,'One synthetic expense')
    record79(synthetic,1,'expense_000002','ASSUMED_EXPENSE','KRW',220,'Second synthetic expense')
    assert len(history79(synthetic))==2
    with pytest.raises(sqlite3.DatabaseError):synthetic.execute('UPDATE local_hypothetical_finance SET amount_minor=1')
    synthetic.execute('DROP TRIGGER local_hypothetical_finance_no_update')
    synthetic.execute('UPDATE local_hypothetical_finance SET amount_minor=1 WHERE id=1')
    with pytest.raises(ValueError,match='chain'):history79(synthetic)

def test_80_assumed_profit_budget_and_separate_settlement(synthetic):
    record79(synthetic,1,'expense_000001','ASSUMED_EXPENSE','KRW',350,'Example expense')
    record79(synthetic,1,'expense_000002','ASSUMED_EXPENSE','USD',125,'Foreign example')
    report=calculate80(synthetic)
    b=report['businesses'][0]
    assert b['assumed_expenses_krw']==350
    assert b['hypothetical_budget_remaining_krw']==450
    assert b['assumed_net_krw']==-350
    assert b['non_krw_excluded']['USD']['sum_minor_not_converted']==125
    assert not report['includes_real_transactions'] and not report['accounting_compliant']

def test_80_snapshot_same_key_conflict(synthetic):
    first=save80(synthetic,'budget_000001')
    assert save80(synthetic,'budget_000001')['duplicate']
    assert first['report']['currency']=='KRW'
    record79(synthetic,1,'expense_000001','ASSUMED_EXPENSE','KRW',10,'Synthetic cost')
    with pytest.raises(ValueError,match='conflict'):save80(synthetic,'budget_000001')
    second=save80(synthetic,'budget_000002')
    assert len(snapshots(synthetic))==2 and second['id']!=first['id']
    with pytest.raises(sqlite3.DatabaseError):synthetic.execute('DELETE FROM local_budget_snapshots')

def test_80_snapshot_tamper_detection(synthetic):
    save80(synthetic,'budget_000001')
    synthetic.execute('DROP TRIGGER local_budget_snapshots_no_update')
    synthetic.execute("UPDATE local_budget_snapshots SET snapshot_json='{}'")
    with pytest.raises(ValueError,match='hash chain'):snapshots(synthetic)

@pytest.fixture
def store(tmp_path):
    s=LocalStore(tmp_path/'stage78_80.sqlite3')
    s.setup_owner('owner78','not-a-production-password')
    listing=prepared(s)
    order=s.create_simulated_order(listing,'stage78_order_01',2)
    with s._connect() as con:
        business_id=con.execute('''SELECT cat.business_id FROM local_unpublished_listings l
          JOIN local_catalog_items cat ON l.catalog_item_id=cat.id WHERE l.id=?''',(listing,)).fetchone()[0]
    return s,order,business_id

def test_store_owner_gate_and_local_78_79_80(store):
    s,order,biz=store
    ticket=s.create_synthetic_support_ticket(order['id'],'ticket_000001','SIMCUST_abc123','QUESTION_SIMULATED','Local only')
    assert not ticket['real_customer']
    assert s.transition_synthetic_support_ticket(ticket['id'],'ticket_action_01','reviewed','Offline reviewed')['state']=='REVIEW_SIMULATED'
    revenue=s.record_hypothetical_finance(biz,'revenue_000001','ASSUMED_REVENUE',order['currency'],order['total_minor'],'Simulated revenue',order['id'])
    assert not revenue['verified_revenue']
    s.record_hypothetical_finance(biz,'expense_000001','ASSUMED_EXPENSE','KRW',150,'Hypothetical expense')
    report=s.hypothetical_budget_report()
    assert report['total_assumed_expenses_krw']>=150
    snap=s.save_hypothetical_budget_snapshot('budget_000001')
    assert snap['report']['simulated_only']
    assert len(s.hypothetical_budget_snapshots())==1
    s.logout()
    for call in (lambda:s.create_synthetic_support_ticket(order['id'],'ticket_000002','SIMCUST_abc123','QUESTION_SIMULATED','Local only'),
                 lambda:s.hypothetical_finance_history(),lambda:s.hypothetical_budget_report(),
                 lambda:s.save_hypothetical_budget_snapshot('budget_000002')):
        with pytest.raises(AuthenticationError):call()

def test_store_reject_wrong_assumed_business_or_currency(store):
    s,order,biz=store
    with pytest.raises(ValueError,match='mismatch'):
        s.record_hypothetical_finance(biz,'revenue_000001','ASSUMED_REVENUE','EUR',100,'Synthetic revenue',order['id'])
    with pytest.raises(ValueError,match='exceeds'):
        s.record_hypothetical_finance(biz,'revenue_000001','ASSUMED_REVENUE',order['currency'],order['total_minor']+1,'Synthetic revenue',order['id'])

def test_store_persistent_after_reconnect(store):
    s,order,biz=store
    s.record_hypothetical_finance(biz,'expense_000001','ASSUMED_EXPENSE','KRW',10,'Synthetic expense')
    s.save_hypothetical_budget_snapshot('budget_000001')
    second=LocalStore(s.path);second.login('owner78','not-a-production-password')
    assert second.hypothetical_budget_snapshots()[0]['report']['total_assumed_expenses_krw']>=10
    assert len(second.hypothetical_finance_history())==1

def test_store_concurrent_same_ledger_key(store):
    s,order,biz=store
    def run(_):return s.record_hypothetical_finance(biz,'expense_concurrent_01','ASSUMED_EXPENSE','KRW',10,'Concurrent fake expense')
    with ThreadPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(run,[1,2]))
    assert results[0]['id']==results[1]['id']
    assert len(s.hypothetical_finance_history())==1


def test_78_ticket_base_tamper_detected(synthetic):
    t=ticket(synthetic)
    synthetic.execute('DROP TRIGGER local_support_tickets_no_update')
    synthetic.execute("UPDATE local_support_tickets SET summary='Changed offline' WHERE id=?",(t['id'],))
    with pytest.raises(ValueError, match='checksum'):
        get78(synthetic,t['id'])


def test_79_accumulated_order_amount_capped(store):
    s,order,biz=store
    half=order['total_minor']//2
    s.record_hypothetical_finance(biz,'revenue_portion01','ASSUMED_REVENUE',order['currency'],half,'Synthetic revenue part',order['id'])
    s.record_hypothetical_finance(biz,'revenue_portion02','ASSUMED_REVENUE',order['currency'],half,'Synthetic revenue part two',order['id'])
    with pytest.raises(ValueError,match='total exceeds'):
        s.record_hypothetical_finance(biz,'revenue_portion03','ASSUMED_REVENUE',order['currency'],1,'Synthetic extra',order['id'])


def test_80_never_double_counts_settlement_reference(store):
    s,order,biz=store
    if order['currency']!='KRW':pytest.skip('sample fixture not KRW')
    total=order['total_minor']
    s.record_hypothetical_finance(biz,'revenue_once_01','ASSUMED_REVENUE','KRW',total,'Revenue example',order['id'])
    s.record_hypothetical_finance(biz,'settlement_ref1','ASSUMED_SETTLEMENT_REFERENCE','KRW',total,'Settlement assumption',order['id'])
    row=next(x for x in s.hypothetical_budget_report()['businesses'] if x['business_id']==biz)
    assert row['assumed_revenue_krw']==total
    assert row['assumed_settlement_reference_krw_not_extra_revenue']==total
    assert row['assumed_net_krw']==total
