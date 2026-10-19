"""Stage54 partial: explicit local-only handoff of ALL sampled follow-up URLs."""
import json
import socket
import sqlite3

import pytest

from desktop.research_followup_exports import (
    FORMAT, MAX_EXPORT_BYTES, encode_followup_export, verify_followup_export,
    save_followup_export, build_full_queue_report,
)
from desktop.storage import AuthenticationError, LocalStore


@pytest.fixture
def owner(tmp_path):
    store = LocalStore(tmp_path / 'followup_export.sqlite3')
    store.setup_owner('followup-export-owner', 'long-password-2026')
    return store


def seed(owner, count=91):
    html = '<p>offline</p>' + ''.join(
        f'<a href="/link-{n:03}">Saved</a>' for n in range(count))
    owner.add_offline_research('https://example.org/index', 'Offline HTML',
                               html, 'html_snapshot')


def test_export_all_pages_in_stable_priority_order(owner, tmp_path):
    seed(owner)
    expected = [item['linked_url'] for page in range(1, 4)
                for item in owner.offline_research_followup_queue(page=page)['items']]
    dest = tmp_path / 'full.json'
    assert owner.export_offline_research_followups(dest) == dest
    envelope = json.loads(dest.read_text(encoding='utf-8'))
    assert envelope['format'] == FORMAT
    report = verify_followup_export(dest.read_bytes())
    assert [item['linked_url'] for item in report['items']] == expected
    assert len(report['items']) == 91 and report['filtered_url_count'] == 91
    assert report['page_size'] == 40 and report['sample_limit'] == 2000
    assert not report['source_authenticity_verified'] and not report['network_accessed']
    assert dest.read_bytes() == encode_followup_export(report)


def test_export_filtered_results_after_reopen(owner, tmp_path):
    seed(owner, 55)
    for n in range(45):
        owner.record_offline_research_followup_note(
            f'https://example.org/link-{n:03}', 'deferred', 'Manual pending work')
    owner.record_offline_research_followup_note(
        'https://example.org/link-044', 'reopen', 'Recheck this one')
    path = tmp_path / 'pending.json'
    owner.export_offline_research_followups(path, review_filter='pending')
    report = verify_followup_export(path.read_bytes())
    assert report['review_filter'] == 'pending'
    assert len(report['items']) == 11
    assert report['review_counts'] == {'pending': 11, 'deferred': 44}
    assert report['items'][0]['linked_url'].endswith('link-044')
    assert report['items'][0]['manual_review']['action'] == 'reopen'
    assert report['items'][0]['manual_review']['note'] == 'Recheck this one'
    path2 = tmp_path / 'deferred.json'
    owner.export_offline_research_followups(path2, review_filter='deferred')
    assert len(verify_followup_export(path2.read_bytes())['items']) == 44


def test_empty_queue_round_trip(owner, tmp_path):
    path = tmp_path / 'empty.json'
    owner.export_offline_research_followups(path)
    report = verify_followup_export(path.read_bytes())
    assert report['items'] == [] and report['filtered_url_count'] == 0
    assert report['unique_url_count'] == 0


def test_owner_login_before_file_path_probe(owner, tmp_path):
    seed(owner, 1)
    owner.logout()
    with pytest.raises(AuthenticationError):
        owner.export_offline_research_followups(tmp_path / 'missing' / 'private.json')
    assert not (tmp_path / 'missing').exists()


def test_export_does_not_change_existing_sqlite(owner, tmp_path):
    seed(owner)
    with sqlite3.connect(owner.path) as con:
        before = list(con.iterdump())
    owner.export_offline_research_followups(tmp_path / 'all.json')
    with sqlite3.connect(owner.path) as con:
        assert list(con.iterdump()) == before


def test_existing_file_never_overwritten(owner, tmp_path):
    path = tmp_path / 'existing.json'
    path.write_text('DO NOT OVERWRITE', encoding='utf-8')
    with pytest.raises(FileExistsError):
        owner.export_offline_research_followups(path)
    assert path.read_text(encoding='utf-8') == 'DO NOT OVERWRITE'


def test_existing_symlink_not_followed(owner, tmp_path):
    target = tmp_path / 'target.json'
    target.write_text('UNCHANGED', encoding='utf-8')
    link = tmp_path / 'link.json'
    try:
        link.symlink_to(target)
    except (OSError, NotImplementedError):
        pytest.skip('symlink not supported')
    with pytest.raises(FileExistsError):
        owner.export_offline_research_followups(link)
    assert target.read_text(encoding='utf-8') == 'UNCHANGED'


