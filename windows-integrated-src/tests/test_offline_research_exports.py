"""Stage54 local evidence JSON export: explicit opt-in, no network, no DB writes."""
import json
import socket
import sqlite3

import pytest

from desktop.storage import AuthenticationError, LocalStore
from desktop.research_exports import (
    EXPORT_FORMAT, encode_evidence_export, save_evidence_export, verify_evidence_export,
)


@pytest.fixture
def owner(tmp_path):
    store = LocalStore(tmp_path / 'owner.sqlite3')
    store.setup_owner('export-owner', 'export-owner-password-2026')
    store.add_offline_research('https://example.org/paper', '로컬 제목',
                               'first line\n한국어 근거 alpha')
    return store


def test_deterministic_utf8_export_and_round_trip(owner):
    report = owner.local_research_evidence_report('한국어')
    a, b = encode_evidence_export(report), encode_evidence_export(report)
    assert a == b and '한국어'.encode() in a
    envelope = json.loads(a)
    assert envelope['format'] == EXPORT_FORMAT
    assert verify_evidence_export(a) == report
    assert envelope['source_authenticity'].startswith('unverified')
    assert envelope['report']['hits'][0]['excerpts'][0]['line'] == 2


def test_export_is_explicit_and_survives_restart(owner, tmp_path):
    destination = tmp_path / 'citation.json'
    result = owner.export_local_research_evidence('근거', destination)
    assert result == destination and destination.is_file()
    owner.logout()
    restored = LocalStore(owner.path)
    restored.login('export-owner', 'export-owner-password-2026')
    assert verify_evidence_export(destination.read_bytes()) == restored.local_research_evidence_report('근거')


def test_existing_file_is_never_overwritten(owner, tmp_path):
    destination = tmp_path / 'existing.json'
    destination.write_text('KEEP ME', encoding='utf-8')
    with pytest.raises(FileExistsError):
        owner.export_local_research_evidence('근거', destination)
    assert destination.read_text(encoding='utf-8') == 'KEEP ME'


def test_existing_symlink_is_not_followed(owner, tmp_path):
    target = tmp_path / 'target.json'
    target.write_text('UNCHANGED', encoding='utf-8')
    link = tmp_path / 'link.json'
    try:
        link.symlink_to(target)
    except (OSError, NotImplementedError):
        pytest.skip('symlink creation not permitted on this host')
    with pytest.raises(FileExistsError):
        owner.export_local_research_evidence('근거', link)
    assert target.read_text(encoding='utf-8') == 'UNCHANGED'


def test_tampering_report_fails_checksum(owner):
    raw = encode_evidence_export(owner.local_research_evidence_report('근거'))
    envelope = json.loads(raw)
    envelope['report']['hits'][0]['excerpts'][0]['text'] = 'invented'
    with pytest.raises(ValueError, match='체크섬'):
        verify_evidence_export(json.dumps(envelope).encode())


def test_invalid_format_and_flags_rejected(owner):
    report = owner.local_research_evidence_report('근거')
    for value in ({}, {'hits': [], 'network_accessed': True,
                       'source_authenticity_verified': False, 'report_text': '', 'query': 'x'}):
        with pytest.raises(ValueError):
            encode_evidence_export(value)
    raw = encode_evidence_export(report)
    envelope = json.loads(raw)
    envelope['format'] = 'unknown'
    with pytest.raises(ValueError):
        verify_evidence_export(json.dumps(envelope).encode())
    envelope = json.loads(raw)
    envelope['source_authenticity'] = 'verified'
    with pytest.raises(ValueError):
        verify_evidence_export(json.dumps(envelope).encode())
    with pytest.raises(ValueError):
        verify_evidence_export(b'not json')


def test_auth_required_even_for_export(owner, tmp_path):
    destination = tmp_path / 'private.json'
    owner.logout()
    with pytest.raises(AuthenticationError):
        owner.export_local_research_evidence('근거', destination)
    assert not destination.exists()


def test_export_does_not_modify_sqlite(owner, tmp_path):
    with sqlite3.connect(owner.path) as con:
        before = list(con.iterdump())
    owner.export_local_research_evidence('근거', tmp_path / 'evidence.json')
    with sqlite3.connect(owner.path) as con:
        assert list(con.iterdump()) == before


def test_cancelled_or_invalid_destination(owner, tmp_path):
    report = owner.local_research_evidence_report('근거')
    for path in ('', '  ', None, 5):
        with pytest.raises(ValueError):
            save_evidence_export(report, path)
    with pytest.raises(FileNotFoundError):
        owner.export_local_research_evidence('근거', tmp_path / 'not-created' / 'x.json')


def test_archived_filter_and_no_match_are_explicit(owner, tmp_path):
    report = owner.local_research_evidence_report('nonexistent')
    assert not verify_evidence_export(encode_evidence_export(report))['hits']
    capture_id = owner.local_research_evidence_report('근거')['hits'][0]['capture_id']
    owner.archive_offline_research(capture_id)
    destination = tmp_path / 'archived.json'
    owner.export_local_research_evidence('근거', destination, include_archived=True)
    exported = verify_evidence_export(destination.read_bytes())
    assert exported['hits'][0]['archived'] is True
    assert exported['source_authenticity_verified'] is False


def test_network_forbidden(owner, tmp_path, monkeypatch):
    def deny(*args, **kwargs):
        raise AssertionError('outbound socket forbidden')
    monkeypatch.setattr(socket.socket, 'connect', deny)
    monkeypatch.setattr(socket.socket, 'connect_ex', deny)
    monkeypatch.setattr(socket, 'create_connection', deny)
    dest = tmp_path / 'offline.json'
    owner.export_local_research_evidence('근거', dest)
    assert verify_evidence_export(dest.read_bytes())['network_accessed'] is False
