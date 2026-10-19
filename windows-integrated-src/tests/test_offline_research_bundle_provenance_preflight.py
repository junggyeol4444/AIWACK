"""Stage 54: local source/version warning *before* explicit bundle approval.

URLs are user-entered unverified claims; no DNS, requests or SQLite writes in preview.
"""
import json
import socket
from pathlib import Path
from unittest.mock import patch

import pytest

from desktop.storage import AuthenticationError, LocalStore


@pytest.fixture
def scenario(tmp_path):
    store = LocalStore(tmp_path / 'company.sqlite3')
    store.setup_owner('warning-owner', 'warning-owner-password-2026')
    manifest = tmp_path / 'bundle.json'

    def prepare(pairs):
        rows = []
        for i, (url, body) in enumerate(pairs):
            filename = f'candidate{i}.txt'
            (tmp_path / filename).write_text(body, encoding='utf-8')
            rows.append({'file': filename, 'url': url, 'title': f'Entry {i}'})
        manifest.write_text(json.dumps({'format': 'aiwack-offline-research-bundle-v1',
                                        'items': rows}), encoding='utf-8')
        return manifest

    def existing(url, body):
        source = tmp_path / 'existing.txt'
        source.write_text(body, encoding='utf-8')
        return store.import_offline_research_file(url, 'Previously captured', source)

    return store, tmp_path, prepare, existing


def test_no_warning_for_unrelated_claims(scenario):
    store, folder, prepare, existing = scenario
    existing('https://local.example/old', 'Old data')
    report = store.preview_offline_research_bundle(
        prepare([('https://local.example/new', 'Fresh data')]))
    assert report['importable'] and report['warning_item_count'] == 0
    assert report['items'][0]['warnings'] == []
    assert not any(report['warning_category_counts'].values())


def test_existing_url_with_different_content_is_warned_not_blocked(scenario):
    store, folder, prepare, existing = scenario
    old_id = existing('https://local.example/same', 'Earlier version')
    manifest = prepare([('https://local.example/same', 'Later version')])
    previous = store.path.read_bytes()
    report = store.preview_offline_research_bundle(manifest)
    assert report['importable'] and report['duplicate_count'] == 0
    assert report['warning_item_count'] == 1
    item = report['items'][0]
    assert item['warnings'] == ['existing_url_other_body']
    assert item['warning_examples']['existing_url_other_body'] == [old_id]
    assert report['warning_category_counts']['existing_url_other_body'] == 1
    assert store.path.read_bytes() == previous
    result = store.import_offline_research_bundle(manifest,
                expected_preview_token=report['preview_token'])
    assert len(result['capture_ids']) == 1
    assert len(store.search_offline_research()) == 2


def test_same_body_different_existing_claimed_url(scenario):
    store, folder, prepare, existing = scenario
    old_id = existing('https://local.example/one', 'Shared local text')
    report = store.preview_offline_research_bundle(
        prepare([('https://another.example/two', 'Shared local text')]))
    assert report['importable']
    assert report['items'][0]['warnings'] == ['existing_body_other_url']
    assert report['items'][0]['warning_examples']['existing_body_other_url'] == [old_id]
    assert report['web_source_verified'] is False


def test_archived_existing_version_still_warns(scenario):
    store, folder, prepare, existing = scenario
    old_id = existing('https://local.example/a', 'Archived original')
    store.archive_offline_research(old_id)
    report = store.preview_offline_research_bundle(
        prepare([('https://local.example/a', 'Later replacement')]))
    assert report['items'][0]['warning_examples']['existing_url_other_body'] == [old_id]


def test_batch_same_url_different_bodies_warning_is_symmetric(scenario):
    store, folder, prepare, existing = scenario
    report = store.preview_offline_research_bundle(prepare([
        ('https://local.example/a', 'Content one'),
        ('https://local.example/a', 'Content two'),
        ('https://local.example/a', 'Content three')]))
    assert report['importable'] and report['warning_item_count'] == 3
    assert report['warning_category_counts']['bundle_url_other_body'] == 3
    assert [item['warning_examples']['bundle_url_other_body'] for item in report['items']] == [
        [2, 3], [1, 3], [1, 2]]


def test_batch_same_body_different_urls_warning_is_symmetric(scenario):
    store, folder, prepare, existing = scenario
    report = store.preview_offline_research_bundle(prepare([
        ('https://local.example/a', 'Identical body'),
        ('https://local.example/b', 'Identical body')]))
    assert report['importable'] and report['warning_item_count'] == 2
    assert all(i['warnings'] == ['bundle_body_other_url'] for i in report['items'])


def test_both_warning_types_can_coexist_and_have_three_example_limit(scenario):
    store, folder, prepare, existing = scenario
    ids = [existing('https://local.example/a', f'Old version {n}') for n in range(6)]
    report = store.preview_offline_research_bundle(prepare([
        ('https://local.example/a', 'Unique version'),
        ('https://local.example/b', 'Unique version')]))
    first = report['items'][0]
    assert first['warnings'] == ['existing_url_other_body', 'bundle_body_other_url']
    assert first['warning_examples']['existing_url_other_body'] == ids[-1:-4:-1]
    assert first['warning_examples']['bundle_body_other_url'] == [2]


def test_exact_duplicates_remain_hard_block_without_false_warning(scenario):
    store, folder, prepare, existing = scenario
    old_id = existing('https://local.example/a', 'Same byte content')
    report = store.preview_offline_research_bundle(
        prepare([('https://local.example/a', 'Same byte content')]))
    assert not report['importable'] and report['duplicate_count'] == 1
    assert report['items'][0]['existing_capture_id'] == old_id
    assert report['items'][0]['warnings'] == []


def test_preview_does_not_change_database_or_manifest(scenario):
    store, folder, prepare, existing = scenario
    existing('https://local.example/a', 'Initial text')
    manifest = prepare([('https://local.example/a', 'Updated text')])
    before_db = store.path.read_bytes()
    before_manifest = manifest.read_bytes()
    first = store.preview_offline_research_bundle(manifest)
    second = store.preview_offline_research_bundle(manifest)
    assert first == second
    assert store.path.read_bytes() == before_db
    assert manifest.read_bytes() == before_manifest
    assert first['database_modified'] is False and first['network_accessed'] is False


def test_logout_cannot_preview(scenario):
    store, folder, prepare, existing = scenario
    manifest = prepare([('https://local.example/a', 'data')])
    store.logout()
    with pytest.raises(AuthenticationError):
        store.preview_offline_research_bundle(manifest)


def test_offline_network_socket_dns_blocked(scenario):
    store, folder, prepare, existing = scenario
    old_id = existing('https://local.example/a', 'Original')
    manifest = prepare([('https://local.example/a', 'Updated')])

    def deny(*args, **kwargs):
        raise AssertionError('No network allowed')

    with patch.object(socket.socket, 'connect', deny), patch.object(socket.socket, 'connect_ex', deny), \
         patch.object(socket.socket, 'sendto', deny), patch.object(socket.socket, 'sendall', deny), \
         patch.object(socket, 'getaddrinfo', deny):
        result = store.preview_offline_research_bundle(manifest)
    assert result['items'][0]['warning_examples']['existing_url_other_body'] == [old_id]


def test_bad_manifest_still_rejected(scenario):
    store, folder, prepare, existing = scenario
    manifest = prepare([('https://local.example/a', 'Updated')])
    manifest.write_text('{invalid', encoding='utf-8')
    with pytest.raises(ValueError):
        store.preview_offline_research_bundle(manifest)
