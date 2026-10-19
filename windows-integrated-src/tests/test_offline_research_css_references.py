"""Stage54 inert HTML-inline CSS reference review: local-only, host-only."""
import json
import socket
from unittest.mock import patch

import pytest

from desktop.research_captures import inspect_offline_inline_css_references
from desktop.storage import LocalStore, AuthenticationError


def test_css_style_element_and_attribute_host_only():
    html = ('<h1>Local</h1><style>'
            '/* url(https://comment.example/a) */'
            '@import "https://fonts.example.net/style.css?token=SECRET";'
            'body { background: url("/photo.png?key=HIDDEN") }'
            '</style><section style="background:url(//static.example.net/bg.webp?x=SECRET)">text</section>')
    result = inspect_offline_inline_css_references(html, 'https://site.example.org/a')
    assert result == [
        {'kind': 'import', 'status': 'other_origin', 'target_host': 'fonts.example.net'},
        {'kind': 'url', 'status': 'same_origin', 'target_host': 'site.example.org'},
        {'kind': 'url', 'status': 'other_origin', 'target_host': 'static.example.net'},
    ]
    assert 'SECRET' not in str(result) and 'HIDDEN' not in str(result)
    assert 'comment.example' not in str(result)


@pytest.mark.parametrize('ref', [
    'data:image/png;base64,SECRET', 'file:///home/secret', 'javascript:alert(1)',
    'https://user:pass@other.example/image', 'https://other.example:8080/x',
    '', 'https://other.example/' + 'x' * 2100,
])
def test_invalid_css_urls_are_never_returned(ref):
    result = inspect_offline_inline_css_references('<div style="background:url(\'' + ref + '\')">text</div>',
                                                  'https://site.example.org/page')
    assert result == [{'kind': 'url', 'status': 'invalid', 'target_host': None}]
    assert 'pass' not in str(result) and 'SECRET' not in str(result)


def test_skip_hidden_elements_and_comments_and_bounded_results():
    html = ('<script>"<style>body{background:url(https://hidden.example)}</style>"</script>'
            '<template><div style="background:url(https://hidden.example)"></div></template>'
            '<noscript><div style="background:url(https://hidden.example)"></div></noscript>'
            '<!-- <div style="background:url(https://hidden.example)"> -->'
            '<style>/* url(https://hidden.example) */ body{background:url(/ok)}</style>')
    assert inspect_offline_inline_css_references(html, 'https://site.example.org/') == [
        {'kind':'url','status':'same_origin','target_host':'site.example.org'}]
    repeated = '<span style="background:url(/a)">ok</span>' * 45
    assert len(inspect_offline_inline_css_references(repeated, 'https://site.example.org/')) == 12


def test_long_inline_css_is_bounded_and_non_disclosing():
    html = '<style>' + 'a' * 33000 + 'url(https://hidden.example/SECRET)' + '</style>'
    assert inspect_offline_inline_css_references(html, 'https://site.example.org/') == [
        {'kind': 'oversized', 'status':'invalid', 'target_host':None}]


def test_readonly_bundle_preview_network_blocked_and_auth(tmp_path):
    db=tmp_path/'db.sqlite'; store=LocalStore(db); store.setup_owner('owner','local-secret')
    html=tmp_path/'sample.html'
    html.write_text('<h1>Example</h1><style>@import "https://assets.example.net/secret?token=PRIVATE";'
                    'p{background:url(/ok.png)}</style>',encoding='utf-8')
    (tmp_path/'plain.txt').write_text('Some local plain evidence',encoding='utf-8')
    manifest=tmp_path/'manifest.json'; manifest.write_text(json.dumps({
        'format':'aiwack-offline-research-bundle-v1', 'items':[
            {'file':'sample.html','url':'https://site.example.org/path','title':'HTML'},
            {'file':'plain.txt','url':'https://site.example.org/plain','title':'Plain'}
        ]}),encoding='utf-8')
    original=db.read_bytes()
    def refuse(*args, **kw): raise AssertionError('network forbidden')
    with patch.object(socket.socket,'connect',refuse), patch.object(socket.socket,'sendto',refuse), \
         patch.object(socket,'getaddrinfo',refuse):
        preview=store.preview_offline_research_bundle(manifest)
    assert preview['css_reference_count'] == 2
    assert preview['css_reference_status_counts'] == {'same_origin':1,'other_origin':1,'invalid':0}
    assert preview['css_reference_kind_counts'] == {'url':1,'import':1,'oversized':0}
    assert preview['css_references_inert'] is True and preview['css_full_urls_exposed'] is False
    assert preview['items'][1]['css_reference_count'] == 0
    assert 'PRIVATE' not in str(preview) and '/secret' not in str(preview['items'][0]['css_reference_examples'])
    assert db.read_bytes() == original and not store.search_offline_research()
    store.logout()
    with pytest.raises(AuthenticationError): store.preview_offline_research_bundle(manifest)


def test_css_changed_after_preview_requires_new_approval(tmp_path):
    store=LocalStore(tmp_path/'data.db'); store.setup_owner('owner','local-secret')
    html=tmp_path/'sample.html'; html.write_text('<h1>Local</h1><style>p{background:url(/a)}</style>',encoding='utf-8')
    manifest=tmp_path/'bundle.json'; manifest.write_text(json.dumps({
        'format':'aiwack-offline-research-bundle-v1', 'items':[
            {'file':'sample.html','url':'https://site.example.org/page','title':'HTML'}]}),encoding='utf-8')
    old=store.preview_offline_research_bundle(manifest)
    html.write_text('<h1>Local</h1><style>p{background:url(https://other.example/new)}</style>',encoding='utf-8')
    with pytest.raises(ValueError,match='다시 검토'):
        store.import_offline_research_bundle(manifest,expected_preview_token=old['preview_token'])
    assert store.search_offline_research() == []
    new=store.preview_offline_research_bundle(manifest)
    assert new['css_reference_status_counts']['other_origin'] == 1
    assert store.import_offline_research_bundle(manifest,expected_preview_token=new['preview_token'])['capture_ids']
