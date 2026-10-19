"""File-byte custody is local evidence comparison, not source authentication."""
import hashlib
import shutil
import socket
import sqlite3

import pytest

from desktop.research_captures import MAX_RAW_BYTES
from desktop.storage import LocalStore, AuthenticationError


@pytest.fixture
def owner(tmp_path):
    store = LocalStore(tmp_path / 'company.sqlite3')
    store.setup_owner('custody-owner', 'safe-password-2026')
    return store


@pytest.fixture
def capture(owner, tmp_path):
    original = tmp_path / 'snapshot.html'
    original.write_bytes(b'<h1>Snapshot 2026</h1>')
    ident = owner.import_offline_research_file('https://example.org/snapshot', 'Saved', original)
    return ident, original


def test_matching_original_file(owner, capture):
    ident, original = capture
    report = owner.recheck_offline_research_import_file(ident, original)
    assert report['bytes_match'] and report['size_match'] and report['filename_match']
    assert report['recorded_size'] == report['selected_size'] == len(original.read_bytes())
    assert report['recorded_sha256'] == report['selected_sha256'] == hashlib.sha256(original.read_bytes()).hexdigest()
    assert report['original_file_bytes_rechecked']
    assert not report['web_source_verified'] and not report['network_accessed']
    assert not report['database_modified']
    assert report['claimed_source_url'] == 'https://example.org/snapshot'


def test_renamed_same_bytes_still_equal(owner, capture, tmp_path):
    ident, original = capture
    renamed = tmp_path / 'another-copy.bin'
    shutil.copyfile(original, renamed)
    report = owner.recheck_offline_research_import_file(ident, renamed)
    assert report['bytes_match'] and not report['filename_match']


def test_same_length_tampering_detected(owner, capture):
    ident, original = capture
    data = original.read_bytes()
    original.write_bytes(data.replace(b'2026', b'2025'))
    report = owner.recheck_offline_research_import_file(ident, original)
    assert report['size_match'] and not report['bytes_match']
    assert report['selected_sha256'] != report['recorded_sha256']


def test_different_length_tampering_detected(owner, capture):
    ident, original = capture
    original.write_bytes(b'changed')
    report = owner.recheck_offline_research_import_file(ident, original)
    assert not report['size_match'] and not report['bytes_match']


def test_invalid_utf8_after_import_is_reported_as_mismatch(owner, capture):
    ident, original = capture
    original.write_bytes(b'\xff\xfe')
    assert not owner.recheck_offline_research_import_file(ident, original)['bytes_match']


def test_empty_file_after_import_is_reported_as_mismatch(owner, capture):
    ident, original = capture
    original.write_bytes(b'')
    report = owner.recheck_offline_research_import_file(ident, original)
    assert report['selected_size'] == 0 and not report['bytes_match']


def test_oversized_file_fails_closed(owner, capture):
    ident, original = capture
    original.write_bytes(b'Z' * (MAX_RAW_BYTES + 1))
    with pytest.raises(ValueError, match='256KB'):
        owner.recheck_offline_research_import_file(ident, original)


def test_manual_record_rejected_before_selected_path_is_opened(owner, tmp_path):
    ident = owner.add_offline_research('https://example.org/m', 'Manual', 'entered text')
    with pytest.raises(ValueError, match='로컬 파일'):
        owner.recheck_offline_research_import_file(ident, tmp_path / 'missing.txt')


@pytest.mark.parametrize('capture_id', [0, -1, '1', 1.0, True, None])
def test_invalid_ids_rejected(owner, capture_id):
    with pytest.raises(ValueError):
        owner.recheck_offline_research_import_file(capture_id, '/tmp/none.txt')


def test_unknown_capture_rejected(owner):
    with pytest.raises(ValueError, match='찾을 수 없습니다'):
        owner.recheck_offline_research_import_file(123456, '/tmp/none.txt')


@pytest.mark.parametrize('path', ['', 'relative.txt', '\\\\server\\share\\doc.txt',
                                  '//host/share/doc.txt', None, 7, 'nul\x00file'])
def test_unsafe_paths_rejected(owner, capture, path):
    with pytest.raises(ValueError):
        owner.recheck_offline_research_import_file(capture[0], path)


def test_missing_and_directory_rejected(owner, capture, tmp_path):
    for selected in (tmp_path / 'missing.txt', tmp_path):
        with pytest.raises(ValueError):
            owner.recheck_offline_research_import_file(capture[0], selected)


def test_symlink_file_rejected(owner, capture, tmp_path):
    shortcut = tmp_path / 'alias.txt'
    try:
        shortcut.symlink_to(capture[1])
    except (NotImplementedError, OSError):
        pytest.skip('symlinks not available')
    with pytest.raises(ValueError, match='심볼릭'):
        owner.recheck_offline_research_import_file(capture[0], shortcut)


def test_symlink_parent_rejected(owner, capture, tmp_path):
    shortcut = tmp_path / 'diralias'
    try:
        shortcut.symlink_to(capture[1].parent, target_is_directory=True)
    except (NotImplementedError, OSError):
        pytest.skip('symlinks not available')
    with pytest.raises(ValueError, match='심볼릭'):
        owner.recheck_offline_research_import_file(capture[0], shortcut / capture[1].name)


def test_archived_record_still_checkable(owner, capture):
    ident, original = capture
    owner.archive_offline_research(ident)
    report = owner.recheck_offline_research_import_file(ident, original)
    assert report['archived'] is True and report['bytes_match']


def test_existing_sqlite_data_remains_byte_identical(owner, capture):
    ident, original = capture
    before = owner.path.read_bytes()
    with sqlite3.connect(owner.path) as con:
        logical_before = '\n'.join(con.iterdump())
    owner.recheck_offline_research_import_file(ident, original)
    with sqlite3.connect(owner.path) as con:
        assert '\n'.join(con.iterdump()) == logical_before
    assert owner.path.read_bytes() == before


def test_relogin_and_permission(owner, capture):
    ident, original = capture
    owner.logout()
    with pytest.raises(AuthenticationError):
        owner.recheck_offline_research_import_file(ident, original)
    next_session = LocalStore(owner.path)
    next_session.login('custody-owner', 'safe-password-2026')
    assert next_session.recheck_offline_research_import_file(ident, original)['bytes_match']


def test_no_network_calls(owner, capture, monkeypatch):
    def denied(*args, **kwargs):
        raise AssertionError('unexpected network call')
    for attr in ('connect', 'connect_ex', 'sendto', 'sendall'):
        monkeypatch.setattr(socket.socket, attr, denied)
    monkeypatch.setattr(socket, 'getaddrinfo', denied)
    assert owner.recheck_offline_research_import_file(*capture)['bytes_match']


def test_bundle_import_can_be_rechecked(owner, tmp_path):
    import json
    file = tmp_path / 'article.md'
    file.write_text('Offline article', encoding='utf-8')
    manifest = tmp_path / 'batch.json'
    manifest.write_text(json.dumps({'format': 'aiwack-offline-research-bundle-v1', 'items': [
        {'url': 'https://example.org/article', 'title': 'Article', 'file': file.name}
    ]}), encoding='utf-8')
    ident = owner.import_offline_research_bundle(str(manifest))['capture_ids'][0]
    assert owner.recheck_offline_research_import_file(ident, file)['bytes_match']
