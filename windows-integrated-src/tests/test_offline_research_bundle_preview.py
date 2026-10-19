"""Stage54: owner-visible local bundle preview and verified import; no network."""
import hashlib
import json
import socket
import sqlite3

import pytest

from desktop.storage import AuthenticationError, LocalStore


@pytest.fixture
def setup(tmp_path):
    store = LocalStore(tmp_path / 'company.sqlite3')
    store.setup_owner('bundle-preview-owner', 'local-password-2026')
    one = tmp_path / 'one.html'
    one.write_bytes(b'<h1>First body</h1><script>skip()</script>')
    two = tmp_path / 'two.txt'
    two.write_text('Another offline body', encoding='utf-8')
    manifest = tmp_path / 'manifest.json'
    entries = [{'file': 'one.html', 'url': 'https://example.org/a', 'title': 'First'},
               {'file': 'two.txt', 'url': 'https://example.org/b', 'title': 'Second'}]
    def save():
        manifest.write_text(json.dumps({'format': 'aiwack-offline-research-bundle-v1',
                                        'items': entries}, ensure_ascii=False), encoding='utf-8')
    save()
    return store, manifest, one, two, entries, save


def test_preview_exact_metadata_no_changes(setup):
    store, manifest, one, two, entries, save = setup
    before = store.path.read_bytes()
    report = store.preview_offline_research_bundle(manifest)
    assert report['importable'] and report['item_count'] == 2
    assert report['duplicate_count'] == 0
    assert [item['status'] for item in report['items']] == ['new', 'new']
    assert report['items'][0]['raw_sha256'] == hashlib.sha256(one.read_bytes()).hexdigest()
    assert report['items'][0]['content_sha256'] == hashlib.sha256(b'First body').hexdigest()
    assert report['items'][0]['kind'] == 'html_snapshot'
    assert report['items'][1]['kind'] == 'manual_text'
    assert report['manifest_sha256'] == hashlib.sha256(manifest.read_bytes()).hexdigest()
    assert len(report['preview_token']) == 64
    assert report['database_modified'] is False and report['network_accessed'] is False
    assert report['web_source_verified'] is False and report['approval_is_signature'] is False
    assert store.path.read_bytes() == before
    assert store.search_offline_research() == []


def test_confirmed_import_matches_preview(setup):
    store, manifest, *_ = setup
    preview = store.preview_offline_research_bundle(manifest)
    result = store.import_offline_research_bundle(manifest,
                                                 expected_preview_token=preview['preview_token'])
    assert len(result['capture_ids']) == preview['item_count']
    assert result['manifest_sha256'] == preview['manifest_sha256']
    assert store.read_offline_research(result['capture_ids'][0])['body'] == 'First body'


def test_existing_duplicate_blocks_preview(setup):
    store, manifest, one, *_ = setup
    ident = store.import_offline_research_file('https://example.org/a', 'old title', one)
    preview = store.preview_offline_research_bundle(manifest)
    assert not preview['importable'] and preview['duplicate_count'] == 1
    assert preview['items'][0]['status'] == 'already_registered'
    assert preview['items'][0]['existing_capture_id'] == ident
    assert preview['items'][1]['status'] == 'new'
    assert len(store.search_offline_research()) == 1


def test_archived_duplicate_still_detected(setup):
    store, manifest, one, *_ = setup
    ident = store.import_offline_research_file('https://example.org/a', 'old', one)
    store.archive_offline_research(ident)
    preview = store.preview_offline_research_bundle(manifest)
    assert not preview['importable']
    assert preview['items'][0]['existing_capture_id'] == ident


def test_internal_same_url_and_body_detected(setup):
    store, manifest, one, two, entries, save = setup
    two.write_text('First body', encoding='utf-8')
    entries[1]['url'] = entries[0]['url']
    save()
    report = store.preview_offline_research_bundle(manifest)
    assert not report['importable'] and report['duplicate_count'] == 1
    assert report['items'][1]['status'] == 'duplicate_in_bundle'
    assert report['items'][1]['duplicate_of_ordinal'] == 1
    assert store.search_offline_research() == []


def test_same_url_different_body_is_allowed_as_version_candidate(setup):
    store, manifest, one, two, entries, save = setup
    entries[1]['url'] = entries[0]['url']
    save()
    report = store.preview_offline_research_bundle(manifest)
    assert report['importable']
    assert [item['status'] for item in report['items']] == ['new', 'new']


