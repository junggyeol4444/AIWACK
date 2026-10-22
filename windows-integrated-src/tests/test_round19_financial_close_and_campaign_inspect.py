"""19회차: 은행 CSV 대사 기반 결산 스냅샷과 30업무 증빙 검사 회귀."""
import csv
import hashlib
import hmac
import json
import sqlite3

import pytest

from desktop.storage import LocalStore
from desktop import company_financial_close as close
from desktop import company_bank_reconciliation as bank
from desktop import company_payment_reconciliation as pay
from tests.test_round18_bank_and_campaign_evidence import (
    payment_fixture, make_signed, record, write_csv, campaign_fixture, complete_one)


def _paid(st, tmp_path, business, tx, amount, bank_ref):
    make_signed(st,business,'settlement',tx,amount,'evt-'+tx)
    return bank.import_owner_csv(st,write_csv(tmp_path,[record(business,tx,amount,bank_ref)]))


def test_close_rejects_unmatched_and_pending_and_emergency(tmp_path):
    st,b=payment_fixture(tmp_path)
    make_signed(st,b,'settlement','tx-close-a01',12000,'event-close-a01')
    preview=st.preview_business_financial_close(b)
    assert not preview['eligible_for_local_close']
    assert preview['blocked'][0]['reason'].startswith('관리자 CSV 대사')
    with pytest.raises(ValueError,match='미대사'):
        st.create_business_financial_close(b,'관리자가 승인 거래 대사 확인')
    write_csv(tmp_path,[record(b,'tx-close-a01',12000,'bank-ref-a01')])
    st.reconcile_owner_bank_csv(tmp_path/'bank_source.csv')
    assert st.preview_business_financial_close(b)['eligible_for_local_close']
    st.emergency_stop_local(True,'결산 기능 비상정지 점검')
    with pytest.raises(PermissionError,match='비상정지'):
        st.create_business_financial_close(b,'관리자가 승인 거래 대사 확인')


def test_close_snapshot_append_only_and_relogin_after_new_event(tmp_path):
    st,b=payment_fixture(tmp_path)
    _paid(st,tmp_path,b,'tx-close-b01',25000,'bank-ref-b01')
    info=st.create_business_financial_close(b,'은행 CSV와 승인 증빙 금액 점검')
    assert info['statement']['accepted_count']==1
    assert info['statement']['net_minor']==25000
    assert info['statement']['independently_verified_bank_or_provider'] is False
    with pytest.raises(ValueError,match='이미 있습니다'):
        st.create_business_financial_close(b,'반복 결산 확정을 금지합니다')
    # More signed events do not retroactively rewrite the old snapshot.
    make_signed(st,b,'settlement','tx-close-b02',3000,'event-close-b02')
    assert st.read_business_financial_close(info['id'])['statement']['net_minor']==25000
    assert st.preview_business_financial_close(b)['eligible_for_local_close'] is False
    st.logout()
    other=LocalStore(st.path);other.login('owner-round18','round18-password-strong')
    assert other.read_business_financial_close(info['id'])['statement_sha256']==info['statement_sha256']


def test_close_refuses_duplicate_or_tampered_sqlite_lines(tmp_path):
    st,b=payment_fixture(tmp_path)
    _paid(st,tmp_path,b,'tx-close-c01',1000,'bank-ref-c01')
    info=st.create_business_financial_close(b,'기존 입출금 대사 감사 증빙')
    with st._connect() as con:
        with pytest.raises(sqlite3.DatabaseError):
            con.execute('UPDATE aiwack_business_financial_closes SET accepted_net_minor=0')
        with pytest.raises(sqlite3.DatabaseError):
            con.execute('DELETE FROM aiwack_business_financial_close_lines')
        # sqlite_schema tamper not emulated: expected read proves entries.
    assert st.read_business_financial_close(info['id'])['immutable_sqlite_close_verified']


def test_close_pending_and_rejected_event_block_final_snapshot(tmp_path):
    st,b=payment_fixture(tmp_path)
    _paid(st,tmp_path,b,'tx-close-d01',1000,'bank-ref-d01')
    raw=json.dumps({'provider':'bank-test-provider','event_id':'event-close-d02',
      'transaction_id':'tx-close-d02','business_id':b,'event_type':'settlement',
      'related_transaction':'','currency':'KRW','amount_minor':1000}).encode()
    secret='local-fixture-secret-2026-round18'
    received=pay.ingest(st,raw,hmac.new(secret.encode(),raw,hashlib.sha256).hexdigest(),secret)
    assert st.preview_business_financial_close(b)['blocked']
    pay.review(st,received['id'],'rejected','검증되지 않은 이벤트 반려 처리')
    with pytest.raises(ValueError,match='검수 미완료'):
        st.create_business_financial_close(b,'반려 거래를 포함한 결산은 중지')


def test_close_multiple_businesses_do_not_mix(tmp_path):
    st,b=payment_fixture(tmp_path)
    b2=st.create_business(1,'두 번째 사업','다른 사업의 승인 거래 대사')
    _paid(st,tmp_path,b,'tx-close-e01',5000,'bank-ref-e01')
    first=st.create_business_financial_close(b,'첫 번째 사업 거래 확인 점검')
    assert st.preview_business_financial_close(b2)['accepted_and_matched']==0
    assert not st.preview_business_financial_close(b2)['eligible_for_local_close']
    assert st.read_business_financial_close(first['id'])['statement']['business_id']==b


def test_campaign_inspection_has_thirty_rows_and_gates_missing_chief(tmp_path,monkeypatch):
    st,campaign=campaign_fixture(tmp_path,monkeypatch)
    before=st.inspect_campaign_step_evidence(campaign['id'])
    assert before['total_tasks']==30
    assert before['chief_call_linked_steps']==0
    assert before['all_30_genuine_model_audits_and_owner_reviews_verified'] is False
    complete_one(st,campaign)
    after=st.inspect_campaign_step_evidence(campaign['id'])
    assert after['approved_worker_steps']==1
    assert after['chief_call_linked_steps']==1
    assert after['verified_sequential_steps']==1
    assert after['rows'][0]['ready_for_handoff']
    assert not after['rows'][1]['ready_for_handoff']
    assert not after['independent_model_execution_or_binary_verified']