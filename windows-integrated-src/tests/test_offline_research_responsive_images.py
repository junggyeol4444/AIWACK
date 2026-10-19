"""Stage54 offline static srcset candidate inspection and owner approval."""
import json
import socket
from unittest.mock import patch

import pytest

from desktop.research_captures import inspect_offline_responsive_images
from desktop.storage import LocalStore, AuthenticationError


def test_img_and_picture_candidates_host_only():
    html = ('<h1>Local</h1><img srcset="/small.jpg?key=SECRET 1x, '
            'https://cdn.example.net/large.jpg?token=SECRET 2x">'
            '<picture><source srcset="//cdn.example.net/hero.webp 800w"></picture>')
    out = inspect_offline_responsive_images(html, 'https://example.org/page')
    assert [(x['element'], x['status'], x['target_host'], x['descriptor']) for x in out] == [
        ('img', 'same_origin', 'example.org', '1x'),
        ('img', 'other_origin', 'cdn.example.net', '2x'),
        ('source', 'other_origin', 'cdn.example.net', '800w'),
    ]
    assert 'SECRET' not in str(out)
    assert all(set(x) == {'element','status','target_host','descriptor'} for x in out)


@pytest.mark.parametrize('srcset', [
    'javascript:alert(1) 1x', 'file:///private/image.png 2x',
    'data:image/png;base64,SECRET 1x', 'https://user:SECRET@cdn.example.net/asset.png 1x',
    'https://example.org:8080/private 1x', '/one 0w', '/two bad',
    '/foo 2x unexpected', '', '  ', '/file 0x', 'https://cdn.example.net/' + 'x'*2050 + ' 1x',
])
def test_srcset_invalid_but_does_not_expose_data(srcset):
    out = inspect_offline_responsive_images('<img srcset="' + srcset + '">', 'https://example.org/page')
    assert out and all(x['status'] == 'invalid' for x in out)
    assert all(x['target_host'] is None for x in out)
    assert 'SECRET' not in str(out)


def test_ignores_nonmatching_hidden_and_base_override():
    html = ('<!-- <img srcset="https://comment.example/1 1x"> -->'
            '<script>"<img srcset=https://script.example/x>"</script>'
            '<template><source srcset="https://template.example/x 2x"></template>'
            '<noscript><img srcset="https://noscript.example/x 1x"></noscript>'
            '<base href="https://fake.example">'
            '<img srcset="/ok 1x"><img src="https://ignored.example/img.png">')
    assert inspect_offline_responsive_images(html, 'https://example.org/page') == [
        {'element':'img','status':'same_origin','target_host':'example.org','descriptor':'1x'}]


def test_bounded_candidates_and_attribute():
    many = '<img srcset="' + ', '.join('/x%d 1x' % n for n in range(45)) + '">'
    out = inspect_offline_responsive_images(many, 'https://example.org/page')
    assert len(out) == 12
    assert all(x['status'] == 'same_origin' for x in out)
    too_big = '<img srcset="' + '/foo'*1100 + '">'
    assert inspect_offline_responsive_images(too_big, 'https://example.org/') == [
        {'element':'img','status':'invalid','target_host':None,'descriptor':None}]


def test_manifest_preview_offline_no_db_write_or_network(tmp_path):
    store = LocalStore(tmp_path/'owner.db')
    store.setup_owner('owner','local-secret')
    (tmp_path/'source.html').write_text('<h1>Evidence</h1><img srcset="/a 1x, '
        'https://cdn.example.net/b?secret=HIDDEN 2x"><source srcset="file:///hidden.png 1x">',
        encoding='utf-8')
    (tmp_path/'plain.txt').write_text('Simple text', encoding='utf-8')
    manifest = tmp_path/'manifest.json'
    manifest.write_text(json.dumps({'format':'aiwack-offline-research-bundle-v1',
        'items':[{'file':'source.html','url':'https://example.org/page','title':'Report'},
                 {'file':'plain.txt','url':'https://example.org/plain','title':'Plain'}]}),encoding='utf-8')
    prior=store.path.read_bytes()
    def deny(*a,**kw):
        raise AssertionError('No network or DNS permitted')
    with patch.object(socket.socket,'connect',deny),patch.object(socket.socket,'connect_ex',deny), \
         patch.object(socket.socket,'sendto',deny),patch.object(socket,'getaddrinfo',deny):
        result=store.preview_offline_research_bundle(manifest)
    assert result['responsive_image_count'] == 3
    assert result['responsive_image_element_counts'] == {'img':2, 'source':1}
    assert result['responsive_image_status_counts'] == {'same_origin':1,'other_origin':1,'invalid':1}
    assert result['responsive_images_inert'] is True
    assert result['responsive_image_full_urls_exposed'] is False
    assert result['database_modified'] is False and result['network_accessed'] is False
    assert result['items'][1]['responsive_image_count'] == 0
    assert 'HIDDEN' not in str(result)
    assert store.path.read_bytes() == prior
    assert store.search_offline_research() == []
    store.logout()
    with pytest.raises(AuthenticationError):
        store.preview_offline_research_bundle(manifest)


def test_stale_manifest_file_after_approval_requires_recheck(tmp_path):
    store = LocalStore(tmp_path/'owner.db')
    store.setup_owner('owner','local-secret')
    file=tmp_path/'source.html'
    file.write_text('<h1>Evidence</h1><img srcset="/ok.png 1x">', encoding='utf-8')
    manifest=tmp_path/'manifest.json'
    manifest.write_text(json.dumps({'format':'aiwack-offline-research-bundle-v1',
         'items':[{'file':'source.html','url':'https://example.org/page','title':'Report'}]}),encoding='utf-8')
    old=store.preview_offline_research_bundle(manifest)
    file.write_text('<h1>Evidence</h1><img srcset="https://other.example/new.jpg 2x">',encoding='utf-8')
    with pytest.raises(ValueError, match='다시 검토'):
        store.import_offline_research_bundle(manifest,expected_preview_token=old['preview_token'])
    assert store.search_offline_research() == []
    new=store.preview_offline_research_bundle(manifest)
    assert new['responsive_image_status_counts']['other_origin'] == 1
    result=store.import_offline_research_bundle(manifest,expected_preview_token=new['preview_token'])
    assert len(result['capture_ids']) == 1
