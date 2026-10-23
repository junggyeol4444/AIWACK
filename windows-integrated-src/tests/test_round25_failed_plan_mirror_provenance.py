"""실제 총괄 GGUF 실패 감사 이중 기록 보존 회귀(모델 문자열은 fixture)."""
import sys
import pytest
from desktop import company_campaign_plan_provenance as provenance
from desktop import company_wide_campaign as wide
from desktop.company_operations import initialize_company_blueprint, create_task
from desktop.model_runtime import ModelConfig
from desktop.storage import LocalStore


def _prepared(tmp_path, monkeypatch):
    store = LocalStore(tmp_path/'mirror.sqlite3')
    store.setup_owner('owner', 'mirror-check-password-2026')
    initialize_company_blueprint(store)
    model = store.add_local_model(ModelConfig('mirror-fixture', 'llamafile', sys.executable, '', 32))
    for person in store.list_employee_records():
        store.set_employee_model(person['id'], model)
    source = create_task(store, '사내 문서 점검', '관리자 승인 전 내부 검토만 진행')

    def generated(config, prompt, **kwargs):
        if '담당 부서:' in prompt:
            return 'not a three department plan'
        if '출력 형식:' in prompt:
            return 'invalid single format'
        return '승인된 내부 자료의 점검 항목을 확인하고 개선 사항을 문서로 정리합니다.'

    monkeypatch.setattr('desktop.employee_model_runtime.run_local_model', generated)
    campaign = wide.propose(store, source)
    return store, campaign['id']


def test_failed_calls_have_matching_immutable_mirror(tmp_path, monkeypatch):
    store, campaign_id = _prepared(tmp_path, monkeypatch)
    proof = provenance.snapshot(store, campaign_id)
    assert proof['verified_plan_groups'] == 5
    assert len(proof['failed_attempts_preserved']) == 15
    assert proof['failed_attempts_model_provenance_checked'] is True


def test_mirror_tampering_rejected_without_approving_any_work(tmp_path, monkeypatch):
    store, campaign_id = _prepared(tmp_path, monkeypatch)
    with store._connect() as con:
        con.execute('DROP TRIGGER aiwack_wide_chief_rejected_no_update')
        con.execute("UPDATE aiwack_wide_chief_rejected_attempts SET output_sha256=? WHERE id=(SELECT MIN(id) FROM aiwack_wide_chief_rejected_attempts)", ('0'*64,))
    with pytest.raises(ValueError, match='이중 감사'):
        provenance.snapshot(store, campaign_id)
    assert len(store.list_tasks()) == 1
