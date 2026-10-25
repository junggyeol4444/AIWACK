"""호출 감사·관리자 인계 대량 원본 전수 검사 계약: 임시 SQLite/파일만 사용."""
from __future__ import annotations

import sqlite3
import hashlib
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
    monkeypatch.setattr(evidence, 'read', lambda store, ident: {
        'id': ident, 'filename': str(evidence._folder(store) / _name('call', ident)),
        'sha256': hashlib.sha256(b'sample').hexdigest()})
    monkeypatch.setattr(dossier, 'read', lambda store, ident: {
        'id': ident, 'path': str(dossier._folder(store) / _name('dossier', ident)),
        'file_sha256': hashlib.sha256(b'sample').hexdigest()})
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


@pytest.mark.parametrize('kind', ['call', 'dossier'])
@pytest.mark.parametrize('fault', ['wrong_id', 'wrong_path', 'missing_identity', 'invalid_digest'])
def test_full_audit_rejects_mismatched_verification_identity(local, monkeypatch, kind, fault):
    module = evidence if kind == 'call' else dossier
    table = ('aiwack_campaign_evidence_exports' if kind == 'call'
             else 'aiwack_campaign_owner_dossiers')
    folder = module._folder(local)
    folder.mkdir()
    name = _name(kind, 1)
    (folder / name).write_text('원본', encoding='utf-8')
    with local._connect() as con:
        con.execute('INSERT INTO ' + table + ' VALUES(1,?)', (name,))
    proof = {'id': 1,
             ('filename' if kind == 'call' else 'path'): str(folder / name),
             ('sha256' if kind == 'call' else 'file_sha256'): 'a' * 64}
    if fault == 'wrong_id':
        proof['id'] = 2
    elif fault == 'wrong_path':
        proof['filename' if kind == 'call' else 'path'] = str(folder / 'different.json')
    elif fault == 'missing_identity':
        del proof['id']
    else:
        proof['sha256' if kind == 'call' else 'file_sha256'] = 'z' * 64
    monkeypatch.setattr(module, 'read', lambda store, ident: proof)
    result = module.inspect_disk_consistency_full(local)
    assert result['registered_files_verified'] == []
    assert len(result['registered_files_failed']) == 1
    assert result['all_registered_files_verified'] is False
    assert result['requires_owner_review'] is True
    assert (folder / name).exists()


@pytest.mark.parametrize('kind', ['call', 'dossier'])
def test_inventory_fingerprint_is_repeatable_and_changes_with_candidate_set(local, kind):
    module = evidence if kind == 'call' else dossier
    folder = module._folder(local)
    folder.mkdir()
    first = module.inspect_disk_consistency_full(local)
    second = module.inspect_disk_consistency_full(local)
    assert first['inventory_snapshot_sha256'] == second['inventory_snapshot_sha256']
    assert len(first['inventory_snapshot_sha256']) == 64
    assert first['inventory_snapshot_is_signature'] is False
    (folder / _name(kind, 42)).write_text('고아 파일', encoding='utf-8')
    third = module.inspect_disk_consistency_full(local)
    assert third['inventory_snapshot_sha256'] != first['inventory_snapshot_sha256']
    assert third['requires_owner_review'] is True


@pytest.mark.parametrize('kind', ['call', 'dossier'])
def test_same_basename_in_other_directory_cannot_validate_registered_archive(
        local, monkeypatch, kind):
    module = evidence if kind == 'call' else dossier
    table = ('aiwack_campaign_evidence_exports' if kind == 'call'
             else 'aiwack_campaign_owner_dossiers')
    folder = module._folder(local)
    folder.mkdir()
    name = _name(kind, 1)
    (folder / name).write_text('original', encoding='utf-8')
    with local._connect() as con:
        con.execute('INSERT INTO ' + table + ' VALUES(1,?)', (name,))
    outside = folder.parent / 'other_archive' / name
    outside.parent.mkdir()
    outside.write_text('different', encoding='utf-8')
    proof = {'id': 1,
             ('filename' if kind == 'call' else 'path'): str(outside),
             ('sha256' if kind == 'call' else 'file_sha256'): 'a' * 64}
    monkeypatch.setattr(module, 'read', lambda store, ident: proof)
    result = module.inspect_disk_consistency_full(local)
    assert result['registered_files_verified'] == []
    assert len(result['registered_files_failed']) == 1
    assert result['requires_owner_review'] is True
    assert (folder / name).read_text(encoding='utf-8') == 'original'


