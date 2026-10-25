"""실제 GGUF 실행을 흉내 내지 않는 순수 읽기/중복 실행 차단 계약 검사."""
from __future__ import annotations

import pytest
from desktop.company_campaign_resume_gate import snapshot, require_next


class AuditStore:
    def __init__(self, *, status='todo', completed=0, genuine=None,
                 prior_runs=None, artifacts=None, plan_state='approved'):
        self.allowed = True
        self.status = status
        self.completed = completed
        self.genuine = completed if genuine is None else genuine
        self.prior_runs = prior_runs or []
        self.artifacts = artifacts or []
        self.plan_state = plan_state
        self.reads = 0

    def require_permission(self, permission):
        assert permission == 'company:manage'
        if not self.allowed:
            raise PermissionError('관리자 로그인 필요')

    def read_full_company_campaign(self, campaign_id):
        self.reads += 1
        steps = [dict(ordinal=i, task_id=i+100,
                      task_status='done' if i <= self.completed else (
                          self.status if i == self.completed+1 else 'todo'))
                 for i in range(1, 31)]
        return {'id': campaign_id, 'state': self.plan_state, 'steps': steps}

    def verified_full_company_progress(self, campaign_id):
        self.reads += 1
        return {'campaign_id': campaign_id,
                'verified_completed_tasks': self.completed,
                'verified_genuine_prefix_tasks': self.genuine,
                'next_task_id': None if self.completed == 30 else self.completed+101,
                'all_30_tasks_evidence_verified': self.completed == 30,
                'all_30_chief_model_call_links_verified': self.genuine == 30}

    def list_task_runs(self, task_id):
        self.reads += 1
        return list(self.prior_runs)

    def list_task_artifacts(self, task_id):
        self.reads += 1
        return list(self.artifacts)


@pytest.mark.parametrize('value', [0, -2, True, '1', None, 1.5])
def test_invalid_campaign_number(value):
    with pytest.raises(ValueError, match='양의 정수'):
        snapshot(AuditStore(), value)


def test_unapproved_draft_is_blocked_without_execution():
    store = AuditStore(plan_state='draft')
    result = snapshot(store, 3)
    assert result['state'] == 'blocked' and result['next_task_id'] is None
    assert result['read_only'] and not result['executed']


def test_first_step_ready_and_no_model_call():
    store = AuditStore()
    result = snapshot(store, 3)
    assert result['state'] == 'ready'
    assert result['next_ordinal'] == 1 and result['next_task_id'] == 101
    assert result['existing_run_count'] == 0 and not result['automatically_retried']
    assert require_next(store, 3, 101)['state'] == 'ready'


def test_verified_prefix_next_step_ready():
    store = AuditStore(completed=9)
    result = snapshot(store, 2)
    assert result['state'] == 'ready' and result['next_ordinal'] == 10


@pytest.mark.parametrize('status', ['in_progress', 'blocked', 'cancelled'])
def test_active_or_blocked_step_never_reruns(status):
    result = snapshot(AuditStore(status=status), 1)
    assert result['state'] == 'blocked' and result['current_task_status'] == status


@pytest.mark.parametrize('runs,artifacts', [([{'status':'running'}], []),
                                             ([{'status':'success'}], []),
                                             ([], [{'id':12}])])
def test_previous_execution_or_artifact_blocks_replay(runs, artifacts):
    store = AuditStore(prior_runs=runs, artifacts=artifacts)
    result = snapshot(store, 1)
    assert result['state'] == 'blocked' and result['has_prior_execution']
    with pytest.raises(ValueError, match='중복|기존 실행'):
        require_next(store, 1, 101)


def test_genuine_chief_prefix_required():
    result = snapshot(AuditStore(completed=8, genuine=7), 1)
    assert result['state'] == 'blocked' and '총괄' in result['reason']


def test_no_implicit_task_switch():
    with pytest.raises(ValueError, match='재개 점검 실패'):
        require_next(AuditStore(), 1, 102)


def test_completed_requires_thirty_genuine_links():
    assert snapshot(AuditStore(completed=30), 1)['state'] == 'completed'
    assert snapshot(AuditStore(completed=30, genuine=29), 1)['state'] == 'blocked'


