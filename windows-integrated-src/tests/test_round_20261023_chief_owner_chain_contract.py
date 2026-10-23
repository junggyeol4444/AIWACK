"""누적 원본 연결과 실GGUF/Windows 과장 방지 계약 검사. 실제 모델 호출 없음."""
import copy
import pytest
from desktop import company_campaign_chain_integrity as chain
from desktop import company_campaign_plan_provenance as provenance

class Store:
    def __init__(self):
        self.progress={'campaign_id':5,'state':'approved','verified_completed_tasks':30,
            'verified_distinct_departments':15,'verified_genuine_prefix_tasks':30,
            'verified_chief_model_call_links':30,'all_30_tasks_evidence_verified':True,
            'all_30_chief_model_call_links_verified':True}
        self.report={'id':100,'campaign_id':5,'decision':'accepted',
            'all_30_model_call_and_owner_review_audits_verified':True,
            'chief_model_call_id':777,'report_sha256':'a'*64,'evidence_sha256':'b'*64}
        self.dossier={'id':900,'campaign_id':5,'owner_final_approved':True,
            'verified_approved_employee_steps':30,'final_report_id':100,'file_sha256':'c'*64}
    def require_permission(self,k): assert k=='company:manage'
    def verified_full_company_progress(self,c):return copy.deepcopy(self.progress)
    def find_campaign_final_report(self,c):return copy.deepcopy(self.report)
    def find_owner_approved_final_dossier_by_campaign(self,c):return copy.deepcopy(self.dossier)

@pytest.fixture
def original_plan(monkeypatch):
    plan={'campaign_id':5,'plan_state':'approved','verified_plan_groups':5,
        'verified_departments':15,'verified_chief_call_count':5,
        'source_task_id':2,'chief_employee_id':1,'snapshot_sha256':'e'*64}
    monkeypatch.setattr(provenance,'snapshot',lambda *_:copy.deepcopy(plan))

def test_no_independent_windows_or_payment_success_claim(original_plan):
    output=chain.snapshot(Store(),5)
    assert output['verified_approved_tasks']==30
    assert output['chief_final_report_id']==100
    assert output['owner_approved_dossier_id']==900
    assert len(output['receipt_sha256'])==64
    assert output['independent_gguf_binary_verified'] is False
    assert output['physical_windows_10_11_gui_verified'] is False
    assert output['uninterrupted_24h_operation_verified'] is False
    assert output['external_pg_bank_transactions_verified'] is False
    assert output['final_T01_T20_acceptance_passed'] is False

@pytest.mark.parametrize('section,key,value',[
    ('progress','verified_completed_tasks',29),('progress','campaign_id',6),
    ('progress','verified_genuine_prefix_tasks',29),
    ('progress','verified_chief_model_call_links',29),
    ('progress','all_30_chief_model_call_links_verified',False),
    ('report','campaign_id',6),('report','decision','pending'),
    ('report','all_30_model_call_and_owner_review_audits_verified',False),
    ('dossier','campaign_id',6),('dossier','owner_final_approved',False),
    ('dossier','verified_approved_employee_steps',29),('dossier','final_report_id',101)])
def test_wrong_campaign_incomplete_chief_or_owner_audit_is_rejected(original_plan,section,key,value):
    store=Store()
    getattr(store,section)[key]=value
    with pytest.raises(ValueError):chain.snapshot(store,5)

@pytest.mark.parametrize('campaign_id',[True,0,-1,'5',5.0])
def test_wrong_id_rejected(original_plan,campaign_id):
    with pytest.raises(ValueError):chain.snapshot(Store(),campaign_id)
