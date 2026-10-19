"""Stage54 local batch file recheck: all manual, offline and read-only."""
import json
import socket
from pathlib import Path
from unittest.mock import patch

import pytest

from desktop.storage import LocalStore, AuthenticationError


@pytest.fixture
def bundle(tmp_path):
    store = LocalStore(tmp_path / 'company.sqlite3')
    store.setup_owner('audit-owner', 'offline-custody-password-2026')
    first, second = tmp_path / 'a.txt', tmp_path / 'b.html'
    first.write_text('Original alpha text', encoding='utf-8')
    second.write_text('<article><p>Other evidence</p></article>', encoding='utf-8')
    manifest = tmp_path / 'sources.json'
    store.create_offline_research_bundle_manifest([
        (first, 'https://example.org/alpha', 'Alpha claim'),
        (second, 'https://example.org/beta', 'Beta claim')], manifest)
    preview = store.preview_offline_research_bundle(manifest)
    stored = store.import_offline_research_bundle(
        manifest, expected_preview_token=preview['preview_token'])
    return store, tmp_path, manifest, stored


def test_original_bytes_match_and_db_unchanged(bundle):
    store, folder, manifest, imported = bundle
    db_before = store.path.read_bytes()
    result = store.verify_imported_offline_research_bundle(manifest)
    assert result['passed'] and result['records_consistent']
    assert result['batch_id'] == imported['batch_id']
    assert result['counts'] == {'match': 2, 'changed': 0, 'unavailable': 0, 'record_mismatch': 0}
    assert [i['status'] for i in result['items']] == ['match', 'match']
    assert result['web_source_verified'] is False
    assert result['original_folder_authenticated'] is False
    assert result['network_accessed'] is False and result['database_modified'] is False
    assert store.path.read_bytes() == db_before


def test_changed_file_is_detected_without_modifying_evidence(bundle):
    store, folder, manifest, imported = bundle
    before = store.read_offline_research(imported['capture_ids'][0])
    (folder / 'a.txt').write_text('Changed alpha text', encoding='utf-8')
    result = store.verify_imported_offline_research_bundle(manifest)
    assert result['counts']['changed'] == 1
    assert result['counts']['match'] == 1
    assert not result['passed']
    assert store.read_offline_research(imported['capture_ids'][0]) == before


def test_missing_file_is_reported_not_fatal(bundle):
    store, folder, manifest, _ = bundle
    (folder / 'a.txt').unlink()
    result = store.verify_imported_offline_research_bundle(manifest)
    assert result['counts']['unavailable'] == 1
    assert result['items'][1]['status'] == 'match'


def test_invalid_utf8_file_is_unavailable(bundle):
    store, folder, manifest, _ = bundle
    (folder / 'a.txt').write_bytes(b'\xff\xfe\x00')
    result = store.verify_imported_offline_research_bundle(manifest)
    assert result['counts']['unavailable'] == 1
    assert not result['passed']


def test_same_bytes_in_copied_manifest_folder_not_proof_of_origin(bundle, tmp_path):
    store, folder, manifest, _ = bundle
    copy = folder / 'copies'
    copy.mkdir()
    (copy / 'sources.json').write_bytes(manifest.read_bytes())
    for filename in ('a.txt', 'b.html'):
        (copy / filename).write_bytes((folder / filename).read_bytes())
    result = store.verify_imported_offline_research_bundle(copy / 'sources.json')
    assert result['passed']
    assert not result['original_folder_authenticated']


def test_changed_manifest_rejected_before_file_access(bundle):
    store, folder, manifest, _ = bundle
    document = json.loads(manifest.read_text(encoding='utf-8'))
    document['items'][0]['title'] = 'Unregistered title'
    manifest.write_text(json.dumps(document), encoding='utf-8')
    with pytest.raises(ValueError, match='등록된.*이력'):
        store.verify_imported_offline_research_bundle(manifest)


def test_unimported_manifest_rejected(tmp_path):
    store = LocalStore(tmp_path / 'company.sqlite3')
    store.setup_owner('audit-owner', 'offline-custody-password-2026')
    (tmp_path / 'a.txt').write_text('local', encoding='utf-8')
    manifest = tmp_path / 'new.json'
    store.create_offline_research_bundle_manifest([
        (tmp_path / 'a.txt', 'https://example.org/unique', 'Test')], manifest)
    with pytest.raises(ValueError, match='등록된.*이력'):
        store.verify_imported_offline_research_bundle(manifest)


def test_symlinked_file_is_not_followed(bundle):
    store, folder, manifest, _ = bundle
    (folder / 'a.txt').rename(folder / 'new-name.txt')
    try:
        (folder / 'a.txt').symlink_to(folder / 'new-name.txt')
    except (OSError, NotImplementedError):
        pytest.skip('symlinks unavailable')
    result = store.verify_imported_offline_research_bundle(manifest)
    assert result['counts']['unavailable'] == 1


def test_symlinked_manifest_parent_rejected(bundle):
    store, folder, manifest, _ = bundle
    linked = folder / 'alias'
    try:
        linked.symlink_to(folder, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip('symlinks unavailable')
    with pytest.raises(ValueError, match='심볼릭'):
        store.verify_imported_offline_research_bundle(linked / 'sources.json')


def test_archived_capture_is_still_checked(bundle):
    store, folder, manifest, imported = bundle
    store.archive_offline_research(imported['capture_ids'][0])
    result = store.verify_imported_offline_research_bundle(manifest)
    assert result['passed'] and result['items'][0]['archived']


def test_logged_out_cannot_verify(bundle):
    store, folder, manifest, _ = bundle
    store.logout()
    with pytest.raises((AuthenticationError, PermissionError)):
        store.verify_imported_offline_research_bundle(manifest)


def test_no_socket_or_dns_access(bundle):
    store, folder, manifest, _ = bundle
    def blocked(*args, **kwargs):
        raise AssertionError('Network calls forbidden')
    with patch.object(socket.socket, 'connect', blocked), \
         patch.object(socket.socket, 'connect_ex', blocked), \
         patch.object(socket.socket, 'sendall', blocked), \
         patch.object(socket.socket, 'sendto', blocked), \
         patch.object(socket, 'getaddrinfo', blocked):
        assert store.verify_imported_offline_research_bundle(manifest)['passed']


def test_batch_audit_leaves_other_batches_intact(bundle):
    store, folder, manifest, first = bundle
    (folder / 'third.md').write_text('third local document', encoding='utf-8')
    another = folder / 'second.json'
    store.create_offline_research_bundle_manifest([
        (folder / 'third.md', 'https://example.org/third', 'Other')], another)
    preview = store.preview_offline_research_bundle(another)
    second = store.import_offline_research_bundle(another,
        expected_preview_token=preview['preview_token'])
    assert store.verify_imported_offline_research_bundle(manifest)['batch_id'] == first['batch_id']
    assert store.verify_imported_offline_research_bundle(another)['batch_id'] == second['batch_id']
