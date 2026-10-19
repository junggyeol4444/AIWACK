"""Offline research bundle HTML form-type preview, never submits inputs."""
import json
import socket
from unittest.mock import patch

import pytest

from desktop.research_captures import inspect_offline_form_controls
from desktop.storage import AuthenticationError, LocalStore


@pytest.fixture
def local_bundle(tmp_path):
    store = LocalStore(tmp_path / 'company.sqlite3')
    store.setup_owner('form-owner', 'local-only-password')

    def make(html, *, plain=False):
        (tmp_path / 'capture.html').write_text('<h1>Offline snapshot</h1>' + html, encoding='utf-8')
        items = [{'file': 'capture.html', 'url': 'https://example.org/report', 'title': 'Claimed report'}]
        if plain:
            (tmp_path / 'note.txt').write_text(
                '<form><input type="password"></form>', encoding='utf-8')
            items.append({'file': 'note.txt', 'url': 'https://example.org/note', 'title': 'Plain note'})
        manifest = tmp_path / 'manifest.json'
        manifest.write_text(json.dumps({'format': 'aiwack-offline-research-bundle-v1',
                                        'items': items}), encoding='utf-8')
        return manifest
    return store, make


def test_sensitive_types_and_get_warning_without_reading_values(local_bundle):
    store, make = local_bundle
    before = store.path.read_bytes()
    preview = store.preview_offline_research_bundle(make(
        '<form action="https://other.example/login">'
        '<input type="PASSWORD" name="username" value="TOPSECRET">'
        '<input type="file" name="private-file">'
        '<input type="hidden" value="SESSION-SECRET"></form>'
        '<form method="POST"><input type="password" value="ANOTHER-SECRET"></form>'))
    assert preview['form_control_count'] == 4
    assert preview['form_control_kind_counts'] == {'password': 2, 'file': 1, 'hidden': 1}
    assert preview['form_password_get_count'] == 1
    assert preview['form_controls_inert'] is True
    assert preview['form_values_captured'] is False
    assert [c['method'] for c in preview['items'][0]['form_control_examples']] == ['GET','GET','GET','POST']
    assert [c['form_ordinal'] for c in preview['items'][0]['form_control_examples']] == [1,1,1,2]
    assert 'TOPSECRET' not in str(preview)
    assert 'SESSION-SECRET' not in str(preview)
    assert 'ANOTHER-SECRET' not in str(preview)
    assert 'username' not in str(preview)
    assert store.path.read_bytes() == before
    assert store.search_offline_research() == []


@pytest.mark.parametrize('html', [
    '<input type="password">',  # not nested in an explicit form
    '<template><form><input type="file"></form></template>',
    '<script>"<form><input type=password></form>"</script>',
    '<style><form><input type="hidden"></form></style>',
    '<form><input type="text" value="secret"></form>',
    '<form><textarea>secret</textarea></form>',
])
def test_non_scoped_and_inert_markup_ignored(html):
    assert inspect_offline_form_controls(html) == []


def test_multiple_forms_and_method_validation():
    controls = inspect_offline_form_controls(
        '<form method="post"><input type="password" /></form>'
        '<form method="PATCH"><input type="password"></form>'
        '<form method="get"><input type="hidden"></form>')
    assert [(x['kind'], x['method'], x['form_ordinal'], x['password_in_get']) for x in controls] == [
        ('password', 'POST', 1, False), ('password', 'OTHER', 2, False),
        ('hidden', 'GET', 3, False)]


def test_bounded_eight_controls_and_plain_text_excluded(local_bundle):
    store, make = local_bundle
    preview = store.preview_offline_research_bundle(make(
        '<form>' + '<input type="hidden" value="private">' * 100 + '</form>', plain=True))
    assert preview['form_control_count'] == 8
    assert len(preview['items'][0]['form_control_examples']) == 4
    assert preview['items'][1]['form_control_count'] == 0


def test_manifest_changes_after_review_require_new_approval(local_bundle, tmp_path):
    store, make = local_bundle
    path = make('<form method="POST"><input type="password"></form>')
    first = store.preview_offline_research_bundle(path)
    (tmp_path / 'capture.html').write_text('<h1>Offline snapshot</h1><form method="GET"><input type="password"></form>',
                                           encoding='utf-8')
    with pytest.raises(ValueError, match='다시 검토'):
        store.import_offline_research_bundle(path, expected_preview_token=first['preview_token'])
    assert store.search_offline_research() == []
    second = store.preview_offline_research_bundle(path)
    assert second['form_password_get_count'] == 1
    assert second['preview_token'] != first['preview_token']
    assert len(store.import_offline_research_bundle(
        path, expected_preview_token=second['preview_token'])['capture_ids']) == 1


def test_network_calls_blocked_and_requires_owner(local_bundle):
    store, make = local_bundle
    manifest = make('<form><input type="password" value="example"></form>')
    def forbidden(*args, **kwargs):
        raise AssertionError('Unexpected socket/DNS call')
    with patch.object(socket.socket, 'connect', forbidden), \
         patch.object(socket.socket, 'sendto', forbidden), \
         patch.object(socket, 'getaddrinfo', forbidden):
        assert store.preview_offline_research_bundle(manifest)['form_password_get_count'] == 1
    store.logout()
    with pytest.raises(AuthenticationError):
        store.preview_offline_research_bundle(manifest)
