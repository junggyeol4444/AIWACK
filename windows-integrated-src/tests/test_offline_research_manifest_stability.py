"""Stage54: do not persist a manifest assembled from changing local files."""
from pathlib import Path
from unittest.mock import patch
import socket

import pytest

import desktop.research_bundle_manifest as module
from desktop.storage import LocalStore


@pytest.fixture
def prepared(tmp_path):
    store = LocalStore(tmp_path / 'company.sqlite3')
    store.setup_owner('owner', 'offline-manifest-stability-password')
    first, second = tmp_path / 'a.txt', tmp_path / 'b.txt'
    first.write_text('Source A', encoding='utf-8')
    second.write_text('Source B', encoding='utf-8')
    entries = [(first, 'https://example.org/a', 'A'),
               (second, 'https://example.org/b', 'B')]
    return store, first, second, entries, tmp_path / 'bundle.json'


def test_stable_files_are_rechecked_and_no_db_write(prepared, monkeypatch):
    store, first, second, entries, target = prepared
    before = store.path.read_bytes()
    original = module.read_local_snapshot
    observed = []

    def tracked(path):
        observed.append(Path(path).name)
        return original(path)

    monkeypatch.setattr(module, 'read_local_snapshot', tracked)
    result = store.create_offline_research_bundle_manifest(entries, target)
    assert result['item_count'] == 2
    assert observed == ['a.txt', 'b.txt', 'a.txt', 'b.txt']
    assert result['input_files'][0]['raw_sha256'] == original(first)[3]
    assert result['network_accessed'] is False and result['database_modified'] is False
    assert store.path.read_bytes() == before
    assert store.preview_offline_research_bundle(target)['importable']


def test_early_file_changed_while_later_file_read_refuses_creation(prepared, monkeypatch):
    store, first, second, entries, target = prepared
    before = store.path.read_bytes()
    original = module.read_local_snapshot
    calls = {'n': 0}

    def mutate_first(path):
        snapshot = original(path)
        calls['n'] += 1
        if calls['n'] == 2:
            first.write_text('Source A edited during scan', encoding='utf-8')
        return snapshot

    monkeypatch.setattr(module, 'read_local_snapshot', mutate_first)
    with pytest.raises(ValueError, match='자료 파일이 변경'):
        store.create_offline_research_bundle_manifest(entries, target)
    assert calls['n'] >= 3
    assert not target.exists()
    assert store.path.read_bytes() == before


def test_early_file_deleted_while_later_file_read_refuses_creation(prepared, monkeypatch):
    store, first, second, entries, target = prepared
    original = module.read_local_snapshot
    calls = {'n': 0}

    def delete_early(path):
        snapshot = original(path)
        calls['n'] += 1
        if calls['n'] == 2:
            first.unlink()
        return snapshot

    monkeypatch.setattr(module, 'read_local_snapshot', delete_early)
    with pytest.raises(ValueError, match='재확인할 수 없습니다'):
        store.create_offline_research_bundle_manifest(entries, target)
    assert not target.exists()


def test_symlink_replacement_during_collection_rejected(prepared, monkeypatch):
    store, first, second, entries, target = prepared
    fake = first.parent / 'other.txt'
    fake.write_text('Replacement', encoding='utf-8')
    probe = first.parent / 'probe-link'
    try:
        probe.symlink_to(fake)
    except (NotImplementedError, OSError):
        pytest.skip('symlinks unavailable')
    probe.unlink()
    original = module.read_local_snapshot
    calls = {'n': 0}

    def link_early(path):
        snapshot = original(path)
        calls['n'] += 1
        if calls['n'] == 2:
            first.unlink()
            first.symlink_to(fake)
        return snapshot

    monkeypatch.setattr(module, 'read_local_snapshot', link_early)
    with pytest.raises(ValueError, match='재확인할 수 없습니다'):
        store.create_offline_research_bundle_manifest(entries, target)
    assert not target.exists()


def test_no_overwrite_or_network_on_recheck(prepared):
    store, first, second, entries, target = prepared
    target.write_text('existing', encoding='utf-8')
    def deny(*args, **kwargs):
        raise AssertionError('network forbidden')
    with patch.object(socket.socket, 'connect', deny), patch.object(socket.socket, 'sendto', deny), \
         patch.object(socket, 'getaddrinfo', deny):
        with pytest.raises(ValueError, match='덮어쓰지'):
            store.create_offline_research_bundle_manifest(entries, target)
    assert target.read_text(encoding='utf-8') == 'existing'
