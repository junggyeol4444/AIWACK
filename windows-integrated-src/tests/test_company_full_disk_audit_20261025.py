"""호출 감사·관리자 인계 대량 원본 전수 검사 계약: 임시 SQLite/파일만 사용."""
from __future__ import annotations

import sqlite3
import pytest
from desktop import company_campaign_evidence as evidence
from desktop import company_campaign_owner_dossier as dossier


class _Store:
    def __init__(self, path):
        self.path = str(path)
        with self._connect() as con:
            for table in ('aiwack_campaign_evidence_exports',
                          'aiwack_campaign_owner_dossiers'):
                con.execute('CREATE TABLE ' + table +
                            '(id INTEGER PRIMARY KEY, filename TEXT UNIQUE)')

    def _connect(self):
        return sqlite3.connect(self.path)

    def require_permission(self, permission):
        assert permission == 'company:manage'


@pytest.fixture
def local(tmp_path, monkeypatch):
    monkeypatch.setattr(evidence, 'initialize', lambda con: None)
    monkeypatch.setattr(dossier, 'initialize', lambda con: None)
    monkeypatch.setattr(evidence, 'read', lambda store, ident: {'sha256': 'a' * 64})
    monkeypatch.setattr(dossier, 'read', lambda store, ident: {'file_sha256': 'b' * 64})
    return _Store(tmp_path / 'company.sqlite')


def _name(kind, number):
    if kind == 'call':
        return f'campaign_1_1_{number:020x}.json'
    return f'owner_final_{number:032x}.json'


@pytest.mark.parametrize('kind', ['call', 'dossier'])
def test_more_than_1000_registered_originals_are_scanned(local, kind):
    module = evidence if kind == 'call' else dossier
    table = ('aiwack_campaign_evidence_exports' if kind == 'call'
             else 'aiwack_campaign_owner_dossiers')
    folder = module._folder(local)
    folder.mkdir()
    with local._connect() as con:
        con.executemany('INSERT INTO ' + table + ' VALUES(?,?)',
                        [(i, _name(kind, i)) for i in range(1, 1002)])
    for i in range(1, 1002):
        (folder / _name(kind, i)).write_text('sample', encoding='utf-8')
    result = module.inspect_disk_consistency_full(local, 1500)
    assert result['registered_rows_scanned'] == 1001
    assert result['candidate_files_scanned'] == 1001
    assert result['all_registered_files_verified'] is True
    assert result['requires_owner_review'] is False
    partial = module.inspect_disk_consistency_full(local, 1000)
    assert partial['scan_complete'] is False
    assert partial['all_registered_files_verified'] is False
    assert partial['requires_owner_review'] is True
    assert partial['orphaned_unregistered_files'] == []


@pytest.mark.parametrize('kind', ['call', 'dossier'])
def test_orphan_and_invalid_candidate_require_review_without_deletion(local, kind):
    module = evidence if kind == 'call' else dossier
    folder = module._folder(local)
    folder.mkdir()
    orphan = folder / _name(kind, 777)
    malformed = folder / ('campaign_bad.json' if kind == 'call'
                          else 'owner_final_bad.json')
    orphan.write_text('orphan', encoding='utf-8')
    malformed.write_text('unsafe', encoding='utf-8')
    result = module.inspect_disk_consistency_full(local)
    assert result['orphaned_unregistered_files'] == [orphan.name]
    assert result['unsafe_candidate_paths'] == [malformed.name]
    assert result['requires_owner_review'] is True
    assert result['files_deleted'] is False
    assert orphan.exists() and malformed.exists()


@pytest.mark.parametrize('invalid', [True, False, 0, -1, 1.0, '10', 10001])
def test_full_audit_limit_is_exact_bounded_integer(local, invalid):
    with pytest.raises(ValueError, match='1~10000'):
        evidence.inspect_disk_consistency_full(local, invalid)


def test_registered_but_damaged_proof_is_not_success(local, monkeypatch):
    folder = evidence._folder(local)
    folder.mkdir()
    name = _name('call', 1)
    with local._connect() as con:
        con.execute('INSERT INTO aiwack_campaign_evidence_exports VALUES(1,?)',
                    (name,))
    (folder / name).write_text('sample', encoding='utf-8')
    monkeypatch.setattr(evidence, 'read', lambda store, ident:
                        (_ for _ in ()).throw(ValueError('원본 손상')))
    result = evidence.inspect_disk_consistency_full(local)
    assert len(result['registered_files_failed']) == 1
    assert result['all_registered_files_verified'] is False
    assert result['requires_owner_review'] is True
