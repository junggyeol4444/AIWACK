"""Stage52 policy preflight is a record, never a capability to execute."""
import sqlite3
from concurrent.futures import ThreadPoolExecutor
import pytest
from desktop.storage import LocalStore, AuthenticationError


@pytest.fixture
def store(tmp_path):
    st=LocalStore(tmp_path/'tools_52.sqlite3')
    st.setup_owner('owner52','stage52-test-password')
    return st


def env(st, *, key='candidate_reader', capability='company:read'):
    employee=st.add_employee_draft('employee52','테스트 직원')
    tool=st.register_ai_tool(key,'내부 읽기 후보','file','로컬 실행이 연결되지 않은 후보',capability)
    return employee,tool


def req(st,e,t,key='request_52'):
    return st.request_ai_tool_use(key,t,e,'회사 자료 조회 사전 검사')


def test_unapproved_is_denied_and_records_persist(store):
    e,t=env(store)
    r=req(store,e,t)
    assert store.check_ai_tool_use(r)=={'allowed':False,'reason':'관리자 승인이 없습니다.','execution_performed':False}
    assert store.read_ai_tool_use_request(r)['status']=='pending'
    assert [v['event'] for v in store.ai_tool_use_audit(r)]==['requested']
    store.logout()
    again=LocalStore(store.path)
    again.login('owner52','stage52-test-password')
    assert again.read_ai_tool_use_request(r)['purpose']=='회사 자료 조회 사전 검사'


def test_approval_checks_employee_capability_and_revocation(store):
    e,t=env(store)
    r=req(store,e,t)
    with pytest.raises(PermissionError):store.decide_ai_tool_use(r,'approved','검토 완료')
    assert store.read_ai_tool_use_request(r)['status']=='pending'
    store.save_employee_access(e,['company:read'],[])
    assert store.decide_ai_tool_use(r,'approved','운영자 별도 승인')
    assert store.check_ai_tool_use(r)['allowed'] is True
    assert store.check_ai_tool_use(r)['execution_performed'] is False
    store.save_employee_access(e,[],[])
    assert store.check_ai_tool_use(r)['allowed'] is False
    assert len(store.ai_tool_use_audit(r))==2


def test_builtin_tool_also_requires_explicit_tool_grant(store):
    e,t=env(store,key='local_company_reader')
    r=req(store,e,t)
    store.save_employee_access(e,['company:read'],[])
    with pytest.raises(PermissionError,match='도구 허가'):store.decide_ai_tool_use(r,'approved','검증')
    store.save_employee_access(e,['company:read'],['local_company_reader'])
    assert store.decide_ai_tool_use(r,'approved','명시적 승인')
    assert store.check_ai_tool_use(r)['allowed']
    store.save_employee_access(e,['company:read'],[])
    assert not store.check_ai_tool_use(r)['allowed']


def test_unset_capability_fails_closed(store):
    e,t=env(store,capability='')
    r=req(store,e,t)
    store.save_employee_access(e,['company:read'],[])
    with pytest.raises(PermissionError,match='필수 직원 권한'):store.decide_ai_tool_use(r,'approved','승인 시도')
    assert store.read_ai_tool_use_request(r)['status']=='pending'


def test_reject_wrong_builtin_requirement(store):
    e,t=env(store,key='local_company_reader',capability='goals:read')
    store.save_employee_access(e,['goals:read'],[])
    r=req(store,e,t)
    with pytest.raises(PermissionError,match='충돌'):store.decide_ai_tool_use(r,'approved','결정')


def test_denial_final_and_audited(store):
    e,t=env(store)
    r=req(store,e,t)
    assert store.decide_ai_tool_use(r,'denied','권한 외 작업')
    assert not store.check_ai_tool_use(r)['allowed']
    with pytest.raises(ValueError):store.decide_ai_tool_use(r,'approved','번복')
    assert [x['event'] for x in store.ai_tool_use_audit(r)]==['requested','denied']


def test_inactive_employee_blocks_approval_and_preflight(store):
    e,t=env(store)
    r=req(store,e,t)
    store.save_employee_access(e,['company:read'],[])
    store.set_employee_inactive(e)
    with pytest.raises(PermissionError):store.decide_ai_tool_use(r,'approved','승인 불가')


