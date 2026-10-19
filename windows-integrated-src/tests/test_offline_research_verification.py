"""Stage54: local evidence export inspection without DB mutation or web fetch."""
import json
import socket
import sqlite3

import pytest

from desktop.storage import AuthenticationError, LocalStore
from desktop.research_exports import MAX_EXPORT_BYTES


@pytest.fixture
def owner(tmp_path):
    store = LocalStore(tmp_path / 'local.sqlite3')
    store.setup_owner('verify-owner', 'verify-owner-password-2026')
    store.add_offline_research('https://example.org/study', 'Study',
                               'first line\nsecond evidence alpha')
    return store


def exported(owner, tmp_path, query='alpha', *, include_archived=False):
    path = tmp_path / 'report.json'
    owner.export_local_research_evidence(query, path, include_archived=include_archived)
    return path


def test_export_matches_current_db(owner, tmp_path):
    result = owner.inspect_local_research_evidence_export(exported(owner, tmp_path))
    assert result['checksum_matches'] is True
    assert result['local_report_matches'] is True
    assert result['matching_scope'] == 'active'
    assert result['exported_hit_count'] == 1
    assert result['source_authenticity_verified'] is False
    assert result['network_accessed'] is False


def test_archived_export_matches_archived_scope(owner, tmp_path):
    capture_id = owner.local_research_evidence_report('alpha')['hits'][0]['capture_id']
    owner.archive_offline_research(capture_id)
    result = owner.inspect_local_research_evidence_export(
        exported(owner, tmp_path, include_archived=True))
    assert result['local_report_matches'] is True
    assert result['matching_scope'] == 'including_archived'


def test_export_stale_after_archive(owner, tmp_path):
    path = exported(owner, tmp_path)
    capture_id = owner.local_research_evidence_report('alpha')['hits'][0]['capture_id']
    owner.archive_offline_research(capture_id)
    result = owner.inspect_local_research_evidence_export(path)
    assert result['checksum_matches'] is True
    assert result['local_report_matches'] is False
    assert result['matching_scope'] is None


def test_export_stale_after_new_matching_capture(owner, tmp_path):
    path = exported(owner, tmp_path)
    owner.add_offline_research('https://example.org/new', 'New', 'alpha more')
    assert not owner.inspect_local_research_evidence_export(path)['local_report_matches']


def test_export_mismatch_in_another_database(owner, tmp_path):
    path = exported(owner, tmp_path)
    other = LocalStore(tmp_path / 'other.sqlite3')
    other.setup_owner('other-owner', 'other-owner-password-2026')
    assert not other.inspect_local_research_evidence_export(path)['local_report_matches']


def test_checksum_tampering_rejected(owner, tmp_path):
    path = exported(owner, tmp_path)
    envelope = json.loads(path.read_bytes())
    envelope['report']['hits'][0]['title'] = 'FAKE'
    path.write_text(json.dumps(envelope), encoding='utf-8')
    with pytest.raises(ValueError, match='체크섬'):
        owner.inspect_local_research_evidence_export(path)


def test_auth_required_before_opening_path(owner, tmp_path):
    path = exported(owner, tmp_path)
    owner.logout()
    with pytest.raises((AuthenticationError, PermissionError)):
        owner.inspect_local_research_evidence_export(path)
    with pytest.raises((AuthenticationError, PermissionError)):
        owner.inspect_local_research_evidence_export(tmp_path / 'not-existing.json')


def test_invalid_paths_and_non_regular_files(owner, tmp_path):
    for path in ('', ' ', None, 42):
        with pytest.raises(ValueError):
            owner.inspect_local_research_evidence_export(path)
    with pytest.raises(FileNotFoundError):
        owner.inspect_local_research_evidence_export(tmp_path / 'missing.json')
    with pytest.raises(ValueError, match='일반'):
        owner.inspect_local_research_evidence_export(tmp_path)
    target = exported(owner, tmp_path)
    link = tmp_path / 'link.json'
    try:
        link.symlink_to(target)
    except (OSError, NotImplementedError):
        pytest.skip('symlink unsupported')
    with pytest.raises(ValueError, match='일반'):
        owner.inspect_local_research_evidence_export(link)


def test_empty_and_oversized_files(owner, tmp_path):
    path = tmp_path / 'invalid.json'
    path.write_bytes(b'')
    with pytest.raises(ValueError, match='크기'):
        owner.inspect_local_research_evidence_export(path)
    path.write_bytes(b'0' * (MAX_EXPORT_BYTES + 1))
    with pytest.raises(ValueError, match='크기'):
        owner.inspect_local_research_evidence_export(path)


def test_read_only_and_restart(owner, tmp_path):
    path = exported(owner, tmp_path)
    with sqlite3.connect(owner.path) as con:
        before = list(con.iterdump())
    original = path.read_bytes()
    assert owner.inspect_local_research_evidence_export(path)['local_report_matches']
    with sqlite3.connect(owner.path) as con:
        assert list(con.iterdump()) == before
    assert path.read_bytes() == original
    owner.logout()
    resumed = LocalStore(owner.path)
    resumed.login('verify-owner', 'verify-owner-password-2026')
    assert resumed.inspect_local_research_evidence_export(path)['local_report_matches']


def test_socket_blocked(owner, tmp_path, monkeypatch):
    path = exported(owner, tmp_path)
    def deny(*args, **kwargs):
        raise AssertionError('outbound socket forbidden')
    monkeypatch.setattr(socket.socket, 'connect', deny)
    monkeypatch.setattr(socket.socket, 'connect_ex', deny)
    monkeypatch.setattr(socket, 'create_connection', deny)
    assert owner.inspect_local_research_evidence_export(path)['network_accessed'] is False