def test_admin_permission_required():
    store = AuditStore();store.allowed = False
    with pytest.raises(PermissionError):
        snapshot(store, 1)


def test_invalid_order_and_duplicate_task_id_fail_closed():
    class Broken(AuditStore):
        def read_full_company_campaign(self, campaign_id):
            data = super().read_full_company_campaign(campaign_id)
            data['steps'][2]['task_id'] = data['steps'][1]['task_id']
            return data
    with pytest.raises(ValueError, match='중복'):
        snapshot(Broken(), 1)


def test_real_sqlite_approved_campaign_resume_gate_and_restart(tmp_path, monkeypatch):
    """합성 모델 문자열을 쓰는 SQLite 회귀검사; 실GGUF/Windows 합격 아님."""
    import sys
    from desktop.storage import LocalStore
    from desktop.model_runtime import ModelConfig
    from desktop import company_operations as ops
    from desktop import company_wide_campaign as wide

    db = LocalStore(tmp_path / 'real-resume-gate.sqlite3')
    db.setup_owner('owner', 'aiwack-resume-owner-2026')
    ops.initialize_company_blueprint(db)
    model = db.add_local_model(ModelConfig('fixture-only', 'llamafile', sys.executable, '', 32))
    for employee in db.list_employee_records():
        db.set_employee_model(employee['id'], model)
    task_id = ops.create_task(db, '15부서 업무 사전 점검', '외부 결제/게시 없음')

    def fixture_chief(config, prompt, **kwargs):
        names = prompt.rsplit('담당 부서: ', 1)[1].split(', ')
        return '\n'.join(f'{name}|사전 검토|{name} 승인 전 검토 보고서 작성'
                         for name in names)
    monkeypatch.setattr('desktop.employee_model_runtime.run_local_model', fixture_chief)
    campaign = wide.approve(db, wide.propose(db, task_id)['id'])
    result = db.inspect_full_company_resume_gate(campaign['id'])
    assert result['state'] == 'ready' and result['next_ordinal'] == 1
    assert db.list_task_runs(result['next_task_id']) == []
    db.logout()
    reopened = LocalStore(db.path)
    reopened.login('owner', 'aiwack-resume-owner-2026')
    assert reopened.inspect_full_company_resume_gate(campaign['id'])['state'] == 'ready'
    monkeypatch.setattr('desktop.task_runtime.run_local_model',
                        lambda *a, **kw: '회귀 검사 전용 직원 합성 문자열')
    monkeypatch.setattr('desktop.chief_task_runtime.collect_chief_task_result',
                        lambda *a, **kw: '회귀 검사 전용 총괄 합성 문자열')
    executed = reopened.run_full_company_next(campaign['id'])
    assert executed['step'] == 1
    blocked = reopened.inspect_full_company_resume_gate(campaign['id'])
    assert blocked['state'] == 'blocked'
    assert blocked['has_prior_execution']
    with pytest.raises(ValueError):
        reopened.run_full_company_next(campaign['id'])


def test_legacy_chain_uses_explicit_opt_out_only_for_genuine_provenance():
    """실GGUF 검증 기본은 엄격, 합성 회귀 경로는 호출자가 명시한 경우만 허용."""
    store = AuditStore(completed=7, genuine=0)
    assert snapshot(store, 7)['state'] == 'blocked'
    assert snapshot(store, 7, require_genuine_provenance=False)['state'] == 'ready'
    assert require_next(store, 7, 108, require_genuine_provenance=False)['state'] == 'ready'
    with pytest.raises(ValueError, match='총괄'):
        require_next(store, 7, 108)


def test_disabling_genuine_provenance_never_skips_owner_review():
    store = AuditStore(completed=6, genuine=0)
    original = store.verified_full_company_progress
    def tampered(campaign_id):
        result = original(campaign_id)
        result['verified_completed_tasks'] = 5
        return result
    store.verified_full_company_progress = tampered
    result = snapshot(store, 7, require_genuine_provenance=False)
    assert result['state'] == 'blocked'
    assert '관리자 승인' in result['reason']


def test_prior_execution_still_blocks_with_optional_model_provenance():
    store = AuditStore(completed=7, genuine=0, prior_runs=[{'status': 'success'}])
    assert snapshot(store, 7, require_genuine_provenance=False)['state'] == 'blocked'
