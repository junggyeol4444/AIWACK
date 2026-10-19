"""Stage54 partial: offline-only manifest batch imports and durable provenance."""
import hashlib
import json
import socket
import sqlite3
from pathlib import Path
import pytest

from desktop.storage import AuthenticationError, LocalStore


@pytest.fixture
def owner(tmp_path):
    db = LocalStore(tmp_path / 'bundle.sqlite3')
    db.setup_owner('bundle-owner', 'secure-bundle-password-for-testing')
    return db


def manifest(tmp_path, items, *, filename='bundle.json'):
    path = tmp_path / filename
    path.write_text(json.dumps({'format':'aiwack-offline-research-bundle-v1',
                                'items':items}, ensure_ascii=False), encoding='utf-8')
    return path


def records(*names):
    return [{'file':name, 'url':f'https://example.org/{i}', 'title':f'자료 {i}'}
            for i, name in enumerate(names, 1)]


def test_multiple_files_provenance_and_restart(owner, tmp_path):
    raw = b'<h1>Offline report</h1><script>alert(1)</script><p>Evidence</p>'
    (tmp_path / 'one.html').write_bytes(raw)
    (tmp_path / 'two.txt').write_text('Second document', encoding='utf-8')
    bundle = manifest(tmp_path, records('one.html','two.txt'))
    result = owner.import_offline_research_bundle(bundle)
    assert len(result['capture_ids']) == 2
    assert result['manifest_sha256'] == hashlib.sha256(bundle.read_bytes()).hexdigest()
    first, second = [owner.read_offline_research(i) for i in result['capture_ids']]
    assert first['body'] == 'Offline report\nEvidence'
    assert first['local_import']['raw_sha256'] == hashlib.sha256(raw).hexdigest()
    assert first['bundle_import']['ordinal'] == 1
    assert second['bundle_import']['ordinal'] == 2
    assert second['body'] == 'Second document'
    assert first['source_verification'] == 'unverified'
    assert 'alert(1)' not in first['body']
    assert len(owner.search_offline_research()) == 2
    owner.logout()
    reopened = LocalStore(owner.path)
    reopened.login('bundle-owner', 'secure-bundle-password-for-testing')
    assert reopened.read_offline_research(result['capture_ids'][0]) == first
    assert reopened.read_offline_research(result['capture_ids'][1]) == second


def test_duplicate_in_manifest_rolls_back_everything(owner, tmp_path):
    (tmp_path/'one.txt').write_text('equal bytes', encoding='utf-8')
    (tmp_path/'two.txt').write_text('equal bytes', encoding='utf-8')
    entries = records('one.txt','two.txt')
    entries[1]['url'] = entries[0]['url']
    with pytest.raises(ValueError, match='이미'):
        owner.import_offline_research_bundle(manifest(tmp_path, entries))
    assert owner.search_offline_research() == []
    with sqlite3.connect(owner.path) as con:
        for table in ('offline_research_batches', 'offline_research_batch_items',
                      'offline_research_local_imports', 'offline_research_captures'):
            assert con.execute(f'SELECT count(*) FROM {table}').fetchone()[0] == 0


def test_existing_duplicate_rolls_back_new_import(owner, tmp_path):
    (tmp_path/'one.txt').write_text('new',encoding='utf-8')
    (tmp_path/'two.txt').write_text('already registered',encoding='utf-8')
    entries = records('one.txt','two.txt')
    original = owner.import_offline_research_file(entries[1]['url'], 'Original', tmp_path/'two.txt')
    with pytest.raises(ValueError):
        owner.import_offline_research_bundle(manifest(tmp_path, entries))
    assert len(owner.search_offline_research()) == 1
    assert owner.read_offline_research(original)['bundle_import'] is None
    with sqlite3.connect(owner.path) as con:
        assert con.execute('SELECT count(*) FROM offline_research_batches').fetchone()[0] == 0


