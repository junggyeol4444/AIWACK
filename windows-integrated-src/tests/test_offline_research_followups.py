"""Stage54 partial: deterministic, bounded offline manual follow-up inventory."""
import socket
import sqlite3

import pytest

from desktop.storage import LocalStore, AuthenticationError
from desktop.research_followups import build_followup_queue, MAX_SCANNED_LINKS


@pytest.fixture
def owner(tmp_path):
    store = LocalStore(tmp_path / 'followup.sqlite3')
    store.setup_owner('followup-owner', 'followup-password-2026')
    return store


def html(owner, suffix, links):
    return owner.add_offline_research('https://example.org/' + suffix, suffix,
        '<p>Local snapshot</p>' + ''.join(f'<a href="/{link}">Link</a>' for link in links),
        'html_snapshot')


def test_priorities_and_reference_counts(owner):
    first = html(owner, 'a', ['missing', 'old', 'many', 'one'])
    second = html(owner, 'b', ['missing', 'many'])
    old = owner.add_offline_research('https://example.org/old', 'old', 'old body')
    owner.archive_offline_research(old)
    owner.add_offline_research('https://example.org/many', 'm1', 'first')
    owner.add_offline_research('https://example.org/many', 'm2', 'second')
    owner.add_offline_research('https://example.org/one', 'one', 'body')
    result = owner.offline_research_followup_queue()
    assert [i['status'] for i in result['items']] == [
        'unregistered', 'archived_only', 'multiple_active', 'one_active']
    assert result['status_counts'] == dict(unregistered=1, archived_only=1,
                                            multiple_active=1, one_active=1)
    assert result['items'][0]['referrer_count'] == 2
    assert result['items'][0]['referrer_ids'] == [second, first]
    assert result['items'][1]['archived_candidate_count'] == 1
    assert result['items'][2]['active_candidate_count'] == 2
    assert not result['source_authenticity_verified']
    assert not result['network_accessed']


def test_archived_referrers_scope_and_archived_targets(owner):
    archived_ref = html(owner, 'archived', ['old'])
    owner.archive_offline_research(archived_ref)
    active = html(owner, 'active', ['now'])
    assert [i['linked_url'] for i in owner.offline_research_followup_queue()['items']] == [
        'https://example.org/now']
    assert len(owner.offline_research_followup_queue(include_archived=True)['items']) == 2


def test_no_links_and_legacy_manual_text(owner):
    owner.add_offline_research('https://example.org/plain', 'plain', '<a href="/notlink">')
    report = owner.offline_research_followup_queue()
    assert report['items'] == []
    assert report['scanned_link_count'] == 0
    assert not report['scan_truncated']


def test_limit_and_order_are_stable(owner):
    html(owner, 'a', ['z', 'b', 'c'])
    report = owner.offline_research_followup_queue(limit=2)
    assert [i['linked_url'] for i in report['items']] == [
        'https://example.org/b', 'https://example.org/c']
    assert report['results_truncated']
    assert report['unique_url_count'] == 3
    assert report['status_counts']['unregistered'] == 3


@pytest.mark.parametrize('options', [dict(limit=0), dict(limit=41), dict(limit=True),
                                     dict(limit='10'), dict(include_archived=1),
                                     dict(include_archived=None)])
def test_invalid_options(owner, options):
    with pytest.raises(ValueError):
        owner.offline_research_followup_queue(**options)


def test_permission_checked_before_query(owner, monkeypatch):
    owner.logout()
    with pytest.raises(AuthenticationError):
        owner.offline_research_followup_queue()


def test_restart_and_no_database_writes(owner):
    html(owner, 'a', ['b'])
    with sqlite3.connect(owner.path) as con:
        before = list(con.iterdump())
    report = owner.offline_research_followup_queue()
    with sqlite3.connect(owner.path) as con:
        assert list(con.iterdump()) == before
    owner.logout()
    reopened = LocalStore(owner.path)
    reopened.login('followup-owner', 'followup-password-2026')
    assert reopened.offline_research_followup_queue() == report


def test_socket_guard(owner, monkeypatch):
    html(owner, 'a', ['b'])
    def denied(*args, **kwargs):
        raise AssertionError('unexpected network request')
    monkeypatch.setattr(socket.socket, 'connect', denied)
    monkeypatch.setattr(socket.socket, 'connect_ex', denied)
    monkeypatch.setattr(socket, 'create_connection', denied)
    assert owner.offline_research_followup_queue()['items'][0]['status'] == 'unregistered'


def test_scan_truncation_is_explicit(tmp_path):
    con = sqlite3.connect(tmp_path / 'test.sqlite3')
    from desktop.research_captures import initialize
    initialize(con)
    # Construct a deliberately large inventory without network or GUI overhead.
    con.execute('''INSERT INTO offline_research_captures
        (source_url,title,body,capture_kind,content_sha256) VALUES (?,?,?,?,?)''',
        ('https://example.org/a','a','body','html_snapshot','0'*64))
    # Each capture permits 100 links. Add 21 captures with distinct URLs.
    for number in range(1, 22):
        if number > 1:
            con.execute('''INSERT INTO offline_research_captures
                (source_url,title,body,capture_kind,content_sha256) VALUES (?,?,?,?,?)''',
                (f'https://example.org/{number}',str(number),'body','html_snapshot','0'*64))
        con.executemany('''INSERT INTO offline_research_html_links
            (capture_id,position,linked_url) VALUES (?,?,?)''',
            [(number, p, f'https://example.org/missing-{number}-{p}') for p in range(1,101)])
    report = build_followup_queue(con)
    assert report['scan_truncated']
    assert report['scanned_link_count'] == MAX_SCANNED_LINKS
    assert report['unique_url_count'] == MAX_SCANNED_LINKS
    assert len(report['items']) == 40
    assert report['results_truncated']
    con.close()
