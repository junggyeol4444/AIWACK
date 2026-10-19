import sqlite3
import pytest
from desktop.offline_order_simulations import initialize as init_orders
from desktop.offline_delivery_simulations import initialize, record, history

def db():
    con=sqlite3.connect(':memory:')
    con.execute('PRAGMA foreign_keys=OFF')
    init_orders(con)
    initialize(con)
    con.execute("""INSERT INTO local_simulated_orders(id,listing_id,listing_digest,listing_revision,client_token,quantity,currency,unit_price_minor,total_minor) VALUES(1,1,'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',1,'token_test',1,'KRW',100,100)""")
    return con

def test_idempotency_and_append_only():
    con=db()
    a=record(con,1,'test-key-123','PLANNED_SIMULATED','local only')
    assert a['real_delivery'] is False and not a['duplicate']
    assert record(con,1,'test-key-123','PLANNED_SIMULATED','local only')['duplicate']
    assert len(history(con,1))==1
    with pytest.raises(sqlite3.DatabaseError):con.execute('DELETE FROM local_mock_delivery_events')

def test_conflicting_replay():
    con=db();record(con,1,'test-key-123','PLANNED_SIMULATED','a')
    with pytest.raises(ValueError):record(con,1,'test-key-123','PLANNED_SIMULATED','b')

@pytest.mark.parametrize('state', ['SENT','DELIVERED','PAID','FULFILLED',''])
def test_real_states_rejected(state):
    with pytest.raises(ValueError):record(db(),1,'test-key-123',state,'')

def test_unknown_order():
    with pytest.raises(ValueError):record(db(),999,'test-key-123','PLANNED_SIMULATED','')

def test_cancel_simulated():
    con=db();v=record(con,1,'test-key-123','CANCELLED_SIMULATED','')
    assert v['state']=='CANCELLED_SIMULATED'
