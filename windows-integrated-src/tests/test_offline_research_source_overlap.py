"""Stage54 partial: offline content/source overlap, not source authentication."""
import hashlib
import socket
import sqlite3

import pytest

from desktop.storage import AuthenticationError, LocalStore
from desktop.research_source_overlap import build_source_overlap_report


@pytest.fixture
def owner(tmp_path):
    store = LocalStore(tmp_path / 'owner.sqlite3')
    store.setup_owner('overlap-owner', 'long-password-2026')
    return store


def add(owner, url, body):
    return owner.add_offline_research(url, 'Local evidence', body)


def test_empty_read_only(owner):
    with sqlite3.connect(owner.path) as con:
        before = list(con.iterdump())
    report = owner.offline_research_source_overlap()
    assert report['items'] == []
    assert report['group_count'] == report['scanned_capture_count'] == 0
    assert all(report[key] is False for key in (
        'source_independence_verified', 'source_authenticity_verified',
        'original_file_bytes_rechecked', 'network_accessed'))
    with sqlite3.connect(owner.path) as con:
        assert list(con.iterdump()) == before


def test_same_body_across_claimed_urls(owner):
    a = add(owner, 'https://a.example/a', 'same local body')
    b = add(owner, 'https://b.example/b', 'same local body')
    result = owner.offline_research_source_overlap()
    assert result['category_counts']['same_body_different_claimed_urls'] == 1
    assert result['category_counts']['different_bodies_same_claimed_url'] == 0
    group = result['items'][0]
    assert group['capture_ids'] == [b, a]
    assert group['claimed_urls'] == ['https://a.example/a', 'https://b.example/b']
    assert group['distinct_value_count'] == 2
    assert group['key'] == hashlib.sha256(b'same local body').hexdigest()[:12]


def test_same_claimed_url_different_body(owner):
    first = add(owner, 'https://a.example/page', 'version one')
    second = add(owner, 'https://a.example/page', 'version two')
    report = owner.offline_research_source_overlap()
    assert report['category_counts']['different_bodies_same_claimed_url'] == 1
    assert report['category_counts']['same_body_different_claimed_urls'] == 0
    group = report['items'][0]
    assert group['key'] == 'https://a.example/page'
    assert group['capture_ids'] == [second, first]
    assert group['distinct_value_count'] == 2


def test_same_url_same_body_cannot_be_registered_twice(owner):
    add(owner, 'https://a.example/page', 'same')
    with pytest.raises(ValueError):
        add(owner, 'https://a.example/page', 'same')
    assert owner.offline_research_source_overlap()['group_count'] == 0


def test_raw_import_bytes_across_urls(owner, tmp_path):
    file1 = tmp_path / 'one.txt'
    file2 = tmp_path / 'two.txt'
    file1.write_bytes(b'identical raw bytes')
    file2.write_bytes(b'identical raw bytes')
    a = owner.import_offline_research_file('https://a.example/x', 'A', str(file1))
    b = owner.import_offline_research_file('https://b.example/x', 'B', str(file2))
    report = owner.offline_research_source_overlap()
    assert report['category_counts']['same_imported_bytes_different_claimed_urls'] == 1
    raw = [g for g in report['items']
           if g['category'] == 'same_imported_bytes_different_claimed_urls'][0]
    assert raw['capture_ids'] == [b, a]
    assert raw['key'] == hashlib.sha256(b'identical raw bytes').hexdigest()[:12]
    assert report['group_count'] == 2  # same extracted text AND same imported bytes


def test_manual_text_has_no_imported_file_hash(owner):
    add(owner, 'https://a.example/x', 'same')
    add(owner, 'https://b.example/x', 'same')
    report = owner.offline_research_source_overlap()
    assert report['category_counts']['same_imported_bytes_different_claimed_urls'] == 0


def test_archived_scope(owner):
    first = add(owner, 'https://a.example/x', 'same')
    add(owner, 'https://b.example/x', 'same')
    owner.archive_offline_research(first)
    assert owner.offline_research_source_overlap()['group_count'] == 0
    report = owner.offline_research_source_overlap(include_archived=True)
    assert report['group_count'] == 1
    assert report['include_archived'] is True


def test_result_limit_applies_after_group_count(owner):
    for n in range(4):
        add(owner, f'https://a.example/{n}', f'body {n}')
        add(owner, f'https://b.example/{n}', f'body {n}')
    report = owner.offline_research_source_overlap(limit=2)
    assert report['group_count'] == 4
    assert report['displayed_group_count'] == 2
    assert report['groups_truncated']
    assert len(report['items']) == 2
    assert [r['key'] for r in report['items']] == sorted(r['key'] for r in report['items'])


def test_more_than_five_ids_and_three_urls_are_bounded(owner):
    for n in range(9):
        add(owner, f'https://source{n}.example/x', 'one shared body')
    group = owner.offline_research_source_overlap()['items'][0]
    assert group['capture_count'] == 9
    assert group['distinct_value_count'] == 9
    assert len(group['capture_ids']) == 5
    assert len(group['claimed_urls']) == 3


def test_newest_2000_only_and_truncation(owner):
    with sqlite3.connect(owner.path) as con:
        rows = [(f'https://unique.example/{n}', 'Synthetic', f'body-{n}', 'manual_text',
                 hashlib.sha256(f'body-{n}'.encode()).hexdigest()) for n in range(2001)]
        con.executemany('''INSERT INTO offline_research_captures
            (source_url,title,body,capture_kind,content_sha256) VALUES(?,?,?,?,?)''', rows)
    report = owner.offline_research_source_overlap()
    assert report['scanned_capture_count'] == 2000
    assert report['scan_truncated'] is True
    assert report['group_count'] == 0


@pytest.mark.parametrize('kwargs', [
    {'include_archived': 1}, {'include_archived': 'yes'}, {'limit': 0},
    {'limit': 51}, {'limit': 2.0}, {'limit': True}, {'limit': '25'},
])
def test_invalid_options_fail_closed(owner, kwargs):
    with pytest.raises(ValueError):
        owner.offline_research_source_overlap(**kwargs)


def test_owner_permission_before_query(owner):
    owner.logout()
    with pytest.raises(AuthenticationError):
        owner.offline_research_source_overlap()


def test_no_network_and_relogin(owner, monkeypatch):
    add(owner, 'https://a.example/x', 'same')
    add(owner, 'https://b.example/x', 'same')
    def deny(*args, **kwargs):
        raise AssertionError('network access is forbidden')
    for attr in ('connect', 'connect_ex', 'sendto', 'sendall'):
        monkeypatch.setattr(socket.socket, attr, deny)
    monkeypatch.setattr(socket, 'getaddrinfo', deny)
    report = owner.offline_research_source_overlap()
    owner.logout()
    other = LocalStore(owner.path)
    other.login('overlap-owner', 'long-password-2026')
    assert other.offline_research_source_overlap() == report


def test_report_does_not_change_sqlite_rows(owner):
    add(owner, 'https://a.example/x', 'same')
    add(owner, 'https://b.example/x', 'same')
    with sqlite3.connect(owner.path) as con:
        before = list(con.iterdump())
        build_source_overlap_report(con)
        after = list(con.iterdump())
    assert before == after
