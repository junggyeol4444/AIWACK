"""서명된 외부 거래 증빙은 실제 매출을 보증하지 않는다."""
import json
import hmac
import hashlib
import pytest
from desktop.storage import LocalStore
from desktop import company_payment_reconciliation as finance

@pytest.fixture
def ctx(tmp_path):
    store=LocalStore(tmp_path/'provider.sqlite3')
    store.setup_owner('owner','provider-owner-password-2026')
    business=store.create_business(1,'정산 검토 사업','실제 공급자 연동 대기')
    return store,business

def body(b,event,kind,transaction,amount,related=''):
    return json.dumps(dict(provider='test-provider',event_id=event,transaction_id=transaction,
        business_id=b,event_type=kind,related_transaction=related,currency='KRW',
        amount_minor=amount),sort_keys=True).encode()

def signed(store,raw):
    secret='provider-signature-secret-2026'
    return finance.ingest(store,raw,hmac.new(secret.encode(),raw,hashlib.sha256).hexdigest(),secret)

def test_external_signed_settlement_refund_reconcile_no_fake_revenue(ctx):
    store,b=ctx
    a=signed(store,body(b,'settlement-01','settlement','tx-0001',120000))
    assert signed(store,body(b,'settlement-01','settlement','tx-0001',120000))['duplicate']
    assert finance.summary(store,b)['accepted_signed_net_minor']==0
    finance.review(store,a['id'],'accepted','관리자 외부 정산 증빙 검수')
    refund=signed(store,body(b,'refund-0001','refund','refund-tx01',30000,'tx-0001'))
    finance.review(store,refund['id'],'accepted','관리자 확인 후 환불 증빙 수락')
    too_large=signed(store,body(b,'refund-0002','refund','refund-tx02',100000,'tx-0001'))
    with pytest.raises(ValueError,match='초과'):
        finance.review(store,too_large['id'],'accepted','누적 원거래 초과 환불 검수')
    totals=finance.summary(store,b)
    assert totals['accepted_signed_net_minor']==90000
    assert totals['real_bank_settlement_confirmed'] is False
    assert totals['external_provider_connected'] is False
    store.logout()
    fresh=LocalStore(store.path);fresh.login('owner','provider-owner-password-2026')
    assert finance.summary(fresh,b)['accepted_signed_net_minor']==90000

def test_invalid_signature_conflict_stopped_and_duplicate_settlement(ctx):
    store,b=ctx
    raw=body(b,'settlement-02','settlement','tx-0002',3000)
    with pytest.raises(PermissionError):
        finance.ingest(store,raw,'0'*64,'provider-signature-secret-2026')
    original=signed(store,raw)
    with pytest.raises(ValueError,match='불일치'):
        signed(store,body(b,'settlement-02','settlement','tx-0002',3300))
    finance.review(store,original['id'],'accepted','원문 확인한 관리자 명시 승인')
    duplicate=signed(store,body(b,'another-event','settlement','tx-0002',3000))
    with pytest.raises(ValueError,match='두 번'):
        finance.review(store,duplicate['id'],'accepted','동일 공급자 거래 중복 금지')
    store.emergency_stop_local(True,'외부 거래 검증 일시 중단')
    with pytest.raises(PermissionError):
        signed(store,body(b,'expense-0003','expense','ex-0003',200))
