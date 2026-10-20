"""기존 LocalStore에서 소유자 승인→실제 SQLite 읽기→감사·재로그인 통합 검사."""
from concurrent.futures import ThreadPoolExecutor
import sqlite3

import pytest

from desktop.storage import LocalStore


@pytest.fixture
def office(tmp_path):
    st=LocalStore(tmp_path/'real_tool.sqlite3')
    st.setup_owner('owner','local-tool-password')
    employee=st.add_employee_draft('real_reader','실제 조회 담당')
    st.save_employee_access(employee,['company:read','goals:read'],
                            ['local_company_reader','local_goals_reader'])
    company=st.register_ai_tool('local_company_reader','회사 실제 읽기','management',
                               '회사 SQLite 조회','company:read')
    goals=st.register_ai_tool('local_goals_reader','목표 실제 읽기','management',
                             '목표 SQLite 조회','goals:read')
    return st,employee,company,goals


def approved(st,employee,tool,key):
    rid=st.request_ai_tool_use(key,tool,employee,'소유자가 실제 SQLite 조회 요청')
    st.decide_ai_tool_use(rid,'approved','로컬 조회 1회 승인')
    return rid


def test_actual_company_query_persists_and_is_immutable(office):
    st,e,company,_=office
    st.save_company('실제 회사','실제 설명','실제 운영 목표')
    rid=approved(st,e,company,'real_company')
    result=st.execute_approved_local_read_tool(rid)
    assert result['result']['company_name']=='실제 회사'
    assert result['result']['real_revenue_verified'] is False
    assert not result['already_executed'] and not result['external_action_performed']
    assert st.execute_approved_local_read_tool(rid)['already_executed']
    st.logout()
    fresh=LocalStore(st.path)
    fresh.login('owner','local-tool-password')
    history=fresh.approved_local_read_tool_history()
    assert len(history)==1 and history[0]['sha256']==result['sha256']
    with fresh._connect() as con:
        with pytest.raises(sqlite3.DatabaseError):
            con.execute('UPDATE aiwack_approved_tool_executions SET result_json=?',('{}',))
        with pytest.raises(sqlite3.DatabaseError):
            con.execute('DELETE FROM aiwack_approved_tool_executions')


def test_actual_goal_query_and_two_sessions_are_exactly_once(office):
    st,e,_,goals=office
    st.add_goal('실제 목표 하나','')
    rid=approved(st,e,goals,'real_goals')
    other=LocalStore(st.path)
    other.login('owner','local-tool-password')
    with ThreadPoolExecutor(max_workers=2) as pool:
        a,b=list(pool.map(lambda s:s.execute_approved_local_read_tool(rid),[st,other]))
    assert a['execution_id']==b['execution_id']
    assert sorted([a['already_executed'],b['already_executed']])==[False,True]
    assert a['result']['goals'][0]['title']=='실제 목표 하나'
    assert len(st.approved_local_read_tool_history())==1


def test_permission_revocation_and_pending_or_denied_block(office):
    st,e,company,_=office
    pending=st.request_ai_tool_use('pending_real',company,e,'미승인')
    with pytest.raises(PermissionError):st.execute_approved_local_read_tool(pending)
    st.decide_ai_tool_use(pending,'denied','반려')
    with pytest.raises(PermissionError):st.execute_approved_local_read_tool(pending)
    rid=approved(st,e,company,'approved_then_revoked')
    st.save_employee_access(e,[],[])
    with pytest.raises(PermissionError):st.execute_approved_local_read_tool(rid)
    assert not st.approved_local_read_tool_history()


def test_unimplemented_tool_never_executes_even_if_approved(office):
    st,e,_,_=office
    st.save_employee_access(e,['documents:draft'],['local_document_drafter'])
    tool=st.register_ai_tool('local_document_drafter','문서 후보','file','후보','documents:draft')
    rid=approved(st,e,tool,'document_no_execute')
    with pytest.raises(PermissionError,match='회사/목표'):
        st.execute_approved_local_read_tool(rid)


def test_emergency_stop_and_invalid_request_fail_closed(office):
    st,e,company,_=office
    rid=approved(st,e,company,'stop_tool')
    st.emergency_stop_local(True,'관리자 비상정지')
    with pytest.raises(PermissionError):st.execute_approved_local_read_tool(rid)
    for invalid in (None,True,0,'1',-1):
        with pytest.raises(ValueError):st.execute_approved_local_read_tool(invalid)
