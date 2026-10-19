"""Stage54 partial: passive URL warning checks without network access."""
import socket
import sqlite3

import pytest

from desktop.research_url_preflight import classify_stored_url
from desktop.storage import AuthenticationError, LocalStore


@pytest.fixture
def owner(tmp_path):
    store = LocalStore(tmp_path / 'url-preflight.sqlite3')
    store.setup_owner('preflight-owner', 'long-password-2026')
    return store


def capture(owner, links):
    return owner.add_offline_research(
        'https://origin.example/index', 'Offline HTML',
        '<p>offline</p>' + ''.join(f'<a href="{url}">saved</a>' for url in links),
        'html_snapshot')


@pytest.mark.parametrize(('url', 'expected'), [
    ('https://127.0.0.1/private', ('ip_literal', 'non_global_ip_literal')),
    ('http://169.254.169.254/latest', ('ip_literal', 'non_global_ip_literal')),
    ('https://10.1.2.3/', ('ip_literal', 'non_global_ip_literal')),
    ('http://[::1]/', ('ip_literal', 'non_global_ip_literal')),
    ('https://8.8.8.8/', ('ip_literal',)),
    ('https://0x7f000001/', ('ambiguous_numeric_hostname',)),
    ('https://0177.0.0.1/', ('ambiguous_numeric_hostname',)),
    ('https://localhost/', ('local_name',)),
    ('https://machine.local/', ('local_name',)),
    ('https://intranet/', ('single_label_hostname',)),
    ('https://xn--bcher-kva.example/', ('internationalized_hostname',)),
    ('https://example.org/', ()),
    ('https://example.org./', ('trailing_dot_hostname',)),
    ('https://user:secret@example.org:8080/',
     ('embedded_credentials', 'nonstandard_port')),
    ('http://[fe80::1%25eth0]/',
     ('encoded_or_scoped_hostname', 'ip_literal', 'non_global_ip_literal')),
    ('file:///etc/passwd', ('invalid_url',)),
    ('https://example.org:invalid/', ('invalid_url',)),
    ('https://example.org/ bad', ('invalid_url',)),
    ('https://[bad/', ('invalid_url',)),
])
def test_classifier_no_network(url, expected, monkeypatch):
    def deny(*args, **kwargs):
        raise AssertionError('Network must never be used for URL preflight')
    monkeypatch.setattr(socket.socket, 'connect', deny)
    monkeypatch.setattr(socket, 'getaddrinfo', deny)
    assert classify_stored_url(url) == expected


def test_integrated_report_and_no_safety_claim(owner):
    capture(owner, ['https://127.0.0.1/private', 'https://safe.example/page',
                    'https://intranet/', 'https://0x7f000001/'])
    report = owner.offline_research_url_preflight()
    assert report['filtered_url_count'] == 4
    assert report['warning_url_count'] == 3
    assert report['warning_counts']['ip_literal'] == 1
    assert report['warning_counts']['non_global_ip_literal'] == 1
    assert report['warning_counts']['single_label_hostname'] == 1
    assert report['warning_counts']['ambiguous_numeric_hostname'] == 1
    assert all(item['warning_codes'] for item in report['items'])
    assert not report['dns_checked'] and not report['network_accessed']
    assert not report['safe_to_fetch_verified'] and not report['source_authenticity_verified']


def test_filter_before_warning_cap(owner):
    links = [f'https://127.0.0.{n}/p' for n in range(1, 61)]
    capture(owner, links)
    for url in links[:50]:
        owner.record_offline_research_followup_note(url, 'deferred', 'Later')
    pending = owner.offline_research_url_preflight(review_filter='pending')
    assert pending['filtered_url_count'] == pending['warning_url_count'] == 10
    assert not pending['warnings_truncated']
    deferred = owner.offline_research_url_preflight(review_filter='deferred')
    assert deferred['filtered_url_count'] == deferred['warning_url_count'] == 50
    assert len(deferred['items']) == 40 and deferred['warnings_truncated']
    assert deferred['warning_counts']['ip_literal'] == 50


def test_archived_scope(owner):
    ident = capture(owner, ['https://127.0.0.1/private'])
    owner.archive_offline_research(ident)
    assert owner.offline_research_url_preflight()['warning_url_count'] == 0
    assert owner.offline_research_url_preflight(include_archived=True)['warning_url_count'] == 1


@pytest.mark.parametrize('bad', [0, 41, True, '4', None, 1.1, -1])
def test_invalid_limit(owner, bad):
    with pytest.raises(ValueError):
        owner.offline_research_url_preflight(limit=bad)


@pytest.mark.parametrize('bad', ['unknown', None, True])
def test_invalid_filter(owner, bad):
    with pytest.raises(ValueError):
        owner.offline_research_url_preflight(review_filter=bad)


@pytest.mark.parametrize('bad', ['yes', 1, None])
def test_invalid_archived(owner, bad):
    with pytest.raises(ValueError):
        owner.offline_research_url_preflight(include_archived=bad)


def test_auth_first(owner):
    owner.logout()
    with pytest.raises(AuthenticationError):
        owner.offline_research_url_preflight(limit=0)


def test_read_only_relogin_and_sockets_blocked(owner, monkeypatch):
    capture(owner, ['https://127.0.0.1/private', 'https://example.org/ok'])
    with sqlite3.connect(owner.path) as con:
        before = list(con.iterdump())
    def deny(*args, **kwargs):
        raise AssertionError('Network forbidden')
    monkeypatch.setattr(socket.socket, 'connect', deny)
    monkeypatch.setattr(socket.socket, 'connect_ex', deny)
    monkeypatch.setattr(socket, 'getaddrinfo', deny)
    report = owner.offline_research_url_preflight()
    with sqlite3.connect(owner.path) as con:
        assert list(con.iterdump()) == before
    owner.logout()
    reopened = LocalStore(owner.path)
    reopened.login('preflight-owner', 'long-password-2026')
    assert reopened.offline_research_url_preflight() == report


def test_empty(owner):
    report = owner.offline_research_url_preflight()
    assert report['items'] == [] and report['warning_url_count'] == 0
    assert not report['warnings_truncated']
