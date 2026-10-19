"""Stage54 partial: owner-only read-only follow-up JSON recheck."""
import json
import socket
import sqlite3

import pytest

from desktop.storage import AuthenticationError, LocalStore
from desktop.research_followup_exports import verify_followup_export


@pytest.fixture
def owner(tmp_path):
    store = LocalStore(tmp_path / 'local.sqlite3')
    store.setup_owner('followup-verify-owner', 'followup-verify-password-2026')
    return store


def seed(owner, count=3):
    owner.add_offline_research('https://example.org/index', 'HTML',
        '<p>offline</p>' + ''.join(f'<a href="/item-{i}">link</a>' for i in range(count)),
        'html_snapshot')


def exported(owner, tmp_path, **options):
    path = tmp_path / 'followups.json'
    owner.export_offline_research_followups(path, **options)
    return path


def test_unchanged_report_and_read_only(owner, tmp_path):
    seed(owner)
    path = exported(owner, tmp_path)
    with sqlite3.connect(owner.path) as con:
        before = list(con.iterdump())
    result = owner.inspect_offline_research_followup_export(path)
    assert result['checksum_matches'] and result['local_report_matches']
    assert result['exported_url_count'] == result['current_url_count'] == 3
    assert result['unchanged_url_count'] == 3
    assert not result['source_authenticity_verified'] and not result['network_accessed']
    with sqlite3.connect(owner.path) as con:
        assert list(con.iterdump()) == before


def test_new_url_and_archived_referrer(owner, tmp_path):
    seed(owner, 2)
    path = exported(owner, tmp_path)
    owner.add_offline_research('https://example.org/another', 'new',
                               '<a href="/new">new</a>', 'html_snapshot')
    result = owner.inspect_offline_research_followup_export(path)
    assert not result['local_report_matches']
    assert result['added_url_count'] == 1
    assert result['added_urls_preview'] == ['https://example.org/new']
    assert result['unchanged_url_count'] == 2
    ident = owner.search_offline_research('HTML')[0]['id']
    owner.archive_offline_research(ident)
    result = owner.inspect_offline_research_followup_export(path)
    assert result['missing_url_count'] == 2
    assert result['missing_urls_preview'] == [f'https://example.org/item-{i}' for i in range(2)]


def test_note_change_is_not_url_addition(owner, tmp_path):
    seed(owner)
    path = exported(owner, tmp_path)
    owner.record_offline_research_followup_note('https://example.org/item-0',
                                                 'deferred', 'Later')
    result = owner.inspect_offline_research_followup_export(path)
    assert result['changed_url_count'] == 1
    assert result['changed_urls_preview'] == ['https://example.org/item-0']
    assert result['added_url_count'] == result['missing_url_count'] == 0
    assert result['unchanged_url_count'] == 2


def test_filter_and_archive_scope_are_preserved(owner, tmp_path):
    seed(owner, 2)
    owner.record_offline_research_followup_note('https://example.org/item-0',
                                                 'deferred', 'later')
    path = exported(owner, tmp_path, include_archived=True, review_filter='deferred')
    ident = owner.search_offline_research('HTML')[0]['id']
    owner.archive_offline_research(ident)
    result = owner.inspect_offline_research_followup_export(path)
    assert result['review_filter'] == 'deferred'
    assert result['include_archived_referrers']
    assert result['local_report_matches']
    assert result['exported_url_count'] == 1


def test_filter_reopen_removes_url(owner, tmp_path):
    seed(owner, 2)
    owner.record_offline_research_followup_note('https://example.org/item-0',
                                                 'deferred', 'later')
    path = exported(owner, tmp_path, review_filter='deferred')
    owner.record_offline_research_followup_note('https://example.org/item-0',
                                                 'reopen', 'recheck')
    result = owner.inspect_offline_research_followup_export(path)
    assert result['missing_url_count'] == 1 and result['current_url_count'] == 0


def test_tampered_report_rejected(owner, tmp_path):
    seed(owner)
    path = exported(owner, tmp_path)
    data = json.loads(path.read_text(encoding='utf-8'))
    data['report']['items'][0]['linked_url'] = 'https://fake.invalid'
    path.write_text(json.dumps(data), encoding='utf-8')
    with pytest.raises(ValueError, match='체크섬'):
        owner.inspect_offline_research_followup_export(path)


def test_invalid_json_and_missing_file(owner, tmp_path):
    path = tmp_path / 'broken.json'
    path.write_text('{', encoding='utf-8')
    with pytest.raises(ValueError):
        owner.inspect_offline_research_followup_export(path)
    with pytest.raises(FileNotFoundError):
        owner.inspect_offline_research_followup_export(tmp_path / 'missing.json')


def test_reject_unsafe_paths_and_large_file(owner, tmp_path):
    path = tmp_path / 'big.json'
    path.write_bytes(b' ' * (12_000_000 + 1))
    with pytest.raises(ValueError, match='크기'):
        owner.inspect_offline_research_followup_export(path)
    with pytest.raises(ValueError):
        owner.inspect_offline_research_followup_export('relative.json')
    with pytest.raises(ValueError):
        owner.inspect_offline_research_followup_export('\\\\server\\share\\data.json')
    with pytest.raises(ValueError):
        owner.inspect_offline_research_followup_export(tmp_path)


def test_symlink_rejected(owner, tmp_path):
    seed(owner)
    path = exported(owner, tmp_path)
    link = tmp_path / 'link.json'
    try:
        link.symlink_to(path)
    except (OSError, NotImplementedError):
        pytest.skip('symlinks unavailable')
    with pytest.raises(ValueError, match='일반'):
        owner.inspect_offline_research_followup_export(link)


def test_permission_checked_before_path(owner, tmp_path):
    owner.logout()
    with pytest.raises(AuthenticationError):
        owner.inspect_offline_research_followup_export(tmp_path / 'nonexistent.json')


def test_relogin_recheck_and_blocked_network(owner, tmp_path, monkeypatch):
    seed(owner)
    path = exported(owner, tmp_path)
    owner.logout()
    restored = LocalStore(owner.path)
    restored.login('followup-verify-owner', 'followup-verify-password-2026')
    def deny(*args, **kwargs):
        raise AssertionError('network forbidden')
    monkeypatch.setattr(socket.socket, 'connect', deny)
    monkeypatch.setattr(socket.socket, 'connect_ex', deny)
    monkeypatch.setattr(socket, 'create_connection', deny)
    assert restored.inspect_offline_research_followup_export(path)['local_report_matches']
    assert verify_followup_export(path.read_bytes())['network_accessed'] is False


def test_more_than_twenty_urls_preview_is_bounded(owner, tmp_path):
    seed(owner, 35)
    path = exported(owner, tmp_path)
    ident = owner.search_offline_research('HTML')[0]['id']
    owner.archive_offline_research(ident)
    result = owner.inspect_offline_research_followup_export(path)
    assert result['missing_url_count'] == 35
    assert len(result['missing_urls_preview']) == 20


def test_metadata_change_only(owner, tmp_path):
    seed(owner, 2)
    path = exported(owner, tmp_path)
    # New referrer with existing URLs changes referrer counts and ID lists.
    owner.add_offline_research('https://example.org/index2', 'HTML2',
        '<a href="https://example.org/item-0">ref</a>', 'html_snapshot')
    result = owner.inspect_offline_research_followup_export(path)
    assert result['changed_url_count'] == 1
    assert result['unchanged_url_count'] == 1
