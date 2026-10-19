"""Stage54: prevent newly arrived local evidence from bypassing bundle approval.

All captures are explicitly supplied local text; this never verifies a website.
"""
import json
import socket
import sqlite3
from unittest.mock import patch

import pytest

from desktop.storage import LocalStore, AuthenticationError


@pytest.fixture
def case(tmp_path):
    store = LocalStore(tmp_path / 'records.sqlite3')
    store.setup_owner('context-owner', 'context-owner-password-2026')
    manifest = tmp_path / 'candidate.json'
    (tmp_path / 'candidate.txt').write_text('New offline body', encoding='utf-8')
    manifest.write_text(json.dumps({'format': 'aiwack-offline-research-bundle-v1',
                                    'items': [{'file': 'candidate.txt',
                                               'url': 'https://research.example/topic',
                                               'title': 'Topic'}]}), encoding='utf-8')
    return store, tmp_path, manifest


def test_new_version_on_same_url_invalidates_approved_preview(case):
    store, folder, manifest = case
    initial = store.preview_offline_research_bundle(manifest)
    assert initial['warning_item_count'] == 0
    store.add_offline_research('https://research.example/topic', 'Earlier text', 'Other offline version')
    with pytest.raises(ValueError, match='다시 검토'):
        store.import_offline_research_bundle(manifest, expected_preview_token=initial['preview_token'])
    assert len(store.search_offline_research()) == 1
    with sqlite3.connect(store.path) as con:
        assert con.execute('SELECT COUNT(*) FROM offline_research_batches').fetchone()[0] == 0
    refreshed = store.preview_offline_research_bundle(manifest)
    assert refreshed['preview_token'] != initial['preview_token']
    assert refreshed['warning_category_counts']['existing_url_other_body'] == 1
    assert len(store.import_offline_research_bundle(
        manifest, expected_preview_token=refreshed['preview_token'])['capture_ids']) == 1


def test_new_source_same_body_invalidates_approval(case):
    store, folder, manifest = case
    initial = store.preview_offline_research_bundle(manifest)
    store.add_offline_research('https://other.example/source', 'Mirror', 'New offline body')
    with pytest.raises(ValueError, match='다시 검토'):
        store.import_offline_research_bundle(manifest, expected_preview_token=initial['preview_token'])
    new_preview = store.preview_offline_research_bundle(manifest)
    assert new_preview['warning_category_counts']['existing_body_other_url'] == 1


def test_unrelated_insert_does_not_invalidate_approval(case):
    store, folder, manifest = case
    first = store.preview_offline_research_bundle(manifest)
    store.add_offline_research('https://other.example/unrelated', 'Other', 'Completely different content')
    second = store.preview_offline_research_bundle(manifest)
    assert first['preview_token'] == second['preview_token']
    assert len(store.import_offline_research_bundle(
        manifest, expected_preview_token=first['preview_token'])['capture_ids']) == 1


def test_related_record_archived_does_not_hide_warning(case):
    store, folder, manifest = case
    existing = store.add_offline_research('https://research.example/topic', 'Previous', 'Different body')
    original = store.preview_offline_research_bundle(manifest)
    store.archive_offline_research(existing)
    current = store.preview_offline_research_bundle(manifest)
    assert current['preview_token'] == original['preview_token']
    assert current['warning_item_count'] == 1
    assert len(store.import_offline_research_bundle(
        manifest, expected_preview_token=original['preview_token'])['capture_ids']) == 1


def test_preview_marker_changes_only_for_relevant_database_captures(case):
    store, folder, manifest = case
    before = store.path.read_bytes()
    first = store.preview_offline_research_bundle(manifest)
    second = store.preview_offline_research_bundle(manifest)
    assert first == second
    assert len(first['local_context_sha256']) == 64
    assert store.path.read_bytes() == before
    assert first['database_modified'] is False and first['network_accessed'] is False


def test_related_version_present_before_preview_is_bound(case):
    store, folder, manifest = case
    store.add_offline_research('https://research.example/topic', 'Old', 'Earlier body')
    preview = store.preview_offline_research_bundle(manifest)
    assert preview['warning_item_count'] == 1
    assert len(store.import_offline_research_bundle(
        manifest, expected_preview_token=preview['preview_token'])['capture_ids']) == 1


def test_exact_duplicate_between_preview_and_approval_keeps_old_error(case):
    store, folder, manifest = case
    preview = store.preview_offline_research_bundle(manifest)
    store.add_offline_research('https://research.example/topic', 'Same', 'New offline body')
    with pytest.raises(ValueError, match='이미 등록'):
        store.import_offline_research_bundle(manifest, expected_preview_token=preview['preview_token'])
    assert len(store.search_offline_research()) == 1


def test_changed_local_file_still_invalidates_token(case):
    store, folder, manifest = case
    token = store.preview_offline_research_bundle(manifest)['preview_token']
    (folder / 'candidate.txt').write_text('Another locally edited text', encoding='utf-8')
    with pytest.raises(ValueError, match='다시 검토'):
        store.import_offline_research_bundle(manifest, expected_preview_token=token)
    assert not store.search_offline_research()


def test_guard_rejects_forged_token_without_database_writes(case):
    store, folder, manifest = case
    with pytest.raises(ValueError, match='다시 검토'):
        store.import_offline_research_bundle(manifest, expected_preview_token='1' * 64)
    with sqlite3.connect(store.path) as con:
        assert con.execute('SELECT COUNT(*) FROM offline_research_batches').fetchone()[0] == 0


def test_permission_required(case):
    store, folder, manifest = case
    store.logout()
    with pytest.raises(AuthenticationError):
        store.preview_offline_research_bundle(manifest)
    with pytest.raises(AuthenticationError):
        store.import_offline_research_bundle(manifest, expected_preview_token='1' * 64)


def test_socket_and_dns_blocked(case):
    store, folder, manifest = case
    def deny(*args, **kwargs):
        raise AssertionError('Remote connection prohibited')
    with patch.object(socket.socket, 'connect', deny), \
         patch.object(socket.socket, 'connect_ex', deny), \
         patch.object(socket.socket, 'sendall', deny), \
         patch.object(socket.socket, 'sendto', deny), \
         patch.object(socket, 'getaddrinfo', deny):
        token = store.preview_offline_research_bundle(manifest)['preview_token']
        store.add_offline_research('https://research.example/topic', 'Other', 'Different body')
        with pytest.raises(ValueError, match='다시 검토'):
            store.import_offline_research_bundle(manifest, expected_preview_token=token)
