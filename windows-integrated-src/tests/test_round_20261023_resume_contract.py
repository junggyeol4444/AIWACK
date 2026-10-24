"""30업무 승인 원본 검증 계약: 실제 Windows/GGUF 성공 증빙이 아닌 SQLite 의존성 없는 단위검사."""
import pytest
from desktop.company_campaign_resume_gate import require_next, snapshot


class PersistedState:
    def __init__(self, completed=0, genuine=0, prior=False):
        self.completed, self.genuine, self.prior = completed, genuine, prior
        self.owner = True

    def require_permission(self, name):
        assert name == 'company:manage'
        if not self.owner:
            raise PermissionError('관리자 로그인 필요')

    def read_full_company_campaign(self, campaign_id):
        return {'id': campaign_id, 'state': 'approved', 'steps': [
            {'ordinal': i, 'task_id': 100+i,
             'task_status': 'done' if i <= self.completed else 'todo'}
            for i in range(1, 31)]}

    def verified_full_company_progress(self, campaign_id):
        return {'campaign_id': campaign_id,
                'verified_completed_tasks': self.completed,
                'verified_genuine_prefix_tasks': self.genuine,
                'next_task_id': None if self.completed == 30 else 101+self.completed,
                'all_30_tasks_evidence_verified': self.completed == 30,
                'all_30_chief_model_call_links_verified': self.genuine == 30}

    def list_task_runs(self, task_id):
        return [{'status': 'success'}] if self.prior else []

    def list_task_artifacts(self, task_id):
        return []


def test_new_campaign_may_run_first_task_only():
    assert require_next(PersistedState(), 1, 101)['next_ordinal'] == 1
    with pytest.raises(ValueError, match='재개 점검 실패'):
        require_next(PersistedState(), 1, 102)


def test_actual_gguf_provenance_mandatory_unless_explicit_legacy_mode():
    state = PersistedState(completed=5, genuine=0)
    assert snapshot(state, 2)['state'] == 'blocked'
    assert snapshot(state, 2, require_genuine_provenance=False)['state'] == 'ready'
    assert require_next(state, 2, 106, require_genuine_provenance=False)['state'] == 'ready'


def test_prior_run_still_blocks_legacy_path():
    state = PersistedState(prior=True)
    with pytest.raises(ValueError, match='기존 실행'):
        require_next(state, 1, 101, require_genuine_provenance=False)


def test_approval_is_never_skipped():
    state = PersistedState(completed=5)
    original = state.verified_full_company_progress
    def wrong_progress(campaign_id):
        data = original(campaign_id)
        data['verified_completed_tasks'] = 4
        return data
    state.verified_full_company_progress = wrong_progress
    assert snapshot(state, 1, require_genuine_provenance=False)['state'] == 'blocked'


def test_permission_and_invalid_campaign_fail_closed():
    state = PersistedState()
    state.owner = False
    with pytest.raises(PermissionError):
        snapshot(state, 1)
    state.owner = True
    for value in (0, True, '1', -1):
        with pytest.raises(ValueError):
            snapshot(state, value)
