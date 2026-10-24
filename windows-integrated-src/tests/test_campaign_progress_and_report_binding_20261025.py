"""30업무 재개 및 총괄 최종보고의 원본 타입·집계 연결 회귀.

모의 저장소를 통한 코드 계약 검사이며 실제 GGUF/Windows 실기 검증은 아니다.
"""
from __future__ import annotations

import pytest

from desktop import company_campaign_chain_integrity as chain
from desktop import company_campaign_plan_provenance as provenance
from desktop import company_campaign_resume_gate as resume


class _ResumeStore:
    def __init__(self):
        self.progress = {
            'campaign_id': 1, 'state': 'approved', 'total_tasks': 30,
            'verified_completed_tasks': 2, 'verified_genuine_prefix_tasks': 2,
            'verified_distinct_workers': 2, 'verified_distinct_departments': 2,
            'verified_chief_model_call_links': 2, 'next_task_id': 103,
            'all_30_tasks_evidence_verified': False,
            'all_30_chief_model_call_links_verified': False,
        }

    def require_permission(self, permission):
        assert permission == 'company:manage'

    def read_full_company_campaign(self, campaign_id):
        return {'id': campaign_id, 'state': 'approved',
                'steps': [{'ordinal': index, 'task_id': 100 + index,
                           'task_status': 'done' if index <= 2 else 'todo'}
                          for index in range(1, 31)]}

    def verified_full_company_progress(self, campaign_id):
        return self.progress

    def list_task_runs(self, task_id):
        return []

    def list_task_artifacts(self, task_id):
        return []


def test_consistent_pending_progress_is_ready():
    result = resume.snapshot(_ResumeStore(), 1)
    assert result['state'] == 'ready'
    assert result['read_only'] is True


@pytest.mark.parametrize('field,value', [
    ('state', 'rejected'), ('total_tasks', 29),
    ('total_tasks', 30.0), ('total_tasks', True),
    ('all_30_tasks_evidence_verified', True),
    ('all_30_chief_model_call_links_verified', True),
    ('verified_distinct_workers', 3),
    ('verified_distinct_workers', 2.0),
    ('verified_distinct_departments', 3),
    ('verified_distinct_departments', True),
    ('verified_chief_model_call_links', 3),
    ('verified_chief_model_call_links', 2.0),
    ('next_task_id', 103.0), ('next_task_id', True),
])
def test_pending_progress_contradiction_blocks_resume(field, value):
    store = _ResumeStore()
    store.progress[field] = value
    result = resume.snapshot(store, 1)
    assert result['state'] == 'blocked'
    assert result['executed'] is False
    with pytest.raises(ValueError, match='재개 점검 실패'):
        resume.require_next(store, 1, 103)


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
            'chief_employee_id': 1, 'chief_model_call_id': 22,
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
        'chief_employee_id': 1, 'snapshot_sha256': 'd' * 64,
        'failed_attempts_model_provenance_checked': True,
        'sqlite_model_call_audit_checked': True,
    }


def test_valid_report_and_dossier_link(monkeypatch):
    monkeypatch.setattr(provenance, 'snapshot', lambda *args: _plan())
    receipt = chain.snapshot(_ChainStore(), 1)
    assert receipt['chief_final_report_id'] == 21
    assert receipt['owner_approved_dossier_id'] == 25
    assert receipt['final_T01_T20_acceptance_passed'] is False


@pytest.mark.parametrize('field,value', [
    ('campaign_id', True), ('campaign_id', 1.0),
    ('chief_employee_id', True), ('chief_employee_id', 1.0),
])
def test_report_identity_must_be_exact_integer(monkeypatch, field, value):
    monkeypatch.setattr(provenance, 'snapshot', lambda *args: _plan())
    store = _ChainStore()
    store.report[field] = value
    with pytest.raises(ValueError, match='총괄 실제 모델 최종보고'):
        chain.snapshot(store, 1)


@pytest.mark.parametrize('value', [True, 1.0, '1'])
def test_dossier_campaign_id_must_be_exact_integer(monkeypatch, value):
    monkeypatch.setattr(provenance, 'snapshot', lambda *args: _plan())
    store = _ChainStore()
    store.dossier['campaign_id'] = value
    with pytest.raises(ValueError, match='최종 인계'):
        chain.snapshot(store, 1)
