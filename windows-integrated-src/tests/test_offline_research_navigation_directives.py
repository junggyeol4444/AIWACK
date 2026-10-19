"""Stage54 read-only HTML navigation directive warnings (not a browser)."""
import json
import socket
from unittest.mock import patch

import pytest

from desktop.research_captures import (inspect_offline_navigation_directives,
                                       extract_offline_links)
from desktop.storage import LocalStore, AuthenticationError


@pytest.fixture
def workspace(tmp_path):
    store = LocalStore(tmp_path / 'company.sqlite3')
    store.setup_owner('navigation-owner', 'offline-owner-password')

    def manifest(html, *, other_text=False):
        (tmp_path / 'page.html').write_text('<h1>Visible archived evidence</h1>' + html, encoding='utf-8')
        items = [{'file': 'page.html', 'url': 'https://example.org/article', 'title': 'Evidence'}]
        if other_text:
            (tmp_path / 'notes.txt').write_text('Plain text source', encoding='utf-8')
            items.append({'file': 'notes.txt', 'url': 'https://other.example/notes', 'title': 'Notes'})
        path = tmp_path / 'manifest.json'
        path.write_text(json.dumps({'format': 'aiwack-offline-research-bundle-v1',
                                   'items': items}), encoding='utf-8')
        return path
    return store, manifest


def test_base_and_refresh_both_other_origin(workspace):
    store, manifest = workspace
    path = manifest('<base href="https://other.example/assets/">'
                    '<meta http-equiv="refresh" content="0; URL=https://else.example/login">')
    before = store.path.read_bytes()
    preview = store.preview_offline_research_bundle(path)
    assert preview['navigation_directive_count'] == 2
    assert preview['navigation_directive_status_counts'] == {
        'same_origin': 0, 'other_origin': 2, 'invalid': 0}
    assert [v['kind'] for v in preview['items'][0]['navigation_directive_examples']] == ['base', 'refresh']
    assert preview['navigation_directives_inert'] is True
    assert preview['web_source_verified'] is False
    assert store.path.read_bytes() == before
    assert not store.search_offline_research()


def test_relative_base_and_refresh_same_origin(workspace):
    store, manifest = workspace
    preview = store.preview_offline_research_bundle(manifest(
        '<base href="/assets/">'
        "<meta HTTP-EQUIV='REFRESH' CONTENT=' 3.5 ;  url = \"../landing\" ' >"))
    assert preview['navigation_directive_status_counts']['same_origin'] == 2
    assert preview['items'][0]['navigation_directive_examples'][1]['target_url'] == 'https://example.org/landing'


@pytest.mark.parametrize('bad', ['javascript:alert(1)', 'file:///etc/passwd',
                                     'data:text/html,test', 'http://localhost/private',
                                     'https://example.org:8443/evil', ''])
def test_invalid_navigation_scheme_or_host(workspace, bad):
    store, manifest = workspace
    preview = store.preview_offline_research_bundle(manifest(
        f'<meta http-equiv="refresh" content="0; url={bad}">'))
    assert preview['navigation_directive_status_counts']['invalid'] == 1
    assert preview['items'][0]['navigation_directive_examples'][0]['target_url'] is None


def test_malformed_refresh_reported_but_plain_reload_ignored(workspace):
    store, manifest = workspace
    preview = store.preview_offline_research_bundle(manifest(
        '<meta http-equiv="refresh" content="7">'
        '<meta http-equiv="refresh" content="xx;url=/malformed">'))
    assert preview['navigation_directive_count'] == 1
    assert preview['navigation_directive_status_counts']['invalid'] == 1


def test_ignore_script_style_and_template(workspace):
    store, manifest = workspace
    preview = store.preview_offline_research_bundle(manifest(
        '<script><base href="https://fake.example/"></script>'
        '<style><meta http-equiv="refresh" content="0;url=https://fake.example/"></style>'
        '<template><base href="https://fake.example/"></template>'
        '<base href="/safe/">'))
    assert preview['navigation_directive_count'] == 1
    assert preview['navigation_directive_status_counts']['same_origin'] == 1


def test_cap_eight_and_four_examples(workspace):
    store, manifest = workspace
    preview = store.preview_offline_research_bundle(manifest('<base href="/other/">' * 40))
    assert preview['navigation_directive_count'] == 8
    assert len(preview['items'][0]['navigation_directive_examples']) == 4


def test_plain_text_has_no_navigation_directives(workspace):
    store, manifest = workspace
    preview = store.preview_offline_research_bundle(manifest('<base href="/x">', other_text=True))
    assert preview['items'][1]['navigation_directive_count'] == 0
    assert preview['items'][1]['navigation_directive_examples'] == []


def test_base_tag_remains_ignored_in_offline_link_resolution(workspace):
    _, _ = workspace
    links = extract_offline_links('<base href="https://other.example/">'
                                  '<a href="next">link</a>', 'https://example.org/article')
    assert links == ['https://example.org/next']


def test_preview_approval_bound_to_html_bytes(workspace, tmp_path):
    store, manifest = workspace
    path = manifest('<base href="/first/">')
    original = store.preview_offline_research_bundle(path)
    (tmp_path / 'page.html').write_text('<h1>Visible archived evidence</h1>'
                                       '<base href="https://else.example/">', encoding='utf-8')
    updated = store.preview_offline_research_bundle(path)
    assert original['preview_token'] != updated['preview_token']
    with pytest.raises(ValueError, match='다시 검토'):
        store.import_offline_research_bundle(path, expected_preview_token=original['preview_token'])
    assert not store.search_offline_research()
    assert len(store.import_offline_research_bundle(
        path, expected_preview_token=updated['preview_token'])['capture_ids']) == 1


def test_unverified_navigation_does_not_block_explicit_approval(workspace):
    store, manifest = workspace
    path = manifest('<meta http-equiv="refresh" content="0;url=https://other.example/">')
    preview = store.preview_offline_research_bundle(path)
    assert preview['importable']
    result = store.import_offline_research_bundle(path, expected_preview_token=preview['preview_token'])
    assert len(result['capture_ids']) == 1


def test_offline_and_owner_only(workspace):
    store, manifest = workspace
    path = manifest('<base href="https://different.example/">')
    def forbidden(*args, **kwargs):
        raise AssertionError('network forbidden')
    with patch.object(socket.socket, 'connect', forbidden), \
         patch.object(socket.socket, 'connect_ex', forbidden), \
         patch.object(socket.socket, 'sendall', forbidden), \
         patch.object(socket.socket, 'sendto', forbidden), \
         patch.object(socket, 'getaddrinfo', forbidden):
        assert store.preview_offline_research_bundle(path)['navigation_directive_count'] == 1
    store.logout()
    with pytest.raises(AuthenticationError):
        store.preview_offline_research_bundle(path)


def test_no_html_directives_empty():
    assert inspect_offline_navigation_directives('<p>No navigation</p>',
                                                  'https://example.org/page') == []
