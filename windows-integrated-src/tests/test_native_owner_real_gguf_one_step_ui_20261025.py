"""기존 한국어 Tk 창의 관리자 1회 실행·취소·최종보고 승인 연결 계약.

모든 호출은 로컬 스텁이며 실제 GGUF/Windows EXE/외부 거래 검증이 아니다.
"""
from __future__ import annotations

import queue
import threading

import pytest

from desktop import company_native_owner_workflows as native


class FakeWindow:
    def __init__(self):
        self.callbacks = []

    def after(self, milliseconds, callback):
        assert milliseconds >= 100
        self.callbacks.append(callback)


class FakeNotice:
    def __init__(self):
        self.value = ''

    def set(self, value):
        self.value = value


class FakeStore:
    def __init__(self, state='ready', existing=False):
        self.state = state
        self.existing = existing
        self.calls = []
        self.fail_after_first = False
        self.checks = 0

    def require_permission(self, permission):
        assert permission == 'company:manage'

    def inspect_full_company_resume_gate(self, campaign_id):
        assert campaign_id == 7
        self.checks += 1
        if self.fail_after_first and self.checks > 1:
            return {'state': 'blocked', 'reason': '실행 직전 원본 변경'}
        return {'state': self.state, 'reason': '로컬 계약 점검'}

    def find_campaign_final_report(self, campaign_id):
        assert campaign_id == 7
        return {'id': 8} if self.existing else None

    def run_full_company_next(self, campaign_id, *, cancel=None):
        assert campaign_id == 7 and isinstance(cancel, threading.Event)
        self.calls.append('next')
        return {'step': 1, 'owner_review_required': True}

    def propose_campaign_final_report(self, campaign_id, *, cancel=None):
        assert campaign_id == 7 and isinstance(cancel, threading.Event)
        self.calls.append('final')
        return {'id': 8, 'decision': 'pending'}


class InlineThread:
    def __init__(self, *, target, daemon, name):
        assert daemon and name.startswith('AIWACK-Owner')
        self.target = target

    def start(self):
        self.target()


@pytest.fixture
def gui(monkeypatch):
    monkeypatch.setattr(native.threading, 'Thread', InlineThread)
    monkeypatch.setattr(native.messagebox, 'askyesno', lambda *a, **kw: True)
    errors = []
    monkeypatch.setattr(native.messagebox, 'showerror',
                        lambda *a, **kw: errors.append(a))
    window = native.CompanyOwnerWorkflows.__new__(native.CompanyOwnerWorkflows)
    window.window = FakeWindow()
    window.notice = FakeNotice()
    window.store = FakeStore()
    window._campaign_cancel = threading.Event()
    window._campaign_results = queue.Queue()
    window._campaign_running = False
    window._id = lambda field: 7
    shown = []
    window._display = lambda title, payload: shown.append((title, payload))
    return window, shown, errors


def test_owner_one_click_runs_only_one_real_model_step(gui):
    window, shown, errors = gui
    window._start_real_model_action('다음 한 업무', 'next', '승인?')
    assert window.store.calls == ['next']
    assert window.store.checks == 2
    assert window._campaign_running is True
    window._poll_real_model_action()
    assert window._campaign_running is False
    assert shown[0][1]['owner_review_required'] is True
    assert not errors


def test_owner_cannot_execute_without_ready_original(gui):
    window, shown, errors = gui
    window.store.state = 'blocked'
    window._start_real_model_action('다음 한 업무', 'next', '승인?')
    assert not window.store.calls and not shown and errors


def test_final_report_requires_completed_30_steps(gui):
    window, shown, errors = gui
    window._start_real_model_action('최종보고', 'final', '승인?')
    assert not window.store.calls and errors


def test_final_report_requires_absent_previous_report(gui):
    window, shown, errors = gui
    window.store.state = 'completed'
    window.store.existing = True
    window._start_real_model_action('최종보고', 'final', '승인?')
    assert not window.store.calls and errors


def test_owner_final_report_is_not_auto_approved(gui):
    window, shown, errors = gui
    window.store.state = 'completed'
    window._start_real_model_action('최종보고', 'final', '승인?')
    assert window.store.calls == ['final']
    window._poll_real_model_action()
    assert shown[0][1]['decision'] == 'pending'
    assert not errors


def test_recheck_prevents_execution_after_owner_confirmation(gui):
    window, shown, errors = gui
    window.store.fail_after_first = True
    window._start_real_model_action('다음 한 업무', 'next', '승인?')
    window._poll_real_model_action()
    assert not window.store.calls and not shown and errors


def test_cancel_event_does_not_invent_success(gui):
    window, shown, errors = gui
    window._campaign_running = True
    window._cancel_real_model_action()
    assert window._campaign_cancel.is_set()
    assert not shown and not errors


def test_second_click_while_running_is_blocked(gui):
    window, shown, errors = gui
    window._campaign_running = True
    window._start_real_model_action('다음 한 업무', 'next', '승인?')
    assert not window.store.calls and errors