def test_archived_tool_blocks_and_existing_approval_becomes_invalid(store):
    e,t=env(store)
    store.save_employee_access(e,['company:read'],[])
    r=req(store,e,t)
    store.decide_ai_tool_use(r,'approved','사전 승인')
    store.retire_registered_ai_tool(t,'안전 이슈로 보관')
    assert not store.check_ai_tool_use(r)['allowed']
    with pytest.raises(ValueError):req(store,e,t,'request_other')


def test_invalid_requests_and_decisions(store):
    e,t=env(store)
    for key in ('', 'x', 'has spaces','../invalid',None,22,'x'*101):
        with pytest.raises(ValueError):req(store,e,t,key)
    for employee in (-1,True,0,99999):
        with pytest.raises(ValueError):req(store,employee,t,'bad_employee')
    with pytest.raises(ValueError):req(store,e,999999)
    r=req(store,e,t)
    with pytest.raises(ValueError):req(store,e,t)
    for status in ('granted','',None,1):
        with pytest.raises(ValueError):store.decide_ai_tool_use(r,status,'사유')
    with pytest.raises(ValueError):store.decide_ai_tool_use(r,'denied','')
    assert store.read_ai_tool_use_request(r)['status']=='pending'
    for ident in (0,False,-1,'1',9999):
        with pytest.raises(ValueError):store.check_ai_tool_use(ident)
    with pytest.raises(ValueError):store.list_ai_tool_use_requests(limit=0)


def test_owner_login_required_for_all_operations(store):
    e,t=env(store)
    r=req(store,e,t)
    store.logout()
    operations=(lambda:store.request_ai_tool_use('another_key',t,e,'목적'),
                lambda:store.list_ai_tool_use_requests(),
                lambda:store.decide_ai_tool_use(r,'denied','거부'),
                lambda:store.check_ai_tool_use(r),
                lambda:store.read_ai_tool_use_request(r),
                lambda:store.ai_tool_use_audit(r))
    for f in operations:
        with pytest.raises(AuthenticationError):f()


def test_sql_protects_audit_and_final_decision(store):
    e,t=env(store)
    r=req(store,e,t)
    store.decide_ai_tool_use(r,'denied','거부')
    with sqlite3.connect(store.path) as con:
        statements=(('DELETE FROM tool_use_requests WHERE id=?',(r,)),
                    ('UPDATE tool_use_requests SET status="approved" WHERE id=?',(r,)),
                    ('UPDATE tool_use_audit SET detail="tamper" WHERE request_id=?',(r,)),
                    ('DELETE FROM tool_use_audit WHERE request_id=?',(r,)))
        for sql,params in statements:
            with pytest.raises(sqlite3.IntegrityError):con.execute(sql,params)


def test_concurrent_decision_exactly_one(store):
    e,t=env(store)
    r=req(store,e,t)
    def do_decide(_):
        try:
            store.decide_ai_tool_use(r,'denied','동시 처리')
            return 'ok'
        except ValueError:
            return 'duplicate'
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(do_decide,range(2)))==['duplicate','ok']
    assert len(store.ai_tool_use_audit(r))==2


def test_concurrent_request_key_exactly_one(store):
    e,t=env(store)
    def do_request(_):
        try:
            req(store,e,t)
            return 'ok'
        except ValueError:
            return 'duplicate'
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(do_request,range(2)))==['duplicate','ok']
    assert len(store.list_ai_tool_use_requests())==1


def test_no_network_or_process_spawn(monkeypatch,store):
    import socket,subprocess
    def blocked(*args,**kwargs):raise AssertionError('external operation was attempted')
    monkeypatch.setattr(socket.socket,'connect',blocked)
    monkeypatch.setattr(subprocess,'Popen',blocked)
    e,t=env(store)
    store.save_employee_access(e,['company:read'],[])
    r=req(store,e,t)
    store.decide_ai_tool_use(r,'approved','승인')
    assert store.check_ai_tool_use(r)['allowed']
