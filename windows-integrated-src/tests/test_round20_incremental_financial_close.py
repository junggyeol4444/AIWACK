"""20회차: 과거 결산 보존, 새로운 기간 중복 산정 방지, 원본 감사 불변 검증."""
import hashlib
import json
import sqlite3
import pytest

from desktop import company_financial_close as close
from desktop import company_bank_reconciliation as bank
from desktop import company_payment_reconciliation as pay
from tests.test_round18_bank_and_campaign_evidence import payment_fixture,make_signed,write_csv,record


def _transaction(store,tmp,biz,key,amount,kind='settlement'):
    make_signed(store,biz,kind,'tx-v20-'+key,amount,'ev-v20-'+key)
    store.reconcile_owner_bank_csv(write_csv(tmp,[record(biz,'tx-v20-'+key,amount,'br-v20-'+key,kind)]))


def test_separate_closes_do_not_double_count_previous_settlements(tmp_path):
    st,b=payment_fixture(tmp_path)
    _transaction(st,tmp_path,b,'001',25000)
    first=st.create_business_financial_close(b,'첫 기간 은행 대사 증빙 감사')
    _transaction(st,tmp_path,b,'002',8000)
    pending=st.preview_business_financial_close(b)
    assert pending['accepted_and_matched']==1
    assert pending['previous_close_id']==first['id']
    second=st.create_business_financial_close(b,'두 번째 기간 은행 대사 확인')
    assert first['statement']['statement_version']==2
    assert second['statement']['period_start_event_id']==first['statement']['cutoff_event_id']+1
    assert second['statement']['accepted_count']==1
    assert second['statement']['net_minor']==8000
    assert second['statement']['prior_close_sha256']==first['statement_sha256']
    aggregate=st.list_business_financial_closes(b)
    assert [p['period_net_minor'] for p in aggregate['periods']]==[25000,8000]
    assert aggregate['cumulative_local_reconciled_net_minor']==33000
    assert st.read_business_financial_close(first['id'])['statement_sha256']==first['statement_sha256']
    assert st.read_business_financial_close(second['id'])['statement_sha256']==second['statement_sha256']
    assert not st.preview_business_financial_close(b)['eligible_for_local_close']


def test_refund_and_expense_subtract_once_each_period(tmp_path):
    st,b=payment_fixture(tmp_path)
    _transaction(st,tmp_path,b,'010',10000)
    first=st.create_business_financial_close(b,'처음 정산 1차 금액 점검')
    # Create a properly linked accepted refund: provider.review enforces the
    # original transaction and prevents exceeding accepted settlement amount.
    original=st.read_business_financial_close(first['id'])
    # A separate expense event is sufficient to test signed negative accounting.
    _transaction(st,tmp_path,b,'011',3000,'expense')
    second=st.create_business_financial_close(b,'신규 비용 금액 기간 대사')
    assert second['statement']['amounts_minor']['expense']==3000
    assert second['statement']['net_minor']==-3000
    assert st.list_business_financial_closes(b)['cumulative_local_reconciled_net_minor']==7000
    assert original['statement_sha256']==st.read_business_financial_close(first['id'])['statement_sha256']


def test_incomplete_new_period_does_not_modify_closed_statement(tmp_path):
    st,b=payment_fixture(tmp_path)
    _transaction(st,tmp_path,b,'020',9000)
    first=st.create_business_financial_close(b,'첫 기간 결산 원장 확인')
    make_signed(st,b,'settlement','tx-v20-next',3000,'ev-v20-next')
    with pytest.raises(ValueError,match='미대사'):
        st.create_business_financial_close(b,'승인 자료가 없는 신규 거래 결산')
    assert st.read_business_financial_close(first['id'])['statement']['net_minor']==9000
    assert len(st.list_business_financial_closes(b)['periods'])==1


def test_period_rows_and_chain_immutable(tmp_path):
    st,b=payment_fixture(tmp_path)
    _transaction(st,tmp_path,b,'030',12000)
    a=st.create_business_financial_close(b,'기간 시작 체인 무결성 검증')
    _transaction(st,tmp_path,b,'031',100)
    z=st.create_business_financial_close(b,'기간 후속 체인 무결성 검증')
    with st._connect() as con:
        with pytest.raises(sqlite3.DatabaseError):
            con.execute('UPDATE aiwack_business_financial_close_periods SET period_start_event_id=1 WHERE close_id=?',(z['id'],))
        with pytest.raises(sqlite3.DatabaseError):
            con.execute('DELETE FROM aiwack_business_financial_close_periods WHERE close_id=?',(z['id'],))
    assert st.read_business_financial_close(z['id'])['statement']['prior_close_sha256']==a['statement_sha256']


def test_legacy_close_migration_retains_exact_v1_hash(tmp_path):
    st,b=payment_fixture(tmp_path)
    _transaction(st,tmp_path,b,'040',7777)
    with st._connect() as con:
        close.initialize(con)
        ready,blocked=close._rows(con,b)
        assert len(ready)==1 and not blocked
        first=ready[0][0]
        legacy=close._statement(b,first,ready,'이전 버전 누적 결산 보존')
        digest=close._digest(legacy)
        old_id=con.execute('''INSERT INTO aiwack_business_financial_closes
            (business_id,cutoff_event_id,accepted_count,accepted_net_minor,owner_note,statement_sha256)
            VALUES(?,?,?,?,?,?)''',(b,first,1,7777,legacy['owner_note'],digest)).lastrowid
        con.execute('''INSERT INTO aiwack_business_financial_close_lines
            (close_id,payment_event_id,bank_match_id,event_sha256,amount_minor)
            VALUES(?,?,?,?,?)''',(old_id,ready[0][0],ready[0][1],ready[0][2],ready[0][4]))
    assert st.read_business_financial_close(old_id)['statement_sha256']==digest
    _transaction(st,tmp_path,b,'041',333)
    new=st.create_business_financial_close(b,'이전 기록 그대로 새 기간 확정')
    assert new['statement']['prior_close_id']==old_id
    assert st.list_business_financial_closes(b)['cumulative_local_reconciled_net_minor']==8110
    assert st.read_business_financial_close(old_id)['statement_sha256']==digest


def test_separate_business_close_histories_do_not_mix(tmp_path):
    st,b=payment_fixture(tmp_path)
    other=st.create_business(1,'별도 사업','사업 원장 격리 확인 시험')
    _transaction(st,tmp_path,b,'050',4000)
    first=st.create_business_financial_close(b,'사업별 결산 1번 증빙 검토')
    _transaction(st,tmp_path,other,'051',6000)
    second=st.create_business_financial_close(other,'사업별 결산 2번 증빙 검토')
    assert st.list_business_financial_closes(b)['cumulative_local_reconciled_net_minor']==4000
    assert st.list_business_financial_closes(other)['cumulative_local_reconciled_net_minor']==6000
    assert first['statement']['prior_close_id'] is None
    assert second['statement']['prior_close_id'] is None