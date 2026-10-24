"""실제 승인 원본의 숫자 식별자·집계 타입 회귀 계약 (모의 저장소만 사용)."""
from __future__ import annotations

import copy

import pytest

from desktop import company_campaign_resume_gate as resume
from desktop import company_campaign_chain_integrity as chain
from desktop import company_campaign_plan_provenance as provenance


class _ResumeStore:
    def require_permission(self, permission):
        assert permission == 'company:manage'

    def read_full_company_campaign(self, campaign_id):
        return {'id': campaign_id, 'state': 'approved',
                'steps': [{'ordinal': i, 'task_id': 100 + i, 'task_status': 'done'}
                          for i in range(1, 31)]}

    def verified_full_company_progress(self, campaign_id):
        return {'campaign_id': campaign_id, 'state': 'approved',
                'verified_genuine_prefix_tasks': 30,
                'verified_completed_tasks': 30, 'total_tasks': 30,
                'verified_distinct_departments': 15,
                'verified_distinct_workers': 30,
                'verified_chief_model_call_links': 30,
                'all_30_tasks_evidence_verified': True,
                'all_30_chief_model_call_links_verified': True,
                'next_task_id': None}


@pytest.mark.parametrize('field,value', [
    ('id', True), ('id', 1.0), ('ordinal', True), ('ordinal', 1.0),
])
def test_resume_rejects_equal_but_non_integer_identifiers(field, value):
    class Tampered(_ResumeStore):
        def read_full_company_campaign(self, campaign_id):
            data = super().read_full_company_campaign(campaign_id)
            if field == 'id':
                data['id'] = value
            else:
                data['steps'][0]['ordinal'] = value
            return data

    with pytest.raises(ValueError, match='순서·배정 원본'):
        resume.snapshot(Tampered(), 1)


@pytest.mark.parametrize('value', [True, 1.0, '1'])
def test_resume_rejects_progress_campaign_id_type(value):
    class Tampered(_ResumeStore):
        def verified_full_company_progress(self, campaign_id):
            data = super().verified_full_company_progress(campaign_id)
            data['campaign_id'] = value
            return data

    with pytest.raises(ValueError, match='협업 번호'):
        resume.snapshot(Tampered(), 1)


class _ChainStore:
    def __init__(self):
        self.progress = {
            'campaign_id': 1, 'state': 'approved',
            'verified_completed_tasks': 30,
            'verified_distinct_departments': 15,
            'verified_distinct_workers': 30,
            'verified_genuine_prefix_tasks': 30,
            'verified_chief_model_call_links': 30,
            'all_30_tasks_evidence_verified': True,
            'all_30_chief_model_call_links_verified': True,
        }
        self.report = {
            'campaign_id': 1, 'decision': 'accepted', 'id': 21,
            'chief_employee_id': 4, 'chief_model_call_id': 22,
            'report_sha256': 'a' * 64, 'evidence_sha256': 'b' * 64,
            'all_30_model_call_and_owner_review_audits_verified': True,
        }
        self.dossier = {
            'campaign_id': 1, 'owner_final_approved': True,
            'verified_approved_employee_steps': 30, 'final_report_id': 21,
            'id': 25, 'file_sha256': 'c' * 64, 'byte_count': 200,
        }

    def require_permission(self, permission):
        assert permission == 'company:manage'

    def verified_full_company_progress(self, campaign_id):
        return self.progress

    def find_campaign_final_report(self, campaign_id):
        return self.report

    def find_owner_approved_final_dossier_by_campaign(self, campaign_id):
        return self.dossier


def _plan():
    return {
        'campaign_id': 1, 'plan_state': 'approved',
        'verified_plan_groups': 5, 'verified_departments': 15,
        'verified_chief_call_count': 5, 'source_task_id': 3,
        'chief_employee_id': 4, 'snapshot_sha256': 'd' * 64,
        'failed_attempts_model_provenance_checked': True,
        'sqlite_model_call_audit_checked': True,
    }


def test_chain_valid_integer_counts_are_read_only(monkeypatch):
    monkeypatch.setattr(provenance, 'snapshot', lambda store, campaign_id: _plan())
    result = chain.snapshot(_ChainStore(), 1)
    assert result['verified_approved_tasks'] == 30
    assert result['final_T01_T20_acceptance_passed'] is False


@pytest.mark.parametrize('field,value', [
    ('verified_completed_tasks', 30.0),
    ('verified_distinct_departments', 15.0),
    ('verified_distinct_workers', 30.0),
    ('verified_genuine_prefix_tasks', 30.0),
    ('verified_chief_model_call_links', 30.0),
    ('campaign_id', True),
])
def test_chain_rejects_progress_type_confusion(monkeypatch, field, value):
    monkeypatch.setattr(provenance, 'snapshot', lambda store, campaign_id: _plan())
    store = _ChainStore()
    store.progress[field] = value
    with pytest.raises(ValueError, match='30업무'):
        chain.snapshot(store, 1)


@pytest.mark.parametrize('field,value', [
    ('verified_plan_groups', 5.0),
    ('verified_departments', 15.0),
    ('campaign_id', True),
])
def test_chain_rejects_plan_type_confusion(monkeypatch, field, value):
    plan = copy.deepcopy(_plan())
    plan[field] = value
    monkeypatch.setattr(provenance, 'snapshot', lambda store, campaign_id: plan)
    with pytest.raises(ValueError, match='5그룹'):
        chain.snapshot(_ChainStore(), 1)


@pytest.mark.parametrize('field,value', [
    ('verified_approved_employee_steps', 30.0),
    ('final_report_id', 21.0),
])
def test_chain_rejects_dossier_type_confusion(monkeypatch, field, value):
    monkeypatch.setattr(provenance, 'snapshot', lambda store, campaign_id: _plan())
    store = _ChainStore()
    store.dossier[field] = value
    with pytest.raises(ValueError, match='최종 인계'):
        chain.snapshot(store, 1)