@pytest.mark.parametrize('kind', ['call', 'dossier'])
def test_missing_registered_archive_never_passes_even_if_verifier_returns_success(
        local, kind):
    module = evidence if kind == 'call' else dossier
    table = ('aiwack_campaign_evidence_exports' if kind == 'call'
             else 'aiwack_campaign_owner_dossiers')
    folder = module._folder(local)
    folder.mkdir()
    name = _name(kind, 1)
    with local._connect() as con:
        con.execute('INSERT INTO ' + table + ' VALUES(1,?)', (name,))
    result = module.inspect_disk_consistency_full(local)
    assert result['registered_files_verified'] == []
    assert len(result['registered_files_failed']) == 1
    assert result['all_registered_files_verified'] is False


@pytest.mark.parametrize('kind', ['call', 'dossier'])
@pytest.mark.parametrize('exception', [TypeError('broken payload'), KeyError('missing field')])
def test_malformed_verifier_failure_is_classified_without_stopping_whole_audit(
        local, monkeypatch, kind, exception):
    module = evidence if kind == 'call' else dossier
    table = ('aiwack_campaign_evidence_exports' if kind == 'call'
             else 'aiwack_campaign_owner_dossiers')
    folder = module._folder(local)
    folder.mkdir()
    name = _name(kind, 1)
    (folder / name).write_text('original', encoding='utf-8')
    with local._connect() as con:
        con.execute('INSERT INTO ' + table + ' VALUES(1,?)', (name,))
    def malformed(store, ident):
        raise exception
    monkeypatch.setattr(module, 'read', malformed)
    result = module.inspect_disk_consistency_full(local)
    assert result['registered_files_verified'] == []
    assert len(result['registered_files_failed']) == 1
    assert result['registered_files_failed'][0]['error_type'] == type(exception).__name__
    assert result['requires_owner_review'] is True


@pytest.mark.parametrize('kind', ['call', 'dossier'])
def test_full_audit_checks_actual_file_hash_not_only_verifier_claim(local, kind):
    module = evidence if kind == 'call' else dossier
    table = ('aiwack_campaign_evidence_exports' if kind == 'call'
             else 'aiwack_campaign_owner_dossiers')
    folder = module._folder(local)
    folder.mkdir()
    name = _name(kind, 1)
    with local._connect() as con:
        con.execute('INSERT INTO ' + table + ' VALUES(1,?)', (name,))
    (folder / name).write_bytes(b'changed-original')
    result = module.inspect_disk_consistency_full(local)
    assert result['registered_files_verified'] == []
    assert len(result['registered_files_failed']) == 1
    assert 'SHA256' in result['registered_files_failed'][0]['reason']
    assert result['requires_owner_review'] is True
    assert (folder / name).read_bytes() == b'changed-original'


@pytest.mark.parametrize('kind', ['call', 'dossier'])
def test_full_audit_classifies_crash_leftover_with_non_json_suffix(local, kind):
    module = evidence if kind == 'call' else dossier
    folder = module._folder(local)
    folder.mkdir()
    name = _name(kind, 1) + '.tmp'
    (folder / name).write_bytes(b'unregistered-partial-write')
    result = module.inspect_disk_consistency_full(local)
    assert result['unsafe_candidate_paths'] == [name]
    assert result['all_registered_files_verified'] is False
    assert result['requires_owner_review'] is True
    assert result['files_deleted'] is False
