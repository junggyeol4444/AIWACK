"""Stage54: manual triage filter never implies external source validation."""
import socket
import sqlite3

import pytest

from desktop.storage import LocalStore, AuthenticationError
from desktop.research_followup_notes import latest_actions_for_queue


@pytest.fixture
def owner(tmp_path):
    store = LocalStore(tmp_path / 'review_filter.sqlite3')
    store.setup_owner('filter-owner', 'filter-password-2026')
    return store


def seed(owner, suffixes):
    body = '<p>Saved offline</p>' + ''.join(
        f'<a href="/{suffix}">Local link</a>' for suffix in suffixes)
    return owner.add_offline_research('https://example.org/root', 'root', body, 'html_snapshot')


def test_pending_deferred_and_reopen_are_manual_only(owner):
    seed(owner, ['a', 'b', 'c'])
    a = 'https://example.org/a'
    b = 'https://example.org/b'
    owner.record_offline_research_followup_note(a, 'deferred', 'Review next week')
    owner.record_offline_research_followup_note(b, 'noted', 'Need a local copy')
    pending = owner.offline_research_followup_queue(review_filter='pending')
    deferred = owner.offline_research_followup_queue(review_filter='deferred')
    assert {r['linked_url'] for r in pending['items']} == {
        'https://example.org/b', 'https://example.org/c'}
    assert [r['linked_url'] for r in deferred['items']] == [a]
    assert pending['review_counts'] == {'pending': 2, 'deferred': 1}
    assert pending['status_counts']['unregistered'] == 3  # Inventory, not filtered.
    assert not pending['source_authenticity_verified']
    assert not deferred['network_accessed']
    owner.record_offline_research_followup_note(a, 'reopen', 'Resume offline review')
    assert owner.offline_research_followup_queue(review_filter='deferred')['items'] == []
    assert owner.offline_research_followup_queue(review_filter='pending')['review_counts'] == {
        'pending': 3, 'deferred': 0}


def test_filter_before_limit_prevents_deferred_starvation(owner):
    suffixes = [f'a{i:02d}' for i in range(42)] + ['z-pending']
    seed(owner, suffixes)
    for suffix in suffixes[:-1]:
        owner.record_offline_research_followup_note(
            f'https://example.org/{suffix}', 'deferred', 'Deferred by owner')
    report = owner.offline_research_followup_queue(review_filter='pending', limit=1)
    assert [i['linked_url'] for i in report['items']] == ['https://example.org/z-pending']
    assert not report['results_truncated']
    assert report['review_counts'] == {'pending': 1, 'deferred': 42}
    deferred = owner.offline_research_followup_queue(review_filter='deferred', limit=1)
    assert len(deferred['items']) == 1 and deferred['results_truncated']
    assert owner.offline_research_followup_queue(limit=1)['results_truncated']


def test_filter_read_only_persistent_and_socket_blocked(owner, monkeypatch):
    seed(owner, ['a'])
    owner.record_offline_research_followup_note('https://example.org/a', 'deferred', 'Waiting')
    with sqlite3.connect(owner.path) as con:
        before = list(con.iterdump())
    def denied(*args, **kwargs):
        raise AssertionError('Network request attempted')
    monkeypatch.setattr(socket.socket, 'connect', denied)
    monkeypatch.setattr(socket.socket, 'connect_ex', denied)
    monkeypatch.setattr(socket, 'create_connection', denied)
    first = owner.offline_research_followup_queue(review_filter='deferred')
    with sqlite3.connect(owner.path) as con:
        assert list(con.iterdump()) == before
    path = owner.path
    owner.logout()
    reopened = LocalStore(path)
    reopened.login('filter-owner', 'filter-password-2026')
    assert reopened.offline_research_followup_queue(review_filter='deferred') == first


@pytest.mark.parametrize('value', ['', None, True, 1, 'verified', 'DEFERRED', 'all;DROP'])
def test_reject_invalid_filter(owner, value):
    with pytest.raises(ValueError):
        owner.offline_research_followup_queue(review_filter=value)


def test_filter_requires_owner_login(owner):
    owner.logout()
    with pytest.raises(AuthenticationError):
        owner.offline_research_followup_queue(review_filter='pending')


def test_action_query_bound_and_legacy_sqlite_compatibility(owner):
    seed(owner, ['a', 'b'])
    with sqlite3.connect(owner.path) as con:
        con.row_factory = sqlite3.Row
        assert latest_actions_for_queue(con, []) == {}
        assert latest_actions_for_queue(con, ['https://example.org/a']) == {}
        with pytest.raises(ValueError):
            latest_actions_for_queue(con, ['https://example.org/a'] * 2001)
        with pytest.raises(ValueError):
            latest_actions_for_queue(con, [None])


def test_chunk_boundary_uses_latest_append_only_action(owner):
    seed(owner, ['a'])
    url = 'https://example.org/a'
    owner.record_offline_research_followup_note(url, 'deferred', 'Initial')
    owner.record_offline_research_followup_note(url, 'reopen', 'Later')
    with sqlite3.connect(owner.path) as con:
        con.row_factory = sqlite3.Row
        urls = [f'https://example.org/other-{i}' for i in range(300)] + [url]
        assert latest_actions_for_queue(con, urls) == {url: 'reopen'}
