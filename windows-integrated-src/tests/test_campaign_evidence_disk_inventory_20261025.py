"""30업무 감사 파일/SQLite 읽기 전용 중단 복구 목록 계약 검사.

임시 SQLite와 로컬 파일만 사용. 실제 Windows GUI·GGUF/결제 검증 아님.
"""
from __future__ import annotations

import sqlite3

import pytest

from desktop import company_campaign_evidence as evidence


class _Store:
    def __init__(self, path):
        self.path = str(path)
        with self._connect() as con:
            con.execute('''CREATE TABLE aiwack_campaign_evidence_exports(
                id INTEGER PRIMARY KEY, filename TEXT UNIQUE)''')

    def _connect(self):
        return sqlite3.connect(self.path)

    def require_permission(self, permission):
        assert permission == 'company:manage'


@pytest.fixture
def audit_store(tmp_path, monkeypatch):
    monkeypatch.setattr(evidence, 'initialize', lambda con: None)
    return _Store(tmp_path / 'company.sqlite')


def _name(campaign=1, step=1, digest='a'):
    return f'campaign_{campaign}_{step}_{digest * 20}.json'


def test_empty_inventory_is_complete_and_read_only(audit_store):
    result = evidence.inspect_disk_consistency(audit_store)
    assert result['scan_complete'] is True
    assert result['requires_owner_review'] is False
    assert result['registered_rows_total'] == 0
    assert result['files_deleted'] is False
    assert result['automatic_recovery_performed'] is False
    assert result['physical_windows_10_11_recovery_verified'] is False


def test_registered_verified_and_damaged_are_separate(audit_store, monkeypatch):
    names = [_name(1, 1), _name(1, 2, 'b')]
    folder = evidence._folder(audit_store)
    folder.mkdir()
    for name in names:
        (folder / name).write_text('{}', encoding='utf-8')
    with audit_store._connect() as con:
        con.executemany('INSERT INTO aiwack_campaign_evidence_exports VALUES(?,?)',
                        [(1, names[0]), (2, names[1])])

    def fake_read(store, ident):
        if ident == 2:
            raise ValueError('원본 SHA 불일치')
        return {'sha256': 'a' * 64}
    monkeypatch.setattr(evidence, 'read', fake_read)
    result = evidence.inspect_disk_consistency(audit_store)
    assert [x['id'] for x in result['registered_files_verified']] == [1]
    assert [x['id'] for x in result['registered_files_failed']] == [2]
    assert result['scan_complete'] is True
    assert result['requires_owner_review'] is True
    assert result['all_scanned_registered_files_intact'] is False
    assert (folder / names[1]).exists()


def test_orphan_and_unsafe_filename_never_deleted(audit_store):
    folder = evidence._folder(audit_store)
    folder.mkdir()
    orphan = folder / _name(4, 3, 'c')
    malformed = folder / 'campaign_bad.json'
    orphan.write_text('orphan', encoding='utf-8')
    malformed.write_text('unsafe', encoding='utf-8')
    result = evidence.inspect_disk_consistency(audit_store)
    assert result['orphaned_unregistered_files'] == [orphan.name]
    assert result['unsafe_candidate_paths'] == [malformed.name]
    assert result['requires_owner_review'] is True
    assert orphan.exists() and malformed.exists()


def test_limit_reports_partial_scan_without_false_success(audit_store, monkeypatch):
    folder = evidence._folder(audit_store)
    folder.mkdir()
    with audit_store._connect() as con:
        for ident in (1, 2):
            name = _name(1, ident, str(ident))
            con.execute('INSERT INTO aiwack_campaign_evidence_exports VALUES(?,?)',
                        (ident, name))
            (folder / name).write_text('evidence', encoding='utf-8')
    monkeypatch.setattr(evidence, 'read', lambda store, ident: {'sha256': 'a' * 64})
    result = evidence.inspect_disk_consistency(audit_store, limit=1)
    assert result['registered_rows_scanned'] == 1
    assert result['registered_rows_total'] == 2
    assert result['scan_complete'] is False
    assert result['requires_owner_review'] is True
    assert result['no_orphaned_files_confirmed'] is False


@pytest.mark.parametrize('bad', [True, 0, -1, 1.0, '1', 1001])
def test_invalid_limit_is_rejected(audit_store, bad):
    with pytest.raises(ValueError, match='1~1000'):
        evidence.inspect_disk_consistency(audit_store, limit=bad)
