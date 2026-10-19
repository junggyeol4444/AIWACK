"""Stage54 partial: local-only hostname triage over stored HTML link strings."""
import socket
import sqlite3

import pytest

from desktop.storage import AuthenticationError, LocalStore


@pytest.fixture
def owner(tmp_path):
    store = LocalStore(tmp_path / 'host_summary.sqlite3')
    store.setup_owner('host-owner', 'host-owner-password-2026')
    return store


def capture(owner, suffix, links):
    return owner.add_offline_research(
        'https://origin.example/' + suffix, suffix,
        '<p>local HTML</p>' + ''.join(f'<a href="{url}">link</a>' for url in links),
        'html_snapshot')


def test_groups_by_host_and_prioritizes_unregistered(owner):
    capture(owner, 'first', ['https://B.example/a', 'https://b.example/b',
                             'https://c.example/c', 'https://d.example/d'])
    capture(owner, 'second', ['https://b.example/a'])
    owner.add_offline_research('https://c.example/c', 'saved', 'body')
    old = owner.add_offline_research('https://d.example/d', 'old', 'body')
    owner.archive_offline_research(old)
    report = owner.offline_research_followup_domains()
    assert report['domain_count'] == 3
    assert [row['hostname'] for row in report['items']] == [
        'b.example', 'd.example', 'c.example']
    b = report['items'][0]
    assert b['url_count'] == 3 and b['referrer_count_total'] == 3
    assert b['status_counts']['unregistered'] == 3
    assert b['sample_urls'] == ['https://B.example/a', 'https://b.example/a', 'https://b.example/b']
    assert report['items'][1]['status_counts']['archived_only'] == 1
    assert report['items'][2]['status_counts']['one_active'] == 1
    assert not report['network_accessed'] and not report['source_authenticity_verified']


def test_review_filter_applied_before_grouping(owner):
    capture(owner, 'first', ['https://a.example/one', 'https://b.example/two'])
    owner.record_offline_research_followup_note('https://a.example/one', 'deferred', 'later')
    all_report = owner.offline_research_followup_domains()
    assert all_report['domain_count'] == 2
    assert all_report['items'][0]['deferred_url_count'] in (0, 1)
    deferred = owner.offline_research_followup_domains(review_filter='deferred')
    assert deferred['domain_count'] == deferred['filtered_url_count'] == 1
    assert deferred['items'][0]['hostname'] == 'a.example'
    assert deferred['items'][0]['deferred_url_count'] == 1
    pending = owner.offline_research_followup_domains(review_filter='pending')
    assert pending['items'][0]['hostname'] == 'b.example'
    owner.record_offline_research_followup_note('https://a.example/one', 'reopen', 'again')
    assert owner.offline_research_followup_domains(review_filter='deferred')['items'] == []
    assert owner.offline_research_followup_domains(review_filter='pending')['domain_count'] == 2


def test_archived_scope(owner):
    ident = capture(owner, 'first', ['https://a.example/one'])
    owner.archive_offline_research(ident)
    assert owner.offline_research_followup_domains()['domain_count'] == 0
    report = owner.offline_research_followup_domains(include_archived=True)
    assert report['domain_count'] == 1 and report['include_archived_referrers']


def test_bounded_display_preserves_total_counts(owner):
    capture(owner, 'first', [f'https://host{i:02}.example/item' for i in range(60)])
    report = owner.offline_research_followup_domains(limit=7)
    assert report['domain_count'] == 60
    assert report['displayed_domain_count'] == len(report['items']) == 7
    assert report['domains_truncated'] and report['filtered_url_count'] == 60
    assert [r['hostname'] for r in report['items']] == [
        f'host{i:02}.example' for i in range(7)]


def test_sample_urls_max_three(owner):
    capture(owner, 'first', [f'https://a.example/{i}' for i in range(8)])
    report = owner.offline_research_followup_domains()
    assert len(report['items'][0]['sample_urls']) == 3
    assert report['items'][0]['url_count'] == 8


@pytest.mark.parametrize('bad', [0, 51, True, 1.5, '5', None, -1])
def test_invalid_limit(owner, bad):
    with pytest.raises(ValueError):
        owner.offline_research_followup_domains(limit=bad)


@pytest.mark.parametrize('bad', [None, 1, 'later', ''])
def test_invalid_filter(owner, bad):
    with pytest.raises(ValueError):
        owner.offline_research_followup_domains(review_filter=bad)


@pytest.mark.parametrize('bad', [None, 1, 'yes'])
def test_invalid_archived(owner, bad):
    with pytest.raises(ValueError):
        owner.offline_research_followup_domains(include_archived=bad)


def test_login_required(owner):
    owner.logout()
    with pytest.raises(AuthenticationError):
        owner.offline_research_followup_domains()


def test_read_only_and_restart(owner):
    capture(owner, 'first', ['https://a.example/a', 'https://b.example/b'])
    with sqlite3.connect(owner.path) as con:
        before = list(con.iterdump())
    report = owner.offline_research_followup_domains()
    with sqlite3.connect(owner.path) as con:
        assert list(con.iterdump()) == before
    owner.logout()
    reopened = LocalStore(owner.path)
    reopened.login('host-owner', 'host-owner-password-2026')
    assert reopened.offline_research_followup_domains() == report


def test_no_socket_or_dns_access(owner, monkeypatch):
    capture(owner, 'first', ['https://a.example/a'])
    def forbidden(*args, **kwargs):
        raise AssertionError('Network is forbidden')
    for name in ('connect', 'connect_ex'):
        monkeypatch.setattr(socket.socket, name, forbidden)
    monkeypatch.setattr(socket, 'create_connection', forbidden)
    monkeypatch.setattr(socket, 'getaddrinfo', forbidden)
    assert owner.offline_research_followup_domains()['domain_count'] == 1


def test_empty(owner):
    report = owner.offline_research_followup_domains()
    assert report['items'] == [] and report['domain_count'] == 0
    assert not report['domains_truncated']
