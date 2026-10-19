"""Stage54: unverified self-declared HTML origin hints before owner approval."""
import json
import socket
from unittest.mock import patch

import pytest

from desktop.research_captures import inspect_offline_source_hints
from desktop.storage import AuthenticationError, LocalStore


@pytest.fixture
def owner(tmp_path):
    store = LocalStore(tmp_path / 'company.sqlite3')
    store.setup_owner('origin-preview-owner', 'offline-example-password')

    def make_manifest(html, *, claim='https://example.org/article', second=None):
        items = [{'file': 'page.html', 'url': claim, 'title': 'Offline HTML'}]
        (tmp_path / 'page.html').write_text('<p>Visible archived text</p>' + html, encoding='utf-8')
        if second:
            (tmp_path / 'second.txt').write_text('Second local source', encoding='utf-8')
            items.append({'file': 'second.txt', 'url': second, 'title': 'Second'})
        path = tmp_path / 'bundle.json'
        path.write_text(json.dumps({'format': 'aiwack-offline-research-bundle-v1',
                                    'items': items}), encoding='utf-8')
        return path
    return store, make_manifest


def test_canonical_match_and_og_url_mismatch(owner):
    store, create = owner
    path = create('<link rel="alternate canonical" href="/article#section">'
                  '<meta property="og:url" content="https://other.example/claimed">')
    before = store.path.read_bytes()
    report = store.preview_offline_research_bundle(path)
    assert report['source_hint_status_counts'] == dict(match=1, mismatch=1, invalid=0)
    assert report['source_hint_count'] == 2
    assert report['source_hints_are_unverified'] is True
    examples = report['items'][0]['source_hint_examples']
    assert [(x['kind'], x['status']) for x in examples] == [('canonical', 'match'), ('og:url', 'mismatch')]
    assert examples[0]['claimed_url'] == 'https://example.org/article'
    assert examples[1]['claimed_url'] == 'https://other.example/claimed'
    assert report['importable']
    assert store.path.read_bytes() == before
    assert store.search_offline_research() == []


def test_invalid_schemes_and_empty_claims(owner):
    store, create = owner
    report = store.preview_offline_research_bundle(create(
        '<link rel="canonical" href="javascript:alert(1)">'
        '<meta property="og:url" content="file:///secret">'
        '<link rel="canonical" href="">'))
    assert report['source_hint_status_counts'] == dict(match=0, mismatch=0, invalid=3)
    assert all(hint['claimed_url'] is None for hint in report['items'][0]['source_hint_examples'])


def test_document_base_tag_not_honored(owner):
    store, create = owner
    report = store.preview_offline_research_bundle(create(
        '<base href="https://wrong.example/">'
        '<link rel="canonical" href="/article">'))
    assert report['source_hint_status_counts']['match'] == 1


def test_meta_case_insensitive_and_relative_mismatch(owner):
    store, create = owner
    report = store.preview_offline_research_bundle(create(
        '<META PROPERTY="OG:URL" CONTENT="other">'))
    assert report['items'][0]['source_hint_examples'][0]['claimed_url'] == 'https://example.org/other'
    assert report['source_hint_status_counts']['mismatch'] == 1


def test_ignore_markup_inside_script_style_template(owner):
    store, create = owner
    report = store.preview_offline_research_bundle(create(
        '<script><link rel="canonical" href="https://fake.example"></script>'
        '<style><meta property="og:url" content="https://fake.example"></style>'
        '<template><link rel="canonical" href="https://fake.example"></template>'
        '<link rel="canonical" href="/article">'))
    assert report['source_hint_count'] == 1
    assert report['source_hint_status_counts']['match'] == 1


def test_cap_eight_source_hints_and_four_examples(owner):
    store, create = owner
    report = store.preview_offline_research_bundle(create(
        '<p>Body</p>' + '<link rel="canonical" href="/changed">' * 50))
    assert report['source_hint_count'] == 8
    assert report['source_hint_status_counts']['mismatch'] == 8
    assert len(report['items'][0]['source_hint_examples']) == 4


def test_plain_text_bundle_has_no_hints(owner):
    store, create = owner
    report = store.preview_offline_research_bundle(create(
        '<link rel="canonical" href="/article">', second='https://example.org/second'))
    assert report['items'][1]['source_hint_count'] == 0
    assert report['items'][1]['source_hint_examples'] == []


def test_hint_changes_invalidate_approval(owner, tmp_path):
    store, create = owner
    path = create('<link rel="canonical" href="/article">')
    old = store.preview_offline_research_bundle(path)
    (tmp_path / 'page.html').write_text('<p>Visible archived text</p>'
            '<link rel="canonical" href="/different">', encoding='utf-8')
    latest = store.preview_offline_research_bundle(path)
    assert latest['source_hint_status_counts']['mismatch'] == 1
    assert old['preview_token'] != latest['preview_token']
    with pytest.raises(ValueError, match='다시 검토'):
        store.import_offline_research_bundle(path, expected_preview_token=old['preview_token'])
    assert not store.search_offline_research()
    assert len(store.import_offline_research_bundle(
        path, expected_preview_token=latest['preview_token'])['capture_ids']) == 1


def test_unverified_hint_is_not_registration_blocker(owner):
    store, create = owner
    path = create('<meta property="og:url" content="https://untrusted.example/x">')
    preview = store.preview_offline_research_bundle(path)
    assert preview['importable']
    assert preview['source_hints_are_unverified']
    result = store.import_offline_research_bundle(path, expected_preview_token=preview['preview_token'])
    assert len(result['capture_ids']) == 1


def test_owner_only_and_no_socket_or_dns(owner):
    store, create = owner
    path = create('<link rel="canonical" href="https://different.example/">')
    def forbidden(*args, **kwargs):
        raise AssertionError('network calls forbidden')
    with patch.object(socket.socket, 'connect', forbidden), \
         patch.object(socket.socket, 'connect_ex', forbidden), \
         patch.object(socket.socket, 'sendall', forbidden), \
         patch.object(socket.socket, 'sendto', forbidden), \
         patch.object(socket, 'getaddrinfo', forbidden):
        assert store.preview_offline_research_bundle(path)['source_hint_count'] == 1
    store.logout()
    with pytest.raises(AuthenticationError):
        store.preview_offline_research_bundle(path)


def test_parser_does_not_follow_metadata_urls():
    assert inspect_offline_source_hints(
        '<meta property="og:url" content="//example.org/relative">',
        'https://example.org/relative')[0]['status'] == 'match'
