"""Local SQLite/disk recovery inventory checks, not Windows/GGUF acceptance."""
from __future__ import annotations

import sqlite3
from pathlib import Path
from uuid import uuid4

import pytest
from desktop import company_campaign_owner_dossier as dossier


class _InventoryStore:
    def __init__(self, path: Path):
        self.path = str(path)

    def require_permission(self, permission):
        assert permission == 'company:manage'

    def _connect(self):
        return sqlite3.connect(self.path)


def _setup(tmp_path):
    store = _InventoryStore(tmp_path / 'owner.sqlite')
    with store._connect() as con:
        dossier.initialize(con)
    return store, dossier._folder(store)


def test_unregistered_crash_orphan_never_deleted(tmp_path):
    store, folder = _setup(tmp_path)
    folder.mkdir()
    orphan = folder / ('owner_final_' + uuid4().hex + '.json')
    orphan.write_text('{"interrupted":true}', encoding='utf-8')
    state = dossier.inspect_disk_consistency(store)
    assert state['orphaned_unregistered_files'] == [orphan.name]
    assert state['requires_owner_review'] is True
    assert state['no_orphaned_files_confirmed'] is False
    assert state['automatic_recovery_performed'] is False
    assert orphan.exists()


def test_symlinked_owner_folder_is_rejected(tmp_path):
    store, folder = _setup(tmp_path)
    outside = tmp_path / 'outside'
    outside.mkdir()
    try:
        folder.symlink_to(outside, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip('Symlinks unavailable on this filesystem')
    with pytest.raises(ValueError, match='안전한'):
        dossier.inspect_disk_consistency(store)


def test_registered_missing_file_is_not_marked_verified(tmp_path, monkeypatch):
    store, folder = _setup(tmp_path)
    missing = 'owner_final_' + uuid4().hex + '.json'
    with store._connect() as con:
        con.execute('''INSERT INTO aiwack_campaign_owner_dossiers
            (campaign_id,report_id,final_report_sha256,evidence_sha256,
             filename,file_sha256,byte_count) VALUES(?,?,?,?,?,?,?)''',
            (1,1,'a'*64,'b'*64,missing,'c'*64,12))
    state = dossier.inspect_disk_consistency(store)
    assert state['registered_files_failed'][0]['filename'] == missing
    assert state['requires_owner_review'] is True
    assert state['registered_files_verified'] == []


def test_bounded_scan_never_claims_complete_when_truncated(tmp_path):
    store, folder = _setup(tmp_path)
    folder.mkdir()
    for _ in range(3):
        (folder / ('owner_final_' + uuid4().hex + '.json')).write_text('{}')
    state = dossier.inspect_disk_consistency(store, limit=1)
    assert state['scan_complete'] is False
    assert state['no_orphaned_files_confirmed'] is False
    assert state['requires_owner_review'] is True
