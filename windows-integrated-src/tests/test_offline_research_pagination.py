"""Stage54 partial: browse every locally sampled follow-up URL, no web access."""
import socket
import sqlite3

import pytest

from desktop.storage import AuthenticationError, LocalStore
from desktop.research_followups import build_followup_queue, MAX_SCANNED_LINKS


@pytest.fixture
def owner(tmp_path):
    store = LocalStore(tmp_path / 'paged.sqlite3')
    store.setup_owner('pagination-owner', 'pagination-password-2026')
    return store


def seed(owner, count=94):
    # Under the 100-links-per-capture limit; each link has a distinct URL.
    html = '<p>Saved locally</p>' + ''.join(
        f'<a href="/item-{n:03}">Reference</a>' for n in range(count))
    owner.add_offline_research('https://example.org/index', 'Offline HTML',
                               html, 'html_snapshot')


def test_pages_cover_all_urls_without_overlap(owner):
    seed(owner)
    seen = []
    for page, expected_size in ((1, 40), (2, 40), (3, 14)):
        report = owner.offline_research_followup_queue(page=page)
        assert len(report['items']) == expected_size
        assert report['page'] == page and report['page_count'] == 3
        assert report['filtered_url_count'] == 94
        assert report['has_previous_page'] == (page > 1)
        assert report['has_next_page'] == (page < 3)
        assert report['results_truncated'] == (page < 3)
        assert not report['network_accessed']
        seen.extend(item['linked_url'] for item in report['items'])
    assert len(set(seen)) == 94
    assert seen == sorted(seen)


def test_short_limit_pages_and_out_of_range(owner):
    seed(owner, 5)
    first = owner.offline_research_followup_queue(page=1, limit=2)
    last = owner.offline_research_followup_queue(page=3, limit=2)
    beyond = owner.offline_research_followup_queue(page=4, limit=2)
    assert first['page_count'] == 3
    assert len(last['items']) == 1 and not last['has_next_page']
    assert beyond['items'] == [] and beyond['page_out_of_range']
    assert beyond['page_count'] == 3
    assert beyond['has_previous_page']


def test_empty_queue_page_metadata(owner):
    first = owner.offline_research_followup_queue()
    assert first['items'] == [] and first['page_count'] == 1
    assert first['filtered_url_count'] == 0
    assert not first['has_next_page']
    assert owner.offline_research_followup_queue(page=2)['page_out_of_range']


def test_manual_filter_before_pagination(owner):
    seed(owner, 90)
    for n in range(50):
        owner.record_offline_research_followup_note(
            f'https://example.org/item-{n:03}', 'deferred', 'Manual later')
    pending = owner.offline_research_followup_queue(review_filter='pending', page=1)
    assert pending['page_count'] == 1
    assert len(pending['items']) == 40
    assert pending['items'][0]['linked_url'].endswith('item-050')
    deferred = owner.offline_research_followup_queue(review_filter='deferred', page=2)
    assert len(deferred['items']) == 10
    assert deferred['items'][0]['linked_url'].endswith('item-040')
    assert deferred['filtered_url_count'] == 50
    assert deferred['review_counts'] == {'pending': 40, 'deferred': 50}


def test_reopen_changes_page_count(owner):
    seed(owner, 41)
    for n in range(41):
        owner.record_offline_research_followup_note(
            f'https://example.org/item-{n:03}', 'deferred', 'Waiting')
    assert owner.offline_research_followup_queue(review_filter='deferred')['page_count'] == 2
    owner.record_offline_research_followup_note(
        'https://example.org/item-040', 'reopen', 'Reopened')
    after = owner.offline_research_followup_queue(review_filter='deferred', page=2)
    assert after['page_out_of_range'] and after['items'] == []
    assert after['page_count'] == 1


@pytest.mark.parametrize('page', [0, -1, 2001, True, 1.0, '1', None, [], {}])
def test_reject_invalid_pages(owner, page):
    with pytest.raises(ValueError):
        owner.offline_research_followup_queue(page=page)


def test_owner_permission_before_page_lookup(owner):
    seed(owner)
    owner.logout()
    with pytest.raises(AuthenticationError):
        owner.offline_research_followup_queue(page=2)


def test_page_is_read_only_persistent_and_offline(owner, monkeypatch):
    seed(owner)
    with sqlite3.connect(owner.path) as con:
        before = list(con.iterdump())
    def denied(*args, **kwargs):
        raise AssertionError('Unexpected network call')
    monkeypatch.setattr(socket.socket, 'connect', denied)
    monkeypatch.setattr(socket.socket, 'connect_ex', denied)
    monkeypatch.setattr(socket, 'create_connection', denied)
    report = owner.offline_research_followup_queue(page=2)
    with sqlite3.connect(owner.path) as con:
        assert list(con.iterdump()) == before
    path = owner.path
    owner.logout()
    restored = LocalStore(path)
    restored.login('pagination-owner', 'pagination-password-2026')
    assert restored.offline_research_followup_queue(page=2) == report


def test_scan_cap_is_not_confused_with_page_cap(tmp_path):
    con = sqlite3.connect(tmp_path / 'cap.sqlite3')
    from desktop.research_captures import initialize
    initialize(con)
    for capture in range(1, 22):
        con.execute('''INSERT INTO offline_research_captures
            (source_url,title,body,capture_kind,content_sha256)
            VALUES (?,?,?,?,?)''',
            (f'https://example.org/c{capture}', str(capture), 'body',
             'html_snapshot', '0' * 64))
        con.executemany('''INSERT INTO offline_research_html_links
            (capture_id,position,linked_url) VALUES (?,?,?)''',
            [(capture, p, f'https://example.org/target-{capture}-{p}')
             for p in range(1, 101)])
    report = build_followup_queue(con, page=50)
    assert report['scan_truncated']
    assert report['scanned_link_count'] == MAX_SCANNED_LINKS
    assert report['page_count'] == 50
    assert len(report['items']) == 40
    assert not report['has_next_page']
    con.close()
