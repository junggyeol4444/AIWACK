"""Stage54 offline HTML active URL claims: string-only, not a browser."""
import json
import socket
from unittest.mock import patch

import pytest

from desktop.research_captures import inspect_offline_active_targets
from desktop.storage import LocalStore, AuthenticationError


@pytest.fixture
def workspace(tmp_path):
    store = LocalStore(tmp_path / 'company.sqlite3')
    store.setup_owner('active-owner', 'local-only-password')

    def make(html, *, plain=False):
        (tmp_path / 'evidence.html').write_text('<h1>Offline source</h1>'+html, encoding='utf-8')
        items = [{'file': 'evidence.html', 'url': 'https://example.org/report', 'title': 'Report'}]
        if plain:
            (tmp_path/'note.txt').write_text('<form action="https://wrong.org">', encoding='utf-8')
            items.append({'file':'note.txt','url':'https://example.org/note','title':'Plain'})
        manifest = tmp_path/'manifest.json'
        manifest.write_text(json.dumps({'format':'aiwack-offline-research-bundle-v1', 'items':items}),encoding='utf-8')
        return manifest
    return store, make


def test_form_and_frame_and_script_status_and_method(workspace):
    store, make = workspace
    before = store.path.read_bytes()
    preview = store.preview_offline_research_bundle(make(
        '<form method="post" action="https://other.org/receive"></form>'
        '<iframe src="/embed"></iframe>'
        '<script src="//cdn.example.org/app.js"></script>'))
    assert preview['active_target_count'] == 3
    assert preview['active_target_status_counts'] == {'same_origin':1,'other_origin':2,'invalid':0}
    assert preview['active_target_kind_counts'] == {'form':1,'iframe':1,'script':1}
    examples = preview['items'][0]['active_target_examples']
    assert [x['kind'] for x in examples] == ['form','iframe','script']
    assert examples[0]['method'] == 'POST'
    assert examples[1]['target_url'] == 'https://example.org/embed'
    assert preview['active_targets_inert'] is True
    assert preview['network_accessed'] is False
    assert store.path.read_bytes() == before
    assert store.search_offline_research() == []


def test_implicit_form_action_and_method_and_unchanged_base(workspace):
    store, make = workspace
    preview = store.preview_offline_research_bundle(make(
        '<base href="https://hostile.example/">'
        '<form><input name="x"></form><form action="" method="POST"></form>'
        '<iframe src="next"></iframe>'))
    examples=preview['items'][0]['active_target_examples']
    assert [x['target_url'] for x in examples] == [
        'https://example.org/report','https://example.org/report','https://example.org/next']
    assert [x['method'] for x in examples[:2]] == ['GET','POST']


@pytest.mark.parametrize('markup', [
    '<form action="javascript:alert(1)"></form>',
    '<iframe src="file:///etc/passwd"></iframe>',
    '<script src="data:text/plain,payload"></script>',
    '<form action="http://localhost/post"></form>',
    '<iframe src="https://example.org:8443/x"></iframe>',
    '<script src=""></script>',
    '<form action="https://example.org:bad/x"></form>',
])
def test_invalid_endpoints_are_warnings_not_normalized(workspace, markup):
    store, make = workspace
    preview=store.preview_offline_research_bundle(make(markup))
    assert preview['active_target_status_counts']['invalid'] == 1
    assert preview['items'][0]['active_target_examples'][0]['target_url'] is None


def test_hidden_markup_ignored_but_real_script_src_seen(workspace):
    store, make = workspace
    preview = store.preview_offline_research_bundle(make(
        '<template><iframe src="https://fake.org/"></iframe></template>'
        '<script><form action="https://fake.org/"></form></script>'
        '<style><iframe src="https://fake.org/"></iframe></style>'
        '<script src="/loaded.js"></script>'))
    assert preview['active_target_count'] == 1
    assert preview['active_target_kind_counts']['script'] == 1


def test_cap_and_plain_text_ignored(workspace):
    store, make = workspace
    preview=store.preview_offline_research_bundle(make('<form action="/check"></form>'*100,plain=True))
    assert preview['active_target_count'] == 8
    assert len(preview['items'][0]['active_target_examples']) == 4
    assert preview['items'][1]['active_target_count'] == 0


def test_original_file_mutated_after_approval_rejected(workspace, tmp_path):
    store, make = workspace
    path=make('<form method="post" action="/old"></form>')
    preview=store.preview_offline_research_bundle(path)
    (tmp_path/'evidence.html').write_text('<h1>Offline source</h1><form method="post" action="https://other.org/new"></form>', encoding='utf-8')
    with pytest.raises(ValueError, match='다시 검토'):
        store.import_offline_research_bundle(path,expected_preview_token=preview['preview_token'])
    assert store.search_offline_research() == []
    refreshed=store.preview_offline_research_bundle(path)
    assert refreshed['preview_token'] != preview['preview_token']
    assert len(store.import_offline_research_bundle(
        path,expected_preview_token=refreshed['preview_token'])['capture_ids']) == 1


def test_explicit_approval_required_even_other_origin(workspace):
    store, make = workspace
    path=make('<form method="POST" action="https://outside.org/upload"></form>')
    preview=store.preview_offline_research_bundle(path)
    assert preview['importable']
    assert store.search_offline_research() == []
    assert len(store.import_offline_research_bundle(
        path,expected_preview_token=preview['preview_token'])['capture_ids']) == 1


def test_owner_authentication_and_blocked_network(workspace):
    store, make = workspace
    path=make('<script src="https://outside.org/app.js"></script>')
    def forbidden(*args,**kwargs):
        raise AssertionError('network request forbidden')
    with patch.object(socket.socket,'connect',forbidden), \
         patch.object(socket.socket,'connect_ex',forbidden), \
         patch.object(socket.socket,'sendall',forbidden), \
         patch.object(socket.socket,'sendto',forbidden), \
         patch.object(socket,'getaddrinfo',forbidden):
        assert store.preview_offline_research_bundle(path)['active_target_count'] == 1
    store.logout()
    with pytest.raises(AuthenticationError):
        store.preview_offline_research_bundle(path)


def test_parser_empty_html():
    assert inspect_offline_active_targets('<p>No form or frames</p>', 'https://example.org/page') == []
