"""Stage54 static source-supplied indexing/license hints: never legal proof."""
import json
import socket
from unittest.mock import patch

import pytest
from desktop.research_captures import inspect_offline_usage_hints
from desktop.storage import LocalStore, AuthenticationError


def test_bounded_label_only_robots_and_license():
    html = ('<meta name="ROBOTS" content="noindex, nofollow, secret=HIDDEN">'
            '<link rel="alternate license" href="https://rights.example.net/license?token=SECRET">'
            '<link rel="license" href="/license?private=SECRET">')
    result = inspect_offline_usage_hints(html, 'https://example.org/page')
    assert result == [
        {'kind':'robots','status':'restricted','flags':['nofollow','noindex'],'target_host':None},
        {'kind':'license','status':'other_origin','flags':[],'target_host':'rights.example.net'},
        {'kind':'license','status':'same_origin','flags':[],'target_host':'example.org'},
    ]
    assert 'SECRET' not in str(result) and 'HIDDEN' not in str(result)


@pytest.mark.parametrize('value', ['javascript:alert(1)', 'file:///secret', '',
                                   'https://name:password@rights.example/x',
                                   'https://rights.example:8080/p'])
def test_license_invalid_without_exposing_url(value):
    result = inspect_offline_usage_hints('<link rel="license" href="' + value + '">',
                                         'https://example.org/page')
    assert result == [{'kind':'license','status':'invalid','flags':[],'target_host':None}]


def test_ignores_hidden_contents_and_meta_without_restriction():
    html = ('<!-- <meta name="robots" content="noindex"> -->'
            '<script>"<link rel=license href=https://evil.example>"</script>'
            '<template><meta name="robots" content="nofollow"></template>'
            '<noscript><link rel="license" href="https://evil.example"></noscript>'
            '<meta name="robots" content="index, follow">')
    assert inspect_offline_usage_hints(html,'https://example.org/') == [
        {'kind':'robots','status':'other','flags':[],'target_host':None}]


def test_hint_limit_and_invalid_long_url():
    html = '<meta name="robots" content="noarchive">'*20
    assert len(inspect_offline_usage_hints(html,'https://example.org/')) == 12
    result=inspect_offline_usage_hints('<link rel="license" href="https://example.org/'+'x'*2050+'">',
                                       'https://example.org/')
    assert result[0]['status'] == 'invalid'


def test_bundle_preview_is_readonly_network_disabled(tmp_path):
    store=LocalStore(tmp_path/'data.db')
    store.setup_owner('owner', 'local-secret')
    (tmp_path/'sample.html').write_text('<h1>Local text</h1><meta name="robots" content="noindex">'
        '<link rel="license" href="https://rights.example.net/?key=HIDDEN">',encoding='utf-8')
    (tmp_path/'simple.txt').write_text('A plain file',encoding='utf-8')
    manifest=tmp_path/'bundle.json'
    manifest.write_text(json.dumps({'format':'aiwack-offline-research-bundle-v1','items':[
        {'file':'sample.html','url':'https://example.org/page','title':'HTML'},
        {'file':'simple.txt','url':'https://example.org/plain','title':'Plain'}]}),encoding='utf-8')
    before=store.path.read_bytes()
    def deny(*args,**kw): raise AssertionError('unexpected network')
    with patch.object(socket.socket,'connect',deny), patch.object(socket.socket,'sendto',deny), \
         patch.object(socket,'getaddrinfo',deny):
        preview=store.preview_offline_research_bundle(manifest)
    assert preview['usage_hint_count'] == 2
    assert preview['usage_hint_kind_counts'] == {'robots':1,'license':1}
    assert preview['usage_hint_status_counts']['restricted'] == 1
    assert preview['usage_hint_status_counts']['other_origin'] == 1
    assert preview['usage_hints_unverified'] and not preview['usage_hint_full_urls_exposed']
    assert preview['items'][1]['usage_hint_count'] == 0
    assert 'HIDDEN' not in str(preview)
    assert preview['database_modified'] is False and preview['network_accessed'] is False
    assert store.path.read_bytes() == before
    assert store.search_offline_research() == []
    store.logout()
    with pytest.raises(AuthenticationError):
        store.preview_offline_research_bundle(manifest)


def test_approval_stale_html_rechecked(tmp_path):
    store=LocalStore(tmp_path/'data.db')
    store.setup_owner('owner', 'local-secret')
    html=tmp_path/'sample.html'
    html.write_text('<h1>Local text</h1><meta name="robots" content="noindex">',encoding='utf-8')
    manifest=tmp_path/'bundle.json'
    manifest.write_text(json.dumps({'format':'aiwack-offline-research-bundle-v1','items':[
        {'file':'sample.html','url':'https://example.org/page','title':'HTML'}]}),encoding='utf-8')
    old=store.preview_offline_research_bundle(manifest)
    html.write_text('<h1>Local text</h1><meta name="robots" content="nofollow">',encoding='utf-8')
    with pytest.raises(ValueError, match='다시 검토'):
        store.import_offline_research_bundle(manifest,expected_preview_token=old['preview_token'])
    new=store.preview_offline_research_bundle(manifest)
    assert new['usage_hint_count'] == 1
    assert store.import_offline_research_bundle(manifest,expected_preview_token=new['preview_token'])['capture_ids']
