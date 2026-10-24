"""기존 인계 파일 읽기 전용 충돌·복구 감사 한도 계약(실기 Windows 시험 아님)."""
from __future__ import annotations

from contextlib import nullcontext

import pytest

from desktop import company_campaign_owner_dossier as dossier


class _Connection:
    def __init__(self, rows):
        self.rows = rows

    def execute(self, query):
        assert 'SELECT id,filename FROM aiwack_campaign_owner_dossiers' in query
        return self

    def fetchall(self):
        return self.rows


class _Store:
    def __init__(self, rows):
        self.rows = rows

    def require_permission(self, permission):
        assert permission == 'company:manage'

    def _connect(self):
        return nullcontext(_Connection(self.rows))


def _name(number):
    return 'owner_final_' + f'{number:032x}' + '.json'


def _setup(monkeypatch, folder):
    monkeypatch.setattr(dossier, '_folder', lambda store: folder)
    monkeypatch.setattr(dossier, 'initialize', lambda con: None)
    monkeypatch.setattr(dossier, 'read',
                        lambda store, ident: {'file_sha256': f'{ident:064x}'})


def test_unrelated_files_do_not_consume_candidate_scan_limit(tmp_path, monkeypatch):
    _setup(monkeypatch, tmp_path)
    for i in range(12):
        (tmp_path / f'unrelated_{i}.txt').write_text('원본', encoding='utf-8')
    (tmp_path / _name(1)).write_text('승인 원본', encoding='utf-8')
    result = dossier.inspect_disk_consistency(_Store([(1, _name(1))]), limit=1)
    assert result['scan_complete'] is True
    assert result['candidate_files_scanned'] == 1
    assert result['registered_rows_total'] == 1
    assert result['orphaned_unregistered_files'] == []
    assert result['no_orphaned_files_confirmed'] is True
    assert result['files_deleted'] is False


def test_unscanned_registered_file_is_not_mislabeled_orphan(tmp_path, monkeypatch):
    _setup(monkeypatch, tmp_path)
    for i in (1, 2):
        (tmp_path / _name(i)).write_text('보존', encoding='utf-8')
    result = dossier.inspect_disk_consistency(
        _Store([(1, _name(1)), (2, _name(2))]), limit=1)
    assert result['registered_rows_total'] == 2
    assert result['registered_rows_scanned'] == 1
    assert result['scan_complete'] is False
    assert result['orphaned_unregistered_files'] == []
    assert result['requires_owner_review'] is True
    assert result['no_orphaned_files_confirmed'] is False


def test_true_orphan_remains_visible_without_mutation(tmp_path, monkeypatch):
    _setup(monkeypatch, tmp_path)
    (tmp_path / _name(7)).write_text('SQLite 미등록', encoding='utf-8')
    result = dossier.inspect_disk_consistency(_Store([]), limit=10)
    assert result['scan_complete'] is True
    assert result['orphaned_unregistered_files'] == [_name(7)]
    assert result['requires_owner_review'] is True
    assert (tmp_path / _name(7)).exists()
    assert result['automatic_recovery_performed'] is False


@pytest.mark.parametrize('invalid', [True, 0, 1001, '10'])
def test_invalid_scan_limit_fails_closed(tmp_path, monkeypatch, invalid):
    _setup(monkeypatch, tmp_path)
    with pytest.raises(ValueError, match='한도'):
        dossier.inspect_disk_consistency(_Store([]), limit=invalid)
