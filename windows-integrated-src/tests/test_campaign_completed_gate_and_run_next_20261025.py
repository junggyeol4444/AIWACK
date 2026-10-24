"""30업무 완료 반환 전 승인/15부서/30호출 증빙 재검사 계약."""
from __future__ import annotations

import pytest

from desktop import company_campaign_resume_gate as gate
from desktop import company_wide_campaign as wide


class _Completed:
    def require_permission(self, permission):
        assert permission == 'company:manage'

    def read_full_company_campaign(self, campaign_id):
        return {'id': campaign_id, 'state': 'approved',
                'steps': [{'ordinal': i, 'task_id': 100+i, 'task_status': 'done'}
                          for i in range(1, 31)]}

    def verified_full_company_progress(self, campaign_id):
        return {'campaign_id': campaign_id, 'state': 'approved',
                'total_tasks': 30, 'verified_completed_tasks': 30,
                'verified_genuine_prefix_tasks': 30,
                'verified_distinct_departments': 15,
                'verified_chief_model_call_links': 30,
                'next_task_id': None,
                'all_30_tasks_evidence_verified': True,
                'all_30_chief_model_call_links_verified': True}


@pytest.mark.parametrize('key,value', [
    ('state', 'draft'), ('total_tasks', 29),
    ('verified_distinct_departments', 14),
    ('verified_chief_model_call_links', 29),
    ('next_task_id', 129),
    ('all_30_tasks_evidence_verified', False),
    ('all_30_chief_model_call_links_verified', False),
])
def test_completed_gate_rejects_incomplete_audit(key, value):
    class Tampered(_Completed):
        def verified_full_company_progress(self, campaign_id):
            data = super().verified_full_company_progress(campaign_id)
            data[key] = value
            return data
    result = gate.snapshot(Tampered(), 8)
    assert result['state'] == 'blocked'
    assert result['read_only'] is True


def test_completed_gate_accepts_only_full_local_provenance():
    result = gate.snapshot(_Completed(), 8)
    assert result['state'] == 'completed'
    assert result['executed'] is False
    assert result['automatically_retried'] is False


def test_run_next_completed_path_rechecks_gate(monkeypatch):
    store = _Completed()
    monkeypatch.setattr(wide, 'read',
                        lambda obj, cid: obj.read_full_company_campaign(cid))
    monkeypatch.setattr(wide, 'verified_progress',
                        lambda obj, cid: obj.verified_full_company_progress(cid))
    result = wide.run_next(store, 8, require_genuine_provenance=True)
    assert result == {'completed': True, 'remaining': 0}


def test_run_next_never_reports_success_for_missing_chief_link(monkeypatch):
    class Missing(_Completed):
        def verified_full_company_progress(self, campaign_id):
            result = super().verified_full_company_progress(campaign_id)
            result['verified_chief_model_call_links'] = 29
            return result
    store = Missing()
    monkeypatch.setattr(wide, 'read',
                        lambda obj, cid: obj.read_full_company_campaign(cid))
    monkeypatch.setattr(wide, 'verified_progress',
                        lambda obj, cid: obj.verified_full_company_progress(cid))
    with pytest.raises(ValueError, match='완료 증빙 재검사 실패'):
        wide.run_next(store, 8, require_genuine_provenance=True)
