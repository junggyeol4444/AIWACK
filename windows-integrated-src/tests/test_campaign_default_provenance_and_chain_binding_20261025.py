"""기존 31AI/30업무 원본 교차결합과 기본 출처 검사 회귀 계약.

합성 SQLite 조회 반환값으로 실패 차단만 검증하며 실제 GGUF/Windows 인수시험이 아니다.
"""
from __future__ import annotations

import inspect

import pytest

from desktop import company_campaign_chain_integrity as chain
from desktop import company_campaign_plan_provenance as plan_provenance
from desktop import company_wide_campaign as wide


class _EvidenceStore:
    def __init__(self):
        self.plan = {
            'campaign_id': 7, 'plan_state': 'approved',
            'verified_plan_groups': 5, 'verified_departments': 15,
            'verified_chief_call_count': 5,
            'source_task_id': 91, 'chief_employee_id': 12,
            'snapshot_sha256': 'a' * 64,
            'failed_attempts_model_provenance_checked': True,
            'sqlite_model_call_audit_checked': True,
        }
        self.progress = {
            'campaign_id': 7, 'state': 'approved',
            'verified_completed_tasks': 30, 'verified_distinct_departments': 15,
            'verified_distinct_workers': 30, 'verified_genuine_prefix_tasks': 30,
            'verified_chief_model_call_links': 30,
            'all_30_tasks_evidence_verified': True,
            'all_30_chief_model_call_links_verified': True,
        }
        self.report = {
            'campaign_id': 7, 'decision': 'accepted',
            'all_30_model_call_and_owner_review_audits_verified': True,
            'id': 41, 'chief_model_call_id': 77, 'chief_employee_id': 12,
            'report_sha256': 'b' * 64, 'evidence_sha256': 'c' * 64,
        }
        self.dossier = {
            'campaign_id': 7, 'owner_final_approved': True,
            'verified_approved_employee_steps': 30,
            'final_report_id': 41, 'id': 60,
            'file_sha256': 'd' * 64, 'byte_count': 4096,
        }

    def require_permission(self, permission):
        assert permission == 'company:manage'

    def verified_full_company_progress(self, campaign_id):
        return self.progress

    def find_campaign_final_report(self, campaign_id):
        return self.report

    def find_owner_approved_final_dossier_by_campaign(self, campaign_id):
        return self.dossier


@pytest.fixture
def original(monkeypatch):
    store = _EvidenceStore()
    monkeypatch.setattr(plan_provenance, 'snapshot',
                        lambda _store, campaign_id: store.plan)
    return store


def test_local_receipt_requires_all_31_ai_original_links(original):
    receipt = chain.snapshot(original, 7)
    assert receipt['verified_approved_tasks'] == 30
    assert receipt['verified_departments'] == 15
    assert receipt['independent_gguf_binary_verified'] is False
    assert chain.verify_receipt(original, 7, receipt)['verified'] is True


@pytest.mark.parametrize('section,key,value', [
    ('plan', 'source_task_id', True),
    ('plan', 'chief_employee_id', 0),
    ('plan', 'snapshot_sha256', 'not-a-digest'),
    ('plan', 'verified_chief_call_count', True),
    ('plan', 'failed_attempts_model_provenance_checked', False),
    ('progress', 'verified_distinct_workers', 29),
    ('report', 'chief_employee_id', 13),
    ('report', 'chief_model_call_id', True),
    ('report', 'report_sha256', 'g' * 64),
    ('report', 'evidence_sha256', ''),
    ('dossier', 'id', True),
    ('dossier', 'file_sha256', '0' * 63),
    ('dossier', 'byte_count', 1024 * 1024 + 1),
])
def test_cross_campaign_provenance_mismatch_fails_closed(original, section, key, value):
    getattr(original, section)[key] = value
    with pytest.raises(ValueError):
        chain.snapshot(original, 7)


def test_native_run_next_defaults_to_genuine_chief_call_provenance():
    parameter = inspect.signature(wide.run_next).parameters['require_genuine_provenance']
    assert parameter.default is True


def test_native_run_next_rejects_non_boolean_provenance_without_execution():
    with pytest.raises(ValueError, match='참/거짓'):
        wide.run_next(object(), 7, require_genuine_provenance='false')

def test_canonical_receipt_json_roundtrip_against_current_sources(original):
    raw = chain.export_receipt_json(original, 7)
    assert raw.endswith('\n')
    assert chain.verify_receipt_json(original, 7, raw)['verified'] is True
    original.report['evidence_sha256'] = 'e' * 64
    with pytest.raises(ValueError, match='현재 승인 원본'):
        chain.verify_receipt_json(original, 7, raw)


@pytest.mark.parametrize('change', [
    lambda raw: raw.replace('"campaign_id":7', '"campaign_id":7,"campaign_id":7'),
    lambda raw: raw.replace('"verified_departments":15', '"verified_departments":NaN'),
    lambda raw: raw.replace('"campaign_id":7', '"campaign_id":8'),
    lambda raw: raw.replace('"campaign_id":7', '"campaign_id":7,"unapproved":true'),
    lambda raw: raw + '{',
])
def test_receipt_json_rejects_corruption_without_mutating_sources(original, change):
    raw = chain.export_receipt_json(original, 7)
    with pytest.raises(ValueError):
        chain.verify_receipt_json(original, 7, change(raw))


def test_receipt_json_rejects_oversized_and_non_string(original):
    with pytest.raises(ValueError):
        chain.verify_receipt_json(original, 7, ' ' * 65537)
    with pytest.raises(ValueError):
        chain.verify_receipt_json(original, 7, {'campaign_id': 7})
