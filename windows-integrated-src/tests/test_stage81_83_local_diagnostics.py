"""Stages 81-83: offline descriptive analytics and non-executing draft proposals."""
import sqlite3
import pytest
from desktop.storage import LocalStore,AuthenticationError
from desktop.local_company_diagnostics import performance,diagnostics,history,propose,initialize
from test_stage78_80_local_commerce import store as base_store

@pytest.fixture
def store(base_store):
    return base_store


def test_performance_is_descriptive_and_never_revenue(store):
    s,order,biz=store
    report=s.local_company_performance_report()
    assert report['actual_sales_data_available'] is False
    assert report['actual_staff_quality_verified'] is False
    assert report['read_only_descriptive'] is True
    assert report['assumed_budget']['includes_real_transactions'] is False
    assert report['tasks']['eligible']>=0
    assert next(b for b in report['businesses'] if b['id']==biz)['real_profit_verified'] is False


def test_detect_unsupported_sales_trend(store):
    s,order,biz=store
    before=s.local_company_diagnostics()
    assert before['live_revenue_decline']=='NOT_EVALUABLE_NO_VERIFIED_SALES'
    assert before['real_operational_problem_detected'] is False
    assert 'VERIFIED_REVENUE_MISSING:0' in {x['key'] for x in before['indicators']}


def test_detect_blocked_task_and_failed_queue(store):
    s,order,biz=store
    with s._connect() as con:
        task=int(con.execute("INSERT INTO company_tasks(title,status) VALUES('Offline test blocked','blocked')").lastrowid)
        q=int(con.execute("INSERT INTO local_task_queue(task_id,state) VALUES(?,'failed')",(task,)).lastrowid)
    current=s.local_company_diagnostics()
    assert f'BLOCKED_TASK:{task}' in {x['key'] for x in current['indicators']}
    assert f'FAILED_QUEUE:{q}' in {x['key'] for x in current['indicators']}
    assert s.local_company_performance_report()['tasks']['blocked']>=1


def test_hypothetical_over_budget_only(store):
    s,order,biz=store
    with s._connect() as con:
        budget=con.execute('SELECT budget_krw FROM managed_businesses WHERE id=?',(biz,)).fetchone()[0]
    s.record_hypothetical_finance(biz,'over_budget_0001','ASSUMED_EXPENSE','KRW',budget+1,'Local fake expense')
    current=s.local_company_diagnostics()
    indicator=next(x for x in current['indicators'] if x['key']==f'HYPOTHETICAL_BUDGET_OVERRUN:{biz}')
    assert indicator['severity']=='ASSUMPTION_ONLY'
    assert indicator['verified_external_problem'] is False


def test_draft_proposal_not_executed_and_idempotent(store):
    s,order,biz=store
    before=s.local_company_performance_report()['tasks']
    key='VERIFIED_REVENUE_MISSING:0'
    p=s.propose_local_improvement_draft(key,'proposal_83_mock','Review absence of verified data')
    assert p['not_an_executed_task'] and p['owner_approval_not_given']
    assert s.propose_local_improvement_draft(key,'proposal_83_mock','Review absence of verified data')['duplicate']
    assert s.local_company_performance_report()['tasks']==before
    with pytest.raises(ValueError, match='conflict'):
        s.propose_local_improvement_draft(key,'proposal_83_mock','Changed proposal data')
    assert len(s.local_improvement_draft_history())==1


def test_reject_unknown_or_resolved_diagnostic(store):
    s,order,biz=store
    with pytest.raises(ValueError,match='no longer present'):
        s.propose_local_improvement_draft('PAID:1','proposal_83_mock','Do not create real tasks')
    with pytest.raises(ValueError):
        s.propose_local_improvement_draft('VERIFIED_REVENUE_MISSING:0','short','Do not create')


def test_audit_append_only_and_tamper(store):
    s,order,biz=store
    s.propose_local_improvement_draft('VERIFIED_REVENUE_MISSING:0','proposal_83_mock','Review manually')
    with s._connect() as con:
        with pytest.raises(sqlite3.DatabaseError):
            con.execute('DELETE FROM local_diagnostic_improvement_drafts')
        with pytest.raises(sqlite3.DatabaseError):
            con.execute("UPDATE local_diagnostic_improvement_drafts SET title='corrupted'")
        con.execute('DROP TRIGGER local_diagnostic_improvement_drafts_no_update')
        con.execute("UPDATE local_diagnostic_improvement_drafts SET title='corrupted'")
    with pytest.raises(ValueError,match='hash chain'):s.local_improvement_draft_history()


def test_permission_and_persistence(store):
    s,order,biz=store
    s.propose_local_improvement_draft('VERIFIED_REVENUE_MISSING:0','proposal_83_mock','Manual only')
    later=LocalStore(s.path)
    later.login('owner78','not-a-production-password')
    assert len(later.local_improvement_draft_history())==1
    later.logout()
    for call in (later.local_company_performance_report,later.local_company_diagnostics,later.local_improvement_draft_history,
                 lambda:later.propose_local_improvement_draft('VERIFIED_REVENUE_MISSING:0','proposal_83_another','Should be denied')):
        with pytest.raises(AuthenticationError):call()


def test_initialize_repeated(store):
    s,order,biz=store
    with s._connect() as con:
        initialize(con);initialize(con)
    assert s.local_company_diagnostics()['live_revenue_decline'].startswith('NOT_EVALUABLE')
