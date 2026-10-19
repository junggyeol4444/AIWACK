"""Stage54: URL-string warnings appear *before* a local batch is approved."""
import json
import socket
import sqlite3
from unittest.mock import patch

import pytest

from desktop.storage import AuthenticationError, LocalStore


@pytest.fixture
def case(tmp_path):
    store = LocalStore(tmp_path / 'company.sqlite3')
    store.setup_owner('preflight-batch-owner', 'preflight-batch-password-2026')
    return store, tmp_path


def manifest(folder, urls):
    entries = []
    for number, url in enumerate(urls):
        filename = f'local-{number}.txt'
        (folder / filename).write_text(f'Offline content #{number}', encoding='utf-8')
        entries.append({'file': filename, 'url': url, 'title': f'Research #{number}'})
    path = folder / 'manifest.json'
    path.write_text(json.dumps({'format': 'aiwack-offline-research-bundle-v1',
                                'items': entries}), encoding='utf-8')
    return path


@pytest.mark.parametrize(('url', 'expected'), [
    ('https://127.0.0.1/secret', ('ip_literal', 'non_global_ip_literal')),
    ('http://169.254.169.254/latest', ('ip_literal', 'non_global_ip_literal')),
    ('https://10.0.0.1/private', ('ip_literal', 'non_global_ip_literal')),
    ('https://8.8.8.8/page', ('ip_literal',)),
    ('https://0x7f000001/page', ('ambiguous_numeric_hostname',)),
    ('https://0177.0.0.1/page', ('ambiguous_numeric_hostname',)),
    ('https://internal.local/document', ('local_name',)),
    ('https://intranet/document', ('single_label_hostname',)),
    ('https://xn--bcher-kva.example/page', ('internationalized_hostname',)),
    ('https://example.org./page', ('trailing_dot_hostname',)),
    ('https://example.org/page', ()),
])
def test_preapproval_url_codes(case, url, expected):
    store, folder = case
    path = manifest(folder, [url])
    before = store.path.read_bytes()
    report = store.preview_offline_research_bundle(path)
    assert tuple(report['items'][0]['url_warning_codes']) == expected
    assert report['url_warning_item_count'] == bool(expected)
    assert sum(report['url_warning_category_counts'].values()) == len(expected)
    assert report['url_preflight_is_string_only']
    assert not report['dns_checked'] and not report['safe_to_fetch_verified']
    assert not report['network_accessed'] and not report['database_modified']
    assert store.path.read_bytes() == before
    assert report['importable']


def test_combined_counts_and_existing_provenance_warnings_remain_independent(case):
    store, folder = case
    store.add_offline_research('https://10.1.2.3/a', 'Old', 'Earlier offline content')
    path = manifest(folder, ['https://10.1.2.3/a', 'https://example.org/ok',
                             'https://somewhere.local/review'])
    report = store.preview_offline_research_bundle(path)
    assert report['warning_item_count'] == 1  # source version mismatch
    assert report['warning_category_counts']['existing_url_other_body'] == 1
    assert report['url_warning_item_count'] == 2
    assert report['url_warning_category_counts'] == {
        'ip_literal': 1, 'local_name': 1, 'non_global_ip_literal': 1}
    assert report['items'][1]['url_warning_codes'] == []
    assert len(store.import_offline_research_bundle(
        path, expected_preview_token=report['preview_token'])['capture_ids']) == 3


def test_exact_duplicate_blocks_even_if_url_warning_present(case):
    store, folder = case
    path = manifest(folder, ['https://10.1.2.3/item'])
    store.add_offline_research('https://10.1.2.3/item', 'Old', 'Offline content #0')
    report = store.preview_offline_research_bundle(path)
    assert report['url_warning_item_count'] == 1
    assert report['duplicate_count'] == 1 and not report['importable']
    with pytest.raises(ValueError, match='이미 등록'):
        store.import_offline_research_bundle(path, expected_preview_token=report['preview_token'])


def test_url_change_invalidates_preview_token(case):
    store, folder = case
    path = manifest(folder, ['https://example.org/ok'])
    first = store.preview_offline_research_bundle(path)
    obj = json.loads(path.read_text(encoding='utf-8'))
    obj['items'][0]['url'] = 'https://10.0.0.1/ok'
    path.write_text(json.dumps(obj), encoding='utf-8')
    second = store.preview_offline_research_bundle(path)
    assert first['preview_token'] != second['preview_token']
    assert second['url_warning_item_count'] == 1
    with pytest.raises(ValueError, match='다시 검토'):
        store.import_offline_research_bundle(path, expected_preview_token=first['preview_token'])
    assert not store.search_offline_research()


def test_excluded_credential_and_port_urls_remain_blocked(case):
    store, folder = case
    for url in ('https://u:password@example.org/private', 'https://example.org:9000/'):
        path = manifest(folder, [url])
        with pytest.raises(ValueError):
            store.preview_offline_research_bundle(path)
    assert not store.search_offline_research()


def test_owner_only_and_no_network_calls(case):
    store, folder = case
    path = manifest(folder, ['http://169.254.169.254/internal'])
    def forbidden(*args, **kwargs):
        raise AssertionError('No network or DNS calls allowed')
    with patch.object(socket.socket, 'connect', forbidden), \
         patch.object(socket.socket, 'connect_ex', forbidden), \
         patch.object(socket.socket, 'sendall', forbidden), \
         patch.object(socket.socket, 'sendto', forbidden), \
         patch.object(socket, 'getaddrinfo', forbidden):
        preview = store.preview_offline_research_bundle(path)
        assert preview['url_warning_item_count'] == 1
        with sqlite3.connect(store.path) as con:
            assert con.execute('SELECT COUNT(*) FROM offline_research_batches').fetchone()[0] == 0
    store.logout()
    with pytest.raises(AuthenticationError):
        store.preview_offline_research_bundle(path)
