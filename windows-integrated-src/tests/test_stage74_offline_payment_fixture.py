import pytest
from desktop.storage import LocalStore
from test_stage73_simulated_orders import prepared

def test_synthetic_fixture_never_confirms_payment(tmp_path):
    s=LocalStore(tmp_path/'fixture.sqlite3');s.setup_owner('owner74','stage74-long-password')
    listing=prepared(s);order=s.create_simulated_order(listing,'localref_0074',2)
    fixture={'kind':'LOCAL_TEST_ONLY','currency':order['currency'],'amount_minor':order['total_minor']}
    first=s.check_offline_payment_fixture(order['id'],'fixture_00074',fixture)
    assert first['verdict']=='UNVERIFIED_NO_PROVIDER' and first['real_payment_verified'] is False
    assert s.check_offline_payment_fixture(order['id'],'fixture_00074',fixture)==first
    with pytest.raises(ValueError,match='conflicting'):
        s.check_offline_payment_fixture(order['id'],'fixture_00074',dict(fixture,amount_minor=0))
    bad=s.check_offline_payment_fixture(order['id'],'fixture_00075',dict(fixture,amount_minor=0))
    assert bad['verdict']=='REJECTED_SYNTHETIC_MISMATCH'
    assert not s.simulated_order(order['id'])['payment_received']

@pytest.mark.parametrize('fixture', [{'kind':'PAID','currency':'KRW','amount_minor':1},{'kind':'LOCAL_TEST_ONLY','currency':'KRW','amount_minor':True},{'kind':'LOCAL_TEST_ONLY','currency':'KRW','amount_minor':1,'provider_token':'secret'}])
def test_invalid_fixture_rejected(tmp_path,fixture):
    s=LocalStore(tmp_path/'invalid.sqlite3');s.setup_owner('owner74','stage74-long-password')
    with pytest.raises(ValueError): s.check_offline_payment_fixture(1,'fixture_00074',fixture)
