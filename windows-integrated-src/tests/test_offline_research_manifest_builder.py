"""Owner-only, offline, no DB writes: create bundle JSON before preview/import."""
import hashlib
import json
import socket
from pathlib import Path
from unittest.mock import patch

import pytest

from desktop.storage import AuthenticationError, LocalStore


@pytest.fixture
def env(tmp_path):
    store = LocalStore(tmp_path / 'local.sqlite3')
    store.setup_owner('manifest-owner', 'local-manifest-password-2026')
    (tmp_path / 'a.txt').write_text('Alpha research', encoding='utf-8')
    (tmp_path / 'b.html').write_text('<p>Beta</p>', encoding='utf-8')
    records = [(tmp_path / 'a.txt','https://example.org/a','Alpha'),
               (tmp_path / 'b.html','https://example.org/b#frag','베타')]
    return store, tmp_path, records


def test_create_preview_import_roundtrip_without_automatic_db_mutation(env):
    store, folder, records = env
    existing = store.path.read_bytes()
    result = store.create_offline_research_bundle_manifest(records, folder / 'batch.json')
    assert store.path.read_bytes() == existing
    data = (folder / 'batch.json').read_bytes()
    obj = json.loads(data)
    assert set(obj) == {'format','items'}
    assert obj['items'][1]['url'] == 'https://example.org/b'
    assert result['manifest_sha256'] == hashlib.sha256(data).hexdigest()
    assert result['source_verified'] is False
    assert all(i['raw_size'] > 0 for i in result['input_files'])
    preview = store.preview_offline_research_bundle(folder / 'batch.json')
    assert preview['importable'] and preview['item_count'] == 2
    assert store.path.read_bytes() == existing
    imported = store.import_offline_research_bundle(folder / 'batch.json',
                      expected_preview_token=preview['preview_token'])
    assert len(imported['capture_ids']) == 2
    assert store.read_offline_research(imported['capture_ids'][1])['body'] == 'Beta'


def test_existing_manifest_never_overwritten(env):
    store, folder, entries = env
    dest = folder / 'batch.json'
    dest.write_text('existing', encoding='utf-8')
    with pytest.raises(ValueError, match='덮어쓰지'):
        store.create_offline_research_bundle_manifest(entries,dest)
    assert dest.read_text() == 'existing'


@pytest.mark.parametrize('entries_error', ['zero','many','duplicate','bad_url','bad_title',
                                           'missing','bad_extension','other_folder','same_as_dest'])
def test_bad_inputs_are_rejected_before_creating_file(env, entries_error):
    store, folder, valid = env
    records = list(valid)
    if entries_error == 'zero': records=[]
    if entries_error == 'many': records=records*11
    if entries_error == 'duplicate': records=[records[0], records[0]]
    if entries_error == 'bad_url': records=[(valid[0][0], 'file:///unsafe', 'Title')]
    if entries_error == 'bad_title': records=[(valid[0][0], 'https://example.org',' ')]
    if entries_error == 'missing': records=[(folder/'missing.txt', 'https://example.org','Test')]
    if entries_error == 'bad_extension':
        x=folder/'bad.exe';x.write_text('abc');records=[(x,'https://example.org','Bad')]
    if entries_error == 'other_folder':
        x=folder/'sub';x.mkdir(); y=x/'valid.txt';y.write_text('abc')
        records=[(y,'https://example.org','Bad')]
    if entries_error == 'same_as_dest':
        x=folder/'batch.json';x.write_text('test')
        records=[(x,'https://example.org','Bad')]
    with pytest.raises(ValueError):
        store.create_offline_research_bundle_manifest(records,folder/'batch.json')
    if entries_error != 'same_as_dest':
        assert not (folder/'batch.json').exists()


@pytest.mark.parametrize('destination', ['relative.json','//example/share.json','\\\\host\\share\\batch.json',
                                        'bad.txt'])
def test_unsafe_destinations(env, destination):
    store, folder, entries=env
    with pytest.raises(ValueError):
        store.create_offline_research_bundle_manifest(entries,destination)


def test_symlink_file_or_parent_rejected(env):
    store,folder,records=env
    linked=folder/'link.txt'
    try: linked.symlink_to(folder/'a.txt')
    except (OSError,NotImplementedError): pytest.skip('symlinks unavailable')
    with pytest.raises(ValueError,match='심볼릭'):
        store.create_offline_research_bundle_manifest([(linked,'https://example.org','Test')],folder/'bundle.json')
    redirected=folder/'redirect';redirected.symlink_to(folder,target_is_directory=True)
    with pytest.raises(ValueError,match='심볼릭'):
        store.create_offline_research_bundle_manifest([(redirected/'a.txt','https://example.org','Test')],redirected/'bundle.json')


def test_logged_out_user_cannot_create(env):
    store,folder,records=env
    store.logout()
    with pytest.raises(AuthenticationError):
        store.create_offline_research_bundle_manifest(records, folder/'batch.json')
    assert not (folder/'batch.json').exists()


def test_cancelled_or_failing_input_never_changes_existing_db(env):
    store,folder,records=env
    previous=store.path.read_bytes()
    with pytest.raises(ValueError):
        store.create_offline_research_bundle_manifest(records[:-1]+[(folder/'missing.txt','https://example.org','Bad')],folder/'batch.json')
    assert store.path.read_bytes() == previous


def test_network_socket_and_dns_disabled(env):
    store,folder,records=env
    def deny(*args,**kwargs):raise AssertionError('network connection forbidden')
    with patch.object(socket.socket,'connect',deny), patch.object(socket.socket,'connect_ex',deny), \
         patch.object(socket.socket,'sendto',deny), patch.object(socket.socket,'sendall',deny), \
         patch.object(socket,'getaddrinfo',deny):
        report=store.create_offline_research_bundle_manifest(records,folder/'bundle.json')
        assert report['network_accessed'] is False
        assert store.preview_offline_research_bundle(folder/'bundle.json')['importable']


def test_format_boundaries_and_unicode(env):
    store,folder,records=env
    records[0]=(records[0][0], 'https://example.org/recherche', '한글 자료')
    report=store.create_offline_research_bundle_manifest(records,folder/'bundle.json')
    assert report['item_count']==2
    assert '한글 자료' in (folder/'bundle.json').read_text(encoding='utf-8')
