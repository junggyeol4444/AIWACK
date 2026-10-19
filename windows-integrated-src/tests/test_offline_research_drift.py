"""Stage54: bounded local report drift hints, without claiming provenance."""
import json
import os
import socket
import sqlite3
from pathlib import Path

import pytest

from desktop.storage import LocalStore, AuthenticationError
from desktop.research_exports import encode_evidence_export
from desktop.research_verification import _candidate_difference, _read_local_json


@pytest.fixture
def owner(tmp_path):
    store = LocalStore(tmp_path / 'local.sqlite3')
    store.setup_owner('drift-owner', 'drift-owner-password-2026')
    return store


def test_new_capture_is_reported_without_guessing_cause(owner, tmp_path):
    first = owner.add_offline_research('https://example.org/first', 'First', 'needle first')
    path = tmp_path / 'report.json'
    owner.export_local_research_evidence('needle', path)
    second = owner.add_offline_research('https://example.org/second', 'Second', 'needle second')
    result = owner.inspect_local_research_evidence_export(path)
    diff = result['candidate_difference']
    assert not result['local_report_matches']
    assert diff['added_capture_ids'] == [second]
    assert diff['missing_capture_ids'] == []
    assert diff['changed_capture_ids'] == []
    assert diff['unchanged_hit_count'] == 1
    assert diff['is_causal_explanation'] is False
    assert result['source_authenticity_verified'] is False


def test_archive_change_shows_candidate_differences(owner, tmp_path):
    first = owner.add_offline_research('https://example.org/first', 'First', 'needle first')
    path = tmp_path / 'report.json'
    owner.export_local_research_evidence('needle', path)
    owner.archive_offline_research(first)
    result = owner.inspect_local_research_evidence_export(path)
    assert not result['local_report_matches']
    diff = result['candidate_difference']
    assert diff['compared_scope'] in ('active', 'including_archived')
    assert first in diff['missing_capture_ids'] or first in diff['changed_capture_ids']
    assert not diff['is_causal_explanation']


def test_identical_reports_have_no_candidate_diff(owner, tmp_path):
    owner.add_offline_research('https://example.org/a', 'First', 'needle first')
    path = tmp_path / 'report.json'
    owner.export_local_research_evidence('needle', path)
    result = owner.inspect_local_research_evidence_export(path)
    assert result['local_report_matches']
    assert result['candidate_difference'] is None


def test_missing_capture_in_other_db(owner, tmp_path):
    owner.add_offline_research('https://example.org/a', 'First', 'needle first')
    path = tmp_path / 'report.json'
    owner.export_local_research_evidence('needle', path)
    other = LocalStore(tmp_path / 'other.sqlite3')
    other.setup_owner('other-owner', 'other-owner-password-2026')
    diff = other.inspect_local_research_evidence_export(path)['candidate_difference']
    assert diff['missing_capture_ids'] == [1]
    assert diff['added_capture_ids'] == []


def test_changed_same_id_and_order_only_are_not_conflated():
    first = {'query': 'a', 'hits': [{'capture_id': 1, 'title': 'A'}], 'report_text': 'one'}
    modified = {'query': 'a', 'hits': [{'capture_id': 1, 'title': 'B'}], 'report_text': 'one'}
    assert _candidate_difference(first, modified, 'active')['changed_capture_ids'] == [1]
    assert not _candidate_difference(first, modified, 'active')['report_metadata_or_order_differs']
    text_only = {'query': 'a', 'hits': first['hits'], 'report_text': 'two'}
    assert _candidate_difference(first, text_only, 'active')['report_metadata_or_order_differs']


