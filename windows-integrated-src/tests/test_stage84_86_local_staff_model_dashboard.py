"""Stages84-86 local drafts and refresh-on-demand dashboard, not actual AI staffing."""
import sqlite3
import pytest
from desktop.storage import LocalStore, AuthenticationError
from test_stage78_80_local_commerce import store as base_store

@pytest.fixture
def store(base_store):return base_store


def create_departments(s):
    with s._connect() as c:
        one=c.execute("INSERT INTO company_departments(name) VALUES('Synthetic research')").lastrowid
        two=c.execute("INSERT INTO company_departments(name) VALUES('Synthetic finance')").lastrowid
    return one,two


def fake_model(s):
    with s._connect() as con:
        return con.execute("INSERT INTO ai_local_models(name,backend,executable_path,model_path,max_tokens) VALUES('Fixture local config','llama_cpp','local-example-only','no-real-model.gguf',256)").lastrowid


def test_84_nonexecuting_hiring_draft(store):
    s,order,biz=store
    department,_=create_departments(s)
    a=s.create_local_staffing_draft('staff_plan_001','CREATE_PROFILE_DRAFT',department,'Owner checks this first')
    assert not a['staff_changed'] and not a['agent_launched'] and a['owner_review_pending']
    assert s.create_local_staffing_draft('staff_plan_001','CREATE_PROFILE_DRAFT',department,'Owner checks this first')['duplicate']
    assert s.offline_company_dashboard_snapshot()['employee_profile_count']==0


def test_84_reassignment_draft_no_mutation(store):
    s,order,biz=store
    a,b=create_departments(s)
    with s._connect() as c:
        emp=c.execute("INSERT INTO ai_employee_profiles(employee_key,display_name,department_id) VALUES('fixture_staff','Fixture staff',?)",(a,)).lastrowid
    row=s.create_local_staffing_draft('staff_plan_002','REASSIGN_DRAFT',b,'Reallocate mock workload',emp)
    assert row['employee_id']==emp and not row['staff_changed']
    with s._connect() as c:
        assert c.execute('SELECT department_id FROM ai_employee_profiles WHERE id=?',(emp,)).fetchone()[0]==a
    with pytest.raises(ValueError,match='unchanged'):
        s.create_local_staffing_draft('staff_plan_003','REASSIGN_DRAFT',a,'Not a move',emp)


def test_84_key_conflict_and_invalid_plan(store):
    s,order,biz=store
    department,other=create_departments(s)
    s.create_local_staffing_draft('staff_plan_001','CREATE_PROFILE_DRAFT',department,'Review first')
    with pytest.raises(ValueError,match='conflict'):
        s.create_local_staffing_draft('staff_plan_001','CREATE_PROFILE_DRAFT',other,'Review first')
    with pytest.raises(ValueError):
        s.create_local_staffing_draft('staff_plan_002','CREATE_EMPLOYEE_NOW',department,'Illegal real action')


def test_85_config_only_no_benchmark_or_model_execution(store):
    s,order,biz=store
    model=fake_model(s)
    report=s.local_model_config_comparison()
    assert report['validated_real_model_count']==0
    assert report['comparison_basis']=='CONFIGURATION_ONLY_NOT_SPEED_OR_QUALITY'
    assert report['models'][0]['id']==model and not report['models'][0]['benchmark_verified']
    assert 'executable_path' not in report['models'][0] and 'model_path' not in report['models'][0]


def test_85_model_switch_is_draft_only(store):
    s,order,biz=store
    model=fake_model(s)
    row=s.create_local_model_switch_draft('model_plan_001',model,'OFFLINE_REVIEW_ONLY','Consider local config')
    assert row['real_model_switched'] is False and row['quality_benchmarked'] is False
    assert s.create_local_model_switch_draft('model_plan_001',model,'OFFLINE_REVIEW_ONLY','Consider local config')['duplicate']
    with pytest.raises(ValueError,match='conflict'):
        s.create_local_model_switch_draft('model_plan_001',model,'OWNER_TEST_PROPOSAL','Consider local config')
    with pytest.raises(ValueError):
        s.create_local_model_switch_draft('model_plan_002',model,'ACTIVATE_REAL_MODEL','Unsafe')
    with pytest.raises(ValueError):
        s.create_local_model_switch_draft('model_plan_003',9999,'OFFLINE_REVIEW_ONLY','Invalid ID')


def test_86_dashboard_is_snapshot_without_external_data(store):
    s,order,biz=store
    report=s.offline_company_dashboard_snapshot()
    assert report['snapshot_only'] is True
    assert report['live_monitoring'] is False
    assert report['real_sales_verified'] is False
    assert report['model_inference_running'] is False
    assert report['no_side_effects'] is True
    assert any(x['business_id']==biz for x in report['hypothetical_budget']['businesses'])


def test_84_85_append_only_integrity(store):
    s,order,biz=store
    dept,_=create_departments(s)
    model=fake_model(s)
    s.create_local_staffing_draft('staff_plan_001','CREATE_PROFILE_DRAFT',dept,'Safe')
    s.create_local_model_switch_draft('model_plan_001',model,'OFFLINE_REVIEW_ONLY','Safe')
    with s._connect() as con:
        with pytest.raises(sqlite3.DatabaseError):
            con.execute('DELETE FROM local_staffing_drafts')
        with pytest.raises(sqlite3.DatabaseError):
            con.execute('UPDATE local_model_switch_drafts SET digest=?',('bad',))
        con.execute('DROP TRIGGER local_staffing_drafts_no_update')
        con.execute("UPDATE local_staffing_drafts SET note='tampered'")
    with pytest.raises(ValueError,match='hash audit'):s.local_staffing_drafts()


def test_85_model_audit_tamper(store):
    s,order,biz=store
    model=fake_model(s)
    s.create_local_model_switch_draft('model_plan_001',model,'OFFLINE_REVIEW_ONLY','Safe')
    with s._connect() as con:
        con.execute('DROP TRIGGER local_model_switch_drafts_no_update')
        con.execute("UPDATE local_model_switch_drafts SET note='tampered'")
    with pytest.raises(ValueError,match='hash audit'):s.local_model_switch_drafts()


def test_84_86_permission_and_persistence(store):
    s,order,biz=store
    department,_=create_departments(s)
    s.create_local_staffing_draft('staff_plan_001','CREATE_PROFILE_DRAFT',department,'Local only')
    later=LocalStore(s.path)
    later.login('owner78','not-a-production-password')
    assert len(later.local_staffing_drafts())==1
    later.logout()
    for action in (later.local_staffing_drafts,later.local_model_config_comparison,later.local_model_switch_drafts,
                   later.offline_company_dashboard_snapshot,
                   lambda:later.create_local_staffing_draft('staff_plan_002','CREATE_PROFILE_DRAFT',department,'Denied')):
        with pytest.raises(AuthenticationError):action()