@pytest.mark.parametrize('bad_path', ['', ' ', None, 2, 'relative.json', '//server/share/x.json',
                                      '\\\\server\\share\\x.json'])
def test_bad_destination_rejected(owner, bad_path):
    with pytest.raises(ValueError):
        save_followup_export(build_full_queue_report_for_test(owner), bad_path)


def build_full_queue_report_for_test(owner):
    with owner._connect() as con:
        return build_full_queue_report(con)


def test_tampering_detected(owner):
    seed(owner, 2)
    raw = encode_followup_export(build_full_queue_report_for_test(owner))
    data = json.loads(raw)
    data['report']['items'][0]['linked_url'] = 'https://attacker.invalid/changed'
    with pytest.raises(ValueError, match='체크섬'):
        verify_followup_export(json.dumps(data).encode('utf-8'))


def test_wrong_flags_format_and_size_rejected(owner):
    report = build_full_queue_report_for_test(owner)
    for key in ('network_accessed', 'source_authenticity_verified'):
        changed = dict(report, **{key: True})
        with pytest.raises(ValueError):
            encode_followup_export(changed)
    raw = encode_followup_export(report)
    data = json.loads(raw)
    data['source_authenticity'] = 'verified'
    with pytest.raises(ValueError):
        verify_followup_export(json.dumps(data).encode('utf-8'))
    with pytest.raises(ValueError):
        verify_followup_export(b'not-json')
    with pytest.raises(ValueError):
        verify_followup_export(b'0' * (MAX_EXPORT_BYTES + 1))


def test_network_blocked_during_export(owner, tmp_path, monkeypatch):
    seed(owner, 7)
    def denied(*args, **kwargs):
        raise AssertionError('outbound socket forbidden')
    monkeypatch.setattr(socket.socket, 'connect', denied)
    monkeypatch.setattr(socket.socket, 'connect_ex', denied)
    monkeypatch.setattr(socket, 'create_connection', denied)
    path = tmp_path / 'offline.json'
    owner.export_offline_research_followups(path)
    assert verify_followup_export(path.read_bytes())['network_accessed'] is False


def test_stable_after_relogin(owner, tmp_path):
    seed(owner, 41)
    first = tmp_path / 'first.json'
    owner.export_offline_research_followups(first)
    path = owner.path
    owner.logout()
    restored = LocalStore(path)
    restored.login('followup-export-owner', 'long-password-2026')
    second = tmp_path / 'second.json'
    restored.export_offline_research_followups(second)
    assert first.read_bytes() == second.read_bytes()


def test_reject_nested_read_transaction(owner):
    with owner._connect() as con:
        con.execute('BEGIN')
        with pytest.raises(ValueError, match='트랜잭션'):
            build_full_queue_report(con)
        con.rollback()


def test_export_scan_cap_is_explicit(owner, tmp_path):
    # Seed 2,100 local HTML link rows without network access; only newest 2,000
    # may appear in the exported bounded queue, and truncation must be visible.
    with owner._connect() as con:
        for capture in range(21):
            cursor = con.execute('''INSERT INTO offline_research_captures
                (source_url,title,body,capture_kind,content_sha256)
                VALUES (?,?,?,?,?)''',
                (f'https://example.org/c{capture}', 'saved', 'text',
                 'html_snapshot', '0' * 64))
            ident = cursor.lastrowid
            con.executemany('''INSERT INTO offline_research_html_links
                (capture_id,position,linked_url) VALUES (?,?,?)''',
                [(ident, p + 1, f'https://example.org/c{capture}/item{p}')
                 for p in range(100)])
    path = tmp_path / 'capped.json'
    owner.export_offline_research_followups(path)
    report = verify_followup_export(path.read_bytes())
    assert report['scan_truncated'] is True
    assert report['scanned_link_count'] == 2000
    assert report['unique_url_count'] == 2000
    assert len(report['items']) == 2000
    assert all('/c0/' not in item['linked_url'] for item in report['items'])


def test_archived_referrer_scope_preserved(owner, tmp_path):
    seed(owner, 2)
    ident = owner.search_offline_research('Offline HTML')[0]['id']
    owner.archive_offline_research(ident)
    active = tmp_path / 'active.json'
    archived = tmp_path / 'archived.json'
    owner.export_offline_research_followups(active)
    owner.export_offline_research_followups(archived, include_archived=True)
    assert verify_followup_export(active.read_bytes())['items'] == []
    report = verify_followup_export(archived.read_bytes())
    assert report['include_archived_referrers'] is True
    assert len(report['items']) == 2
