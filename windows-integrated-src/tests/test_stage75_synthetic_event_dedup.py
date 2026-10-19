import pytest
from desktop.storage import LocalStore
from test_stage73_simulated_orders import prepared


def test_synthetic_event_dedup_and_conflict(tmp_path):
    s=LocalStore(tmp_path/'stage75.sqlite3');s.setup_owner('owner75','stage75-long-password')
    listing=prepared(s);order=s.create_simulated_order(listing,'localref_0075',2)
    fixture={'kind':'LOCAL_TEST_ONLY','currency':order['currency'],'amount_minor':order['total_minor']}
    f=s.check_offline_payment_fixture(order['id'],'fixture_00075',fixture)
    payload={'kind':'LOCAL_SYNTHETIC_EVENT','fixture_reference':'fixture_00075'}
    first=s.record_synthetic_payment_event(order['id'],f['id'],'synthetic_event_0075',payload)
    assert first['duplicate'] is False and first['real_payment_verified'] is False
    second=s.record_synthetic_payment_event(order['id'],f['id'],'synthetic_event_0075',payload)
    assert second['duplicate'] is True and second['id']==first['id']
    with pytest.raises(ValueError,match='conflicting'):
        s.record_synthetic_payment_event(order['id'],f['id'],'synthetic_event_0075',dict(payload,fixture_reference='other'))
    assert s.simulated_order(order['id'])['payment_received'] is False

@pytest.mark.parametrize('payload', [{'kind':'PROVIDER_PAYMENT','fixture_reference':'fixture_00075'}, {'kind':'LOCAL_SYNTHETIC_EVENT','fixture_reference':'fixture_00075','token':'secret'}])
def test_reject_nonlocal_event(tmp_path,payload):
    s=LocalStore(tmp_path/'invalid75.sqlite3');s.setup_owner('owner75','stage75-long-password')
    with pytest.raises(ValueError):
        s.record_synthetic_payment_event(1,1,'synthetic_event_0075',payload)
