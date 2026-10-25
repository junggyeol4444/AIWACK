"""기존 한국어 Tk 30업무 관리자 검수 연결의 오프라인 계약 테스트.

실 GGUF 바이너리/Windows GUI 클릭 검증이 아니라 구조 회귀용이다.
전체 개발 완료 후 통합검증 단계에서 실행한다.
"""
from __future__ import annotations

import hashlib

import pytest

from desktop.company_native_owner_workflows import CompanyOwnerWorkflows


class Field:
    def __init__(self, value):
        self.value = str(value)
    def get(self):
        return self.value


class FakeStore:
    def __init__(self):
        self.artifact = {
            'id': 91, 'task_id': 301, 'body': '실제 직원 실행 원문 검토 대상',
            'sha256': hashlib.sha256('실제 직원 실행 원문 검토 대상'.encode()).hexdigest(),
            'review_status': 'pending'}
        self.report = {
            'id': 81, 'artifact_id': 91, 'chief_employee_id': 4,
            'body': '총괄 검토 원문', 'sha256': hashlib.sha256('총괄 검토 원문'.encode()).hexdigest(),
            'owner_decision': 'pending'}
        self.plan = {
            'id': 7, 'state': 'approved', 'chief_employee_id': 4,
            'steps': [{'ordinal': 1, 'task_id': 301, 'task_status': 'in_progress'}]}
        self.chief_context_count = 0
    def read_full_company_campaign(self, campaign_id):
        assert campaign_id == 7
        return self.plan
    def read_task_artifact(self, artifact_id):
        assert artifact_id == 91
        return self.artifact
    def find_chief_task_report(self, artifact_id):
        assert artifact_id == 91
        return self.report
    def require_permission(self, permission):
        assert permission == 'company:manage'
    def list_task_artifacts(self, task_id):
        assert task_id == 301
        return [self.artifact]
    def chief_task_report_context(self, artifact_id):
        assert artifact_id == 91
        self.chief_context_count += 1
        return {'task_id': 301}


def _controller(store):
    ui = object.__new__(CompanyOwnerWorkflows)
    ui.store = store
    ui.values = {'summary_campaign': Field(7), 'summary_artifact': Field(91)}
    return ui


def test_owner_packet_binds_worker_and_chief_to_approved_campaign():
    ui = _controller(FakeStore())
    packet = ui._campaign_review_packet()
    assert packet['campaign_id'] == 7
    assert packet['step']['ordinal'] == 1
    assert packet['artifact']['id'] == 91
    assert packet['chief_report']['id'] == 81
    assert packet['automatic_approval'] is False


def test_owner_packet_rejects_artifact_from_unrelated_campaign():
    store = FakeStore()
    store.plan['steps'][0]['task_id'] = 999
    with pytest.raises(ValueError, match='속하지'):
        _controller(store)._campaign_review_packet()


def test_owner_packet_rejects_mutated_worker_body():
    store = FakeStore()
    store.artifact['body'] = '검수 전에 바뀐 내용'
    with pytest.raises(ValueError, match='SHA256'):
        _controller(store)._campaign_review_packet()


def test_owner_packet_rejects_mutated_chief_body_and_wrong_chief():
    store = FakeStore()
    store.report['body'] = '총괄 응답 변경'
    with pytest.raises(ValueError, match='SHA256'):
        _controller(store)._campaign_review_packet()
    store.report['body'] = '총괄 검토 원문'
    store.report['chief_employee_id'] = 5
    with pytest.raises(ValueError, match='연결 불일치'):
        _controller(store)._campaign_review_packet()


def test_worker_recovery_does_not_touch_tk_fields_and_refuses_existing_report():
    store = FakeStore()
    ui = _controller(store)
    with pytest.raises(ValueError, match='이미 총괄'):
        ui._campaign_review_packet_worker(7, 301, 91)
    store.report = None
    packet = ui._campaign_review_packet_worker(7, 301, 91)
    assert packet['artifact_id'] == 91
    assert store.chief_context_count == 1
    assert packet['step']['ordinal'] == 1


def test_worker_recovery_rejects_changed_task_status():
    store = FakeStore()
    store.report = None
    store.plan['steps'][0]['task_status'] = 'done'
    with pytest.raises(ValueError, match='원본이 변경'):
        _controller(store)._campaign_review_packet_worker(7, 301, 91)


def test_worker_recovery_refuses_artifact_swapped_after_owner_confirmation():
    store = FakeStore()
    store.report = None
    with pytest.raises(ValueError, match='원본이 변경'):
        _controller(store)._campaign_review_packet_worker(7, 301, 999)
