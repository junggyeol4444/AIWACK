"""Stage54 continuation: imports user-selected local files without ever fetching URLs."""
import hashlib
import sqlite3
import socket
from pathlib import Path
import pytest
from desktop.storage import LocalStore, AuthenticationError
from desktop.research_captures import MAX_RAW_BYTES

@pytest.fixture
def owner(tmp_path):
    store = LocalStore(tmp_path / 'existing.sqlite3')
    store.setup_owner('offline-file-owner', 'secure-owner-passphrase-2026')
    return store


def test_html_file_raw_hash_and_text_hash_remain_distinct(owner, tmp_path):
    raw = b'<html><h1>Market</h1><script>danger()</script><p>Demand &amp; supply</p></html>'
    snapshot = tmp_path / 'local_capture.HTML'
    snapshot.write_bytes(raw)
    ident = owner.import_offline_research_file('https://example.org/reports', 'Local example', str(snapshot))
    doc = owner.read_offline_research(ident)
    assert 'Market' in doc['body'] and 'Demand & supply' in doc['body']
    assert 'danger()' not in doc['body']
    assert doc['capture_kind'] == 'html_snapshot'
    assert doc['source_verification'] == 'unverified'
    assert doc['content_sha256'] == hashlib.sha256(doc['body'].encode()).hexdigest()
    provenance = doc['local_import']
    assert provenance['original_filename'] == snapshot.name
    assert provenance['raw_sha256'] == hashlib.sha256(raw).hexdigest()
    assert provenance['raw_sha256'] != doc['content_sha256']
    assert provenance['raw_size'] == len(raw)
    assert str(tmp_path) not in str(provenance)
    assert owner.search_offline_research('Market')[0]['id'] == ident
    owner.logout()
    next_session = LocalStore(owner.path)
    next_session.login('offline-file-owner', 'secure-owner-passphrase-2026')
    assert next_session.read_offline_research(ident) == doc


def test_existing_captures_migrate_and_keep_legacy_data(owner, tmp_path):
    legacy = owner.add_offline_research('https://example.org/legacy', 'Legacy', 'Old text')
    assert owner.read_offline_research(legacy)['local_import'] is None
    file = tmp_path / 'sample.md'
    file.write_text('# New local file', encoding='utf-8')
    new = owner.import_offline_research_file('https://example.org/new', 'New', file)
    assert owner.read_offline_research(legacy)['body'] == 'Old text'
    assert owner.read_offline_research(new)['local_import']['raw_size'] == file.stat().st_size
    reopened = LocalStore(owner.path)
    reopened.login('offline-file-owner', 'secure-owner-passphrase-2026')
    assert reopened.read_offline_research(legacy)['local_import'] is None
    assert reopened.read_offline_research(new)['local_import'] is not None


def test_bom_is_accepted_and_raw_hash_tracks_the_bom(owner, tmp_path):
    file = tmp_path / 'snapshot.txt'
    raw = b'\xef\xbb\xbfcontent from local file'
    file.write_bytes(raw)
    ident = owner.import_offline_research_file('https://example.org/bom', 'BOM', file)
    doc = owner.read_offline_research(ident)
    assert doc['body'] == 'content from local file'
    assert doc['local_import']['raw_sha256'] == hashlib.sha256(raw).hexdigest()


@pytest.mark.parametrize('name,data', [
    ('bad.png', b'actual bytes'),
    ('invalid.txt', b'\xff\xfe'),
    ('empty.txt', b''),
    ('oversized.html', b'x'*(MAX_RAW_BYTES + 1)),
    ('only_script.html', b'<script>alert(1)</script>'),
    ('invalid_binary.txt', b'a\x00b'),
], ids=['bad_extension', 'invalid_utf8', 'empty', 'oversized', 'script_only', 'nul_byte'])
def test_unsafe_or_invalid_local_files_rejected_without_db_changes(owner, tmp_path, name, data):
    path = tmp_path / name
    path.write_bytes(data)
    with pytest.raises(ValueError):
        owner.import_offline_research_file('https://example.org/raw', 'test', path)
    assert owner.search_offline_research() == []
    with sqlite3.connect(owner.path) as db:
        assert db.execute('SELECT COUNT(*) FROM offline_research_local_imports').fetchone()[0] == 0


def test_network_path_and_missing_file_rejected(owner, tmp_path):
    for path in ('\\\\server\\share\\doc.txt','//host/share/doc.txt',
                 tmp_path / 'missing.html'):
        with pytest.raises(ValueError):
            owner.import_offline_research_file('https://example.org/example','Title',path)


def test_symlink_rejected(owner, tmp_path):
    target=tmp_path/'safe.txt'
    target.write_text('safe', encoding='utf-8')
    shortcut=tmp_path/'shortcut.txt'
    try:
        shortcut.symlink_to(target)
    except (OSError, NotImplementedError):
        pytest.skip('Creating symbolic links requires privileges on this platform')
    with pytest.raises(ValueError):
        owner.import_offline_research_file('https://example.org','Title',shortcut)


def test_dedup_and_immutable_file_provenance(owner, tmp_path):
    path=tmp_path/'capture.txt'
    path.write_text('unchanged content', encoding='utf-8')
    ident=owner.import_offline_research_file('https://example.org/p','Title',path)
    with pytest.raises(ValueError, match='이미'):
        owner.import_offline_research_file('https://example.org/p','Again',path)
    with sqlite3.connect(owner.path) as db:
        assert db.execute('SELECT COUNT(*) FROM offline_research_local_imports').fetchone()[0] == 1
        with pytest.raises(sqlite3.IntegrityError):
            db.execute('UPDATE offline_research_local_imports SET raw_sha256=? WHERE capture_id=?',('x'*64,ident))
        with pytest.raises(sqlite3.IntegrityError):
            db.execute('DELETE FROM offline_research_local_imports WHERE capture_id=?',(ident,))
    owner.archive_offline_research(ident)
    assert owner.read_offline_research(ident)['local_import']['raw_size'] == path.stat().st_size


def test_unlogged_owner_cannot_import_even_if_file_exists(owner, tmp_path):
    path=tmp_path/'capture.txt';path.write_text('secret',encoding='utf-8')
    owner.logout()
    with pytest.raises(AuthenticationError):
        owner.import_offline_research_file('https://example.org','Title',path)
    assert path.exists()


def test_blocked_sockets_are_not_used_by_local_import(owner, tmp_path, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError('remote connection attempted')
    monkeypatch.setattr(socket.socket,'connect',forbidden)
    monkeypatch.setattr(socket.socket,'connect_ex',forbidden)
    monkeypatch.setattr(socket,'create_connection',forbidden)
    file=tmp_path/'doc.htm';file.write_text('<h1>offline</h1>',encoding='utf-8')
    ident=owner.import_offline_research_file('https://example.org','Title',file)
    assert owner.read_offline_research(ident)['body']=='offline'
