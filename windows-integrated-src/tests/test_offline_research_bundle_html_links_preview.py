"""Stage54 local HTML link candidates visible before owner approves a bundle."""
import json
import socket
from unittest.mock import patch

import pytest

from desktop.storage import AuthenticationError, LocalStore


@pytest.fixture
def setup(tmp_path):
    store = LocalStore(tmp_path / 'company.sqlite3')
    store.setup_owner('html-link-preview', 'offline-test-owner-password')

    def manifest(files):
        entries = []
        for index, (name, url, content) in enumerate(files):
            (tmp_path / name).write_text(content, encoding='utf-8')
            entries.append({'file': name, 'url': url, 'title': f'Offline #{index}'})
        path = tmp_path / 'manifest.json'
        path.write_text(json.dumps({'format': 'aiwack-offline-research-bundle-v1',
                                    'items': entries}), encoding='utf-8')
        return path
    return store, tmp_path, manifest


def test_in_bundle_and_unregistered_links_before_import(setup):
    store, folder, manifest = setup
    path = manifest([
        ('one.html', 'https://example.org/root/index.html',
         '<p>HTML text</p><a href="../second">in bundle</a>'
         '<a href="https://elsewhere.example/missing">missing</a>'
         '<a href="javascript:alert(1)">ignored</a>'),
        ('two.txt', 'https://example.org/second', 'second document')])
    before = store.path.read_bytes()
    result = store.preview_offline_research_bundle(path)
    assert result['html_link_count'] == 2
    assert result['html_link_status_counts'] == {
        'in_bundle': 1, 'registered_active': 0, 'registered_archived': 0, 'unregistered': 1}
    assert result['items'][0]['html_link_count'] == 2
    assert result['items'][1]['html_link_count'] == 0
    assert [x['status'] for x in result['items'][0]['html_link_examples']] == [
        'in_bundle', 'unregistered']
    assert result['items'][0]['html_link_examples'][0]['candidate_ids_or_ordinals'] == [2]
    assert result['importable'] and result['html_links_are_unverified']
    assert store.path.read_bytes() == before
    assert store.search_offline_research() == []


def test_active_and_archived_local_candidates(setup):
    store, folder, manifest = setup
    active = store.add_offline_research('https://ref.example/active', 'Active', 'Existing A')
    archived = store.add_offline_research('https://ref.example/archived', 'Archived', 'Existing B')
    store.archive_offline_research(archived)
    path = manifest([('one.html', 'https://example.org/html', '<p>text</p>'
                     '<a href="https://ref.example/active">A</a>'
                     '<a href="https://ref.example/archived">B</a>')])
    report = store.preview_offline_research_bundle(path)
    assert report['html_link_status_counts'] == dict(
        in_bundle=0, registered_active=1, registered_archived=1, unregistered=0)
    assert [x['candidate_ids_or_ordinals'] for x in report['items'][0]['html_link_examples']] == [
        [active], [archived]]
    assert report['warning_item_count'] == 0 and report['duplicate_count'] == 0


def test_html_link_registration_between_preview_and_approval_requires_new_approval(setup):
    store, folder, manifest = setup
    path = manifest([('one.html', 'https://example.org/html',
                      '<p>Body</p><a href="https://target.example/next">next</a>')])
    preview = store.preview_offline_research_bundle(path)
    assert preview['html_link_status_counts']['unregistered'] == 1
    store.add_offline_research('https://target.example/next', 'Later', 'Independent source')
    refreshed = store.preview_offline_research_bundle(path)
    assert refreshed['html_link_status_counts']['registered_active'] == 1
    assert preview['preview_token'] != refreshed['preview_token']
    with pytest.raises(ValueError, match='다시 검토'):
        store.import_offline_research_bundle(path, expected_preview_token=preview['preview_token'])
    assert len(store.search_offline_research()) == 1
    assert len(store.import_offline_research_bundle(
        path, expected_preview_token=refreshed['preview_token'])['capture_ids']) == 1


def test_archiving_link_target_requires_new_approval(setup):
    store, folder, manifest = setup
    ident = store.add_offline_research('https://target.example/next', 'Target', 'Other')
    path = manifest([('one.html', 'https://example.org/html',
                      '<p>Body</p><a href="https://target.example/next">next</a>')])
    old = store.preview_offline_research_bundle(path)
    store.archive_offline_research(ident)
    new = store.preview_offline_research_bundle(path)
    assert new['html_link_status_counts']['registered_archived'] == 1
    assert old['preview_token'] != new['preview_token']
    with pytest.raises(ValueError, match='다시 검토'):
        store.import_offline_research_bundle(path, expected_preview_token=old['preview_token'])


def test_unrelated_local_capture_does_not_cancel_approval(setup):
    store, folder, manifest = setup
    path = manifest([('one.html', 'https://example.org/html',
                      '<p>Body</p><a href="https://target.example/next">next</a>')])
    preview = store.preview_offline_research_bundle(path)
    store.add_offline_research('https://other.example/unrelated', 'Unrelated', 'No overlap')
    assert preview['preview_token'] == store.preview_offline_research_bundle(path)['preview_token']
    assert len(store.import_offline_research_bundle(
        path, expected_preview_token=preview['preview_token'])['capture_ids']) == 1


def test_max_100_links_and_only_five_examples(setup):
    store, folder, manifest = setup
    html = '<p>test</p>' + ''.join(f'<a href="/v/{n}">x</a>' for n in range(150))
    path = manifest([('links.html', 'https://example.org/start', html)])
    report = store.preview_offline_research_bundle(path)
    assert report['html_link_count'] == 100
    assert report['html_link_status_counts']['unregistered'] == 100
    assert len(report['items'][0]['html_link_examples']) == 5
    assert report['items'][0]['html_link_count'] == 100


def test_links_in_hidden_html_are_not_summarized(setup):
    store, folder, manifest = setup
    path = manifest([('one.html', 'https://example.org/start',
                      '<p>Visible</p><script><a href="/evil"></script>'
                      '<style><a href="/other"></style>'
                      '<a href="/visible">Real</a>')])
    report = store.preview_offline_research_bundle(path)
    assert report['html_link_count'] == 1
    assert report['items'][0]['html_link_examples'][0]['linked_url'] == 'https://example.org/visible'


def test_no_external_calls_and_owner_only(setup):
    store, folder, manifest = setup
    path = manifest([('one.html', 'https://example.org/start',
                      '<p>Visible</p><a href="https://other.example/link">ref</a>')])
    def deny(*args, **kwargs):
        raise AssertionError('No network access')
    with patch.object(socket.socket, 'connect', deny), \
         patch.object(socket.socket, 'connect_ex', deny), \
         patch.object(socket.socket, 'sendto', deny), \
         patch.object(socket.socket, 'sendall', deny), \
         patch.object(socket, 'getaddrinfo', deny):
        assert store.preview_offline_research_bundle(path)['html_link_count'] == 1
    store.logout()
    with pytest.raises(AuthenticationError):
        store.preview_offline_research_bundle(path)


def test_many_link_targets_bind_context_in_chunks(setup):
    store, folder, manifest = setup
    files = []
    for n in range(12):
        html = '<p>source content</p>' + ''.join(
            f'<a href="https://refs.example/{n}/{i}">ref</a>' for i in range(100))
        files.append((f'input{n}.html', f'https://source.example/{n}', html))
    path = manifest(files)
    preview = store.preview_offline_research_bundle(path)
    assert preview['html_link_count'] == 1200
    assert preview['html_link_status_counts']['unregistered'] == 1200
    assert len(preview['items'][0]['html_link_examples']) == 5
    assert preview['importable']