def test_invalid_duplicate_and_oversized_hit_ids_rejected(owner, tmp_path):
    report = owner.local_research_evidence_report('needle')
    report['hits'] = [{'capture_id': 1}, {'capture_id': 1}]
    path = tmp_path / 'invalid.json'
    path.write_bytes(encode_evidence_export(report))
    with pytest.raises(ValueError, match='중복'):
        owner.inspect_local_research_evidence_export(path)
    report['hits'] = [{'capture_id': 1.0}]
    path.write_bytes(encode_evidence_export(report))
    with pytest.raises(ValueError, match='ID'):
        owner.inspect_local_research_evidence_export(path)


def test_relative_and_unc_paths_rejected_before_io(owner):
    for path in ('relative.json', r'\\server\share\report.json', '//server/share/report.json'):
        with pytest.raises(ValueError):
            owner.inspect_local_research_evidence_export(path)


def test_directory_and_symlink_refused(owner, tmp_path):
    with pytest.raises(ValueError, match='일반'):
        owner.inspect_local_research_evidence_export(tmp_path)
    path = tmp_path / 'regular.json'
    path.write_bytes(encode_evidence_export(owner.local_research_evidence_report('needle')))
    link = tmp_path / 'link.json'
    try:
        link.symlink_to(path)
    except (OSError, NotImplementedError):
        pytest.skip('symlink unavailable')
    with pytest.raises(ValueError, match='일반'):
        owner.inspect_local_research_evidence_export(link)


def test_no_network_or_database_writes(owner, tmp_path, monkeypatch):
    owner.add_offline_research('https://example.org/a', 'First', 'needle first')
    path = tmp_path / 'report.json'
    owner.export_local_research_evidence('needle', path)
    owner.add_offline_research('https://example.org/b', 'Second', 'needle second')
    with sqlite3.connect(owner.path) as con:
        before = list(con.iterdump())
    raw = path.read_bytes()
    def deny(*args, **kwargs):
        raise AssertionError('network call prohibited')
    monkeypatch.setattr(socket.socket, 'connect', deny)
    monkeypatch.setattr(socket.socket, 'connect_ex', deny)
    monkeypatch.setattr(socket, 'create_connection', deny)
    assert owner.inspect_local_research_evidence_export(path)['candidate_difference']
    with sqlite3.connect(owner.path) as con:
        assert list(con.iterdump()) == before
    assert path.read_bytes() == raw


def test_auth_before_path_probe(owner, tmp_path):
    owner.logout()
    with pytest.raises((AuthenticationError, PermissionError)):
        owner.inspect_local_research_evidence_export(tmp_path / 'not_here.json')


def test_bounded_20_hits(owner, tmp_path):
    for n in range(24):
        owner.add_offline_research(f'https://example.org/{n}', str(n), 'needle')
    path = tmp_path / 'report.json'
    owner.export_local_research_evidence('needle', path)
    owner.add_offline_research('https://example.org/new', 'New', 'needle')
    diff = owner.inspect_local_research_evidence_export(path)['candidate_difference']
    assert len(diff['added_capture_ids']) <= 20
    assert len(diff['missing_capture_ids']) <= 20
    assert len(diff['changed_capture_ids']) <= 20
    assert diff['is_causal_explanation'] is False

@pytest.mark.skipif(os.name == 'nt' or not hasattr(os, 'O_NOFOLLOW'),
                    reason='POSIX O_NOFOLLOW only')
def test_symlink_swap_between_lstat_and_open_is_refused(owner, tmp_path, monkeypatch):
    path = tmp_path / 'report.json'
    original = encode_evidence_export(owner.local_research_evidence_report('needle'))
    path.write_bytes(original)
    other = tmp_path / 'other.json'
    other.write_bytes(original)
    real_open = os.open

    def swap_then_open(filename, flags, *args, **kwargs):
        if Path(filename) == path:
            path.unlink()
            path.symlink_to(other)
        return real_open(filename, flags, *args, **kwargs)

    monkeypatch.setattr('desktop.research_verification.os.open', swap_then_open)
    with pytest.raises(ValueError, match='일반'):
        owner.inspect_local_research_evidence_export(path)
