"""Stage54: passive HTML resource host inspection, strictly offline."""
import json
import socket
from unittest.mock import patch

import pytest

from desktop.research_captures import inspect_offline_passive_resources
from desktop.storage import AuthenticationError, LocalStore


def test_inert_resource_categories_and_host_only():
    html = ('<h1>Offline data</h1>'
            '<img src="/image.png?session=SECRET-PARAM">'
            '<link rel="alternate stylesheet" href="https://cdn.example.net/style.css?key=SECRET-STYLE">'
            '<video poster="//media.example.net/poster.jpg"></video>'
            '<audio src="https://media.example.net/file.ogg"></audio>'
            '<source src="relative.webm">'
            '<track src="https://media.example.net/captions.vtt">')
    output = inspect_offline_passive_resources(html, 'https://example.org/a/page')
    assert [x['kind'] for x in output] == [
        'image', 'stylesheet', 'media', 'media', 'media', 'media']
    assert [x['status'] for x in output] == [
        'same_origin', 'other_origin', 'other_origin',
        'other_origin', 'same_origin', 'other_origin']
    assert [x['target_host'] for x in output] == [
        'example.org', 'cdn.example.net', 'media.example.net',
        'media.example.net', 'example.org', 'media.example.net']
    assert 'SECRET' not in str(output)
    assert all(set(item) == {'kind', 'status', 'target_host'} for item in output)


@pytest.mark.parametrize('element', [
    '<img src="javascript:alert(1)">',
    '<img src="file:///etc/passwd">',
    '<audio src="data:audio/mp3;base64,ABC">',
    '<link rel="stylesheet" href="https://user:SECRET@cdn.example.net/x.css">',
    '<img src="http://example.com:8888/x">',
    '<img src="">',
    '<img src="https://example.org/' + 'x'*2050 + '">',
])
def test_invalid_or_unsafe_url_strings_are_only_flagged(element):
    result = inspect_offline_passive_resources(element, 'https://example.org/page')
    assert len(result) == 1
    assert result[0]['status'] == 'invalid'
    assert result[0]['target_host'] is None
    assert 'SECRET' not in str(result)


def test_non_matching_markup_and_hidden_template_are_ignored():
    html = ('<!-- <img src="https://fake.example/a"> -->'
            '<script>"<img src=https://evil.example/a>"</script>'
            '<template><img src="https://hidden.example/x"></template>'
            '<style>.x{background:url(https://hidden.example/y)}</style>'
            '<noscript><img src="https://hidden.example/img"></noscript>'
            '<link rel="canonical" href="https://example.org/">'
            '<a href="https://link.example/">Link</a><img srcset="https://srcset.example/a 1x">')
    assert inspect_offline_passive_resources(html, 'https://example.org/') == []


def test_limit_and_no_base_override():
    html = ('<base href="https://spoof.example/">'
            + '<img src="/x">' * 30)
    result = inspect_offline_passive_resources(html, 'https://example.org/story')
    assert len(result) == 12
    assert all(x == {'kind': 'image', 'status': 'same_origin', 'target_host': 'example.org'}
               for x in result)


@pytest.fixture
def bundle(tmp_path):
    store = LocalStore(tmp_path / 'store.db')
    store.setup_owner('owner','local-only-password')
    def manifest(html, *, plain=False):
        (tmp_path / 'evidence.html').write_text('<h1>Observed offline</h1>' + html, encoding='utf-8')
        items=[{'file': 'evidence.html', 'url': 'https://example.org/report', 'title':'Source asserted'}]
        if plain:
            (tmp_path / 'sample.txt').write_text('<img src="https://foreign.example/nope">',encoding='utf-8')
            items.append({'file':'sample.txt','url':'https://example.org/sample','title':'Plain text'})
        path=tmp_path/'manifest.json'
        path.write_text(json.dumps({'format': 'aiwack-offline-research-bundle-v1',
                                    'items': items}), encoding='utf-8')
        return path
    return store, manifest


def test_preview_counts_security_properties_and_no_db_change(bundle):
    store, manifest = bundle
    path = manifest('<img src="https://tracker.example/p.gif?token=PRIVATE">'
                    '<img src="/internal.png"><link rel="stylesheet" href="data:unsafe">', plain=True)
    before=store.path.read_bytes()
    def block(*args, **kwargs):
        raise AssertionError('network access forbidden')
    with patch.object(socket.socket, 'connect', block), \
         patch.object(socket.socket, 'connect_ex', block), \
         patch.object(socket.socket, 'sendto', block), \
         patch.object(socket, 'getaddrinfo', block):
        preview=store.preview_offline_research_bundle(path)
    assert preview['passive_resource_count'] == 3
    assert preview['passive_resource_kind_counts'] == {'image': 2, 'stylesheet': 1, 'media': 0}
    assert preview['passive_resource_status_counts'] == {'same_origin': 1, 'other_origin': 1, 'invalid': 1}
    assert preview['passive_resources_inert'] is True
    assert preview['passive_resource_full_urls_exposed'] is False
    assert preview['network_accessed'] is False
    assert preview['database_modified'] is False
    assert preview['items'][1]['passive_resource_count'] == 0
    assert 'PRIVATE' not in str(preview)
    assert store.path.read_bytes() == before
    assert store.search_offline_research() == []


def test_file_change_rejects_stale_approval(bundle, tmp_path):
    store, manifest = bundle
    path=manifest('<img src="/asset.png">')
    first=store.preview_offline_research_bundle(path)
    (tmp_path/'evidence.html').write_text('<h1>Observed offline</h1><img src="https://other.example/asset.png">',
                                          encoding='utf-8')
    with pytest.raises(ValueError, match='다시 검토'):
        store.import_offline_research_bundle(path, expected_preview_token=first['preview_token'])
    assert store.search_offline_research() == []
    updated=store.preview_offline_research_bundle(path)
    assert updated['passive_resource_status_counts']['other_origin'] == 1
    result=store.import_offline_research_bundle(path, expected_preview_token=updated['preview_token'])
    assert len(result['capture_ids']) == 1


def test_logout_denies_preview(bundle):
    store, manifest = bundle
    path=manifest('<img src="https://example.net/test">')
    store.logout()
    with pytest.raises(AuthenticationError):
        store.preview_offline_research_bundle(path)