def test_broken_second_file_rolls_back_everything(owner,tmp_path):
    (tmp_path/'one.txt').write_text('good',encoding='utf-8')
    bundle=manifest(tmp_path, records('one.txt','missing.html'))
    with pytest.raises(ValueError):
        owner.import_offline_research_bundle(bundle)
    assert not owner.search_offline_research()


@pytest.mark.parametrize('item', ['../outside.txt', '/tmp/path.html', 'folder/page.html',
                                  'folder\\page.txt', 'C:page.html', '.', '..', ''])
def test_manifest_filename_rejected(owner, tmp_path, item):
    bundle = manifest(tmp_path,[{'file':item, 'title':'title', 'url':'https://example.org'}])
    with pytest.raises(ValueError):
        owner.import_offline_research_bundle(bundle)
    assert owner.search_offline_research() == []


def test_symlink_source_and_manifest_rejected(owner, tmp_path):
    content=tmp_path/'one.txt'; content.write_text('normal',encoding='utf-8')
    link=tmp_path/'shortcut.txt'
    try:
        link.symlink_to(content)
    except (OSError,NotImplementedError):
        pytest.skip('Platform cannot create symlinks')
    bundle=manifest(tmp_path,records('shortcut.txt'))
    with pytest.raises(ValueError):
        owner.import_offline_research_bundle(bundle)
    bundle.unlink()
    bundle.symlink_to(content)
    with pytest.raises(ValueError):
        owner.import_offline_research_bundle(bundle)


def test_overlarge_and_invalid_manifest(owner, tmp_path):
    malformed=tmp_path/'bundle.json'
    malformed.write_bytes(b'{'*100)
    with pytest.raises(ValueError): owner.import_offline_research_bundle(malformed)
    malformed.write_bytes(b' '*32769)
    with pytest.raises(ValueError): owner.import_offline_research_bundle(malformed)
    malformed.write_bytes(b'\xff')
    with pytest.raises(ValueError): owner.import_offline_research_bundle(malformed)


def test_schema_limits_and_duplicate_file_paths(owner,tmp_path):
    file=tmp_path/'one.txt'; file.write_text('ok',encoding='utf-8')
    for entries in ([],records(*(['one.txt']*21)),records('one.txt','one.txt')):
        with pytest.raises(ValueError): owner.import_offline_research_bundle(manifest(tmp_path,entries))
    assert owner.search_offline_research() == []


def test_owner_authentication_before_file_read(owner,tmp_path):
    bundle=manifest(tmp_path,records('missing.txt'))
    owner.logout()
    with pytest.raises(AuthenticationError): owner.import_offline_research_bundle(bundle)
    with sqlite3.connect(owner.path) as con:
        assert con.execute("SELECT count(*) FROM offline_research_batches").fetchone()[0] == 0


def test_sql_provenance_immutable(owner,tmp_path):
    (tmp_path/'one.md').write_text('# Memo',encoding='utf-8')
    result=owner.import_offline_research_bundle(manifest(tmp_path,records('one.md')))
    with sqlite3.connect(owner.path) as con:
        with pytest.raises(sqlite3.IntegrityError):
            con.execute('UPDATE offline_research_batches SET item_count=2')
        with pytest.raises(sqlite3.IntegrityError):
            con.execute('DELETE FROM offline_research_batches')
        with pytest.raises(sqlite3.IntegrityError):
            con.execute('DELETE FROM offline_research_batch_items')
    owner.archive_offline_research(result['capture_ids'][0])
    assert owner.read_offline_research(result['capture_ids'][0])['archived_at']


def test_no_network_calls_even_for_claimed_url(owner,tmp_path,monkeypatch):
    (tmp_path/'one.html').write_text('<p>Downloaded already</p>', encoding='utf-8')
    def denied(*args, **kwargs):
        raise AssertionError('network request forbidden')
    monkeypatch.setattr(socket.socket,'connect',denied)
    monkeypatch.setattr(socket.socket,'connect_ex',denied)
    monkeypatch.setattr(socket,'create_connection',denied)
    result=owner.import_offline_research_bundle(manifest(tmp_path,records('one.html')))
    assert owner.read_offline_research(result['capture_ids'][0])['body']=='Downloaded already'
