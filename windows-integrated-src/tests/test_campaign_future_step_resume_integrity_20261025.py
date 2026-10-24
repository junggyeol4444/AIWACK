"""30업무 재개 중 후속 실행 흔적 차단 계약(모의 저장소, 실 GGUF 증빙 아님)."""
from __future__ import annotations

import pytest

from desktop.company_campaign_resume_gate import require_next, snapshot


class CampaignStore:
    def __init__(self):
        self.status = {i: ('done' if i <= 2 else 'todo') for i in range(1, 31)}
        self.prior_runs = set()
        self.prior_artifacts = set()

    def require_permission(self, name):
        assert name == 'company:manage'

    def read_full_company_campaign(self, campaign_id):
        return {
            'id': campaign_id, 'state': 'approved',
            'steps': [{'ordinal': i, 'task_id': 100 + i,
                       'task_status': self.status[i]} for i in range(1, 31)]
        }

    def verified_full_company_progress(self, campaign_id):
        return {
            'campaign_id': campaign_id, 'verified_completed_tasks': 2,
            'verified_genuine_prefix_tasks': 2, 'next_task_id': 103,
            'all_30_tasks_evidence_verified': False,
            'all_30_chief_model_call_links_verified': False,
        }

    def list_task_runs(self, task_id):
        return [{'status': 'success'}] if task_id in self.prior_runs else []

    def list_task_artifacts(self, task_id):
        return [{'id': task_id}] if task_id in self.prior_artifacts else []


def test_clean_next_task_still_ready():
    store = CampaignStore()
    result = require_next(store, 8, 103)
    assert result['state'] == 'ready'
    assert result['next_ordinal'] == 3
    assert result['read_only'] is True
    assert result['executed'] is False


@pytest.mark.parametrize('future_status', ['done', 'running', 'failed'])
def test_future_status_blocks_even_when_prefix_matches(future_status):
    store = CampaignStore()
    store.status[5] = future_status
    result = snapshot(store, 8)
    assert result['state'] == 'blocked'
    assert '후속 업무' in result['reason']
    with pytest.raises(ValueError, match='재개 점검 실패'):
        require_next(store, 8, 103)


@pytest.mark.parametrize('field', ['prior_runs', 'prior_artifacts'])
def test_future_model_call_or_artifact_blocks_resume(field):
    store = CampaignStore()
    getattr(store, field).add(111)
    result = snapshot(store, 8)
    assert result['state'] == 'blocked'
    assert '11' in result['reason']
    assert result['automatically_retried'] is False


@pytest.mark.parametrize('invalid_id', [True, 103.0, '103', 0, -1, None])
def test_expected_task_id_must_be_exact_positive_integer(invalid_id):
    with pytest.raises(ValueError, match='업무 번호'):
        require_next(CampaignStore(), 8, invalid_id)


def test_current_task_run_still_blocks_without_auto_retry():
    store = CampaignStore()
    store.prior_runs.add(103)
    result = snapshot(store, 8)
    assert result['state'] == 'blocked'
    assert result['has_prior_execution'] is True
    assert result['automatically_retried'] is False