@pytest.mark.parametrize('which', ['file_same_length', 'file_content', 'manifest_title',
                                   'manifest_url', 'manifest_order', 'manifest_whitespace'])
def test_changed_data_after_preview_is_rejected_atomically(setup, which):
    store, manifest, one, two, entries, save = setup
    preview = store.preview_offline_research_bundle(manifest)
    if which == 'file_same_length':
        one.write_bytes(one.read_bytes().replace(b'First', b'Other'))
    elif which == 'file_content':
        two.write_text('Changed', encoding='utf-8')
    elif which == 'manifest_title':
        entries[0]['title'] = 'Changed'
        save()
    elif which == 'manifest_url':
        entries[0]['url'] = 'https://example.org/new'
        save()
    elif which == 'manifest_order':
        entries.reverse()
        save()
    else:
        manifest.write_text(manifest.read_text() + '\n', encoding='utf-8')
    before = store.path.read_bytes()
    with pytest.raises(ValueError, match='다시 검토'):
        store.import_offline_research_bundle(manifest,
                                             expected_preview_token=preview['preview_token'])
    assert store.path.read_bytes() == before
    assert not store.search_offline_research()


@pytest.mark.parametrize('token', ['', '0'*64, 123, False, 'bogus', '\ud55c'*64])
def test_invalid_approval_tokens_rejected(setup, token):
    store, manifest, *_ = setup
    with pytest.raises(ValueError, match='다시 검토'):
        store.import_offline_research_bundle(manifest, expected_preview_token=token)
    assert not store.search_offline_research()


def test_second_import_between_preview_and_confirmation_is_atomic(setup):
    store, manifest, one, *_ = setup
    token = store.preview_offline_research_bundle(manifest)['preview_token']
    store.import_offline_research_file('https://example.org/b', 'old', setup[3])
    with pytest.raises(ValueError, match='이미 등록'):
        store.import_offline_research_bundle(manifest, expected_preview_token=token)
    assert len(store.search_offline_research()) == 1
    with sqlite3.connect(store.path) as con:
        assert con.execute('SELECT COUNT(*) FROM offline_research_batches').fetchone()[0] == 0


def test_logout_denies_preview_without_touching_file(setup):
    store, manifest, *_ = setup
    store.logout()
    manifest.unlink()
    with pytest.raises(AuthenticationError):
        store.preview_offline_research_bundle(manifest)


def test_relogin_preview_and_import(setup):
    store, manifest, *_ = setup
    store.logout()
    reopened = LocalStore(store.path)
    reopened.login('bundle-preview-owner', 'local-password-2026')
    token = reopened.preview_offline_research_bundle(manifest)['preview_token']
    assert len(reopened.import_offline_research_bundle(manifest, expected_preview_token=token)['capture_ids']) == 2


def test_failed_preview_file_never_changes_db(setup):
    store, manifest, one, *_ = setup
    one.unlink()
    before = store.path.read_bytes()
    with pytest.raises(ValueError):
        store.preview_offline_research_bundle(manifest)
    assert store.path.read_bytes() == before


def test_unsafe_manifest_rejected(setup, tmp_path):
    store, manifest, *_ = setup
    for value in ('/tmp/does-not-exist.json', 'relative.json', '//share/file.json', '\\\\server\\share\\bundle.json'):
        with pytest.raises(ValueError):
            store.preview_offline_research_bundle(value)
    link = tmp_path / 'link.json'
    try:
        link.symlink_to(manifest)
    except (OSError, NotImplementedError):
        pytest.skip('symlinks not available')
    with pytest.raises(ValueError):
        store.preview_offline_research_bundle(link)


def test_network_blocked_for_preview_and_guarded_import(setup, monkeypatch):
    store, manifest, *_ = setup
    def forbid(*args, **kwargs):
        raise AssertionError('network forbidden')
    for attr in ('connect', 'connect_ex', 'sendto', 'sendall'):
        monkeypatch.setattr(socket.socket, attr, forbid)
    monkeypatch.setattr(socket, 'getaddrinfo', forbid)
    token = store.preview_offline_research_bundle(manifest)['preview_token']
    assert len(store.import_offline_research_bundle(manifest, expected_preview_token=token)['capture_ids']) == 2
