"""기존 30업무 최종 단계의 실제 총괄 모델 승인 게이트 계약.

구조/모의 저장소 테스트만 작성. Windows GGUF 실행 성공 증빙이 아니다.
"""
from __future__ import annotations

import pytest

from desktop import company_wide_campaign as wide


class Conn:
    def __init__(self, member):
        self.member = member
    def __enter__(self):
        return self
    def __exit__(self, *args):
        return False
    def execute(self, query, params=()):
        class Cursor:
            def __init__(self, row):
                self.row = row
            def fetchone(self):
                return self.row
        if 'FROM aiwack_wide_campaign_steps s' in query:
            return Cursor(self.member)
        raise AssertionError('예상하지 않은 SQLite 조회: ' + query[:80])


class Store:
    def __init__(self, member=(7, 1, 301, 4, 'approved')):
        self.member = member
    def require_permission(self, permission):
        assert permission == 'company:manage'
    def _connect(self):
        return Conn(self.member)


@pytest.fixture
def genuine_preflight(monkeypatch):
    monkeypatch.setattr(wide, 'initialize', lambda con: None)
    monkeypatch.setattr(wide, '_assert_campaign_plan_matches_genuine_staging',
                        lambda store, con, campaign: None)
    monkeypatch.setattr(wide, '_verified_step_evidence',
                        lambda con, campaign, ordinal, **kwargs:
                        {'artifact_id': 91, 'previous_task_id': 301})
    monkeypatch.setattr(wide, '_verified_chief_model_call_link',
                        lambda con, campaign, ordinal, **kwargs: True)
    progress = {'verified_completed_tasks': 0,
                'verified_genuine_prefix_tasks': 0, 'next_task_id': 301}
    monkeypatch.setattr(wide, 'verified_progress',
                        lambda store, campaign: dict(progress))
    return progress


def test_owner_finalization_preflight_requires_genuine_chief_link(
        monkeypatch, genuine_preflight):
    monkeypatch.setattr(wide, '_verified_chief_model_call_link',
                        lambda *args, **kwargs: False)
    with pytest.raises(ValueError, match='실제 모델 호출'):
        wide.require_campaign_owner_finalization(Store(), 91)


def test_owner_finalization_rejects_wrong_artifact(genuine_preflight):
    with pytest.raises(ValueError, match='원본 불일치'):
        wide.require_campaign_owner_finalization(Store(), 92)


def test_owner_finalization_rejects_nonsequential_step(genuine_preflight):
    genuine_preflight['verified_completed_tasks'] = 1
    with pytest.raises(ValueError, match='순서 불일치'):
        wide.require_campaign_owner_finalization(Store(), 91)


def test_owner_finalization_rejects_unapproved_campaign(genuine_preflight):
    with pytest.raises(ValueError, match='승인되지'):
        wide.require_campaign_owner_finalization(Store((7,1,301,4,'draft')), 91)


def test_owner_finalization_returns_only_verified_single_step(genuine_preflight):
    result = wide.require_campaign_owner_finalization(Store(), 91)
    assert result['task_id'] == 301
    assert result['genuine_chief_model_call_verified'] is True
    assert result['automatic_approval'] is False


def test_non_campaign_artifact_never_finalizes_via_strict_campaign_path(
        monkeypatch, genuine_preflight):
    called = []
    monkeypatch.setattr('desktop.company_operations.finalize_approved_artifact',
                        lambda *args: called.append(args))
    with pytest.raises(ValueError, match='속하지'):
        wide.finalize_campaign_owner_artifact(Store(None), 91)
    assert called == []
