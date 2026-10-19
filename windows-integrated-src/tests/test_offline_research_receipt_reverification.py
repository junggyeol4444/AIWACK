"""Stage54: a custody recheck must not pass stale early-file reads."""
from unittest.mock import patch
import socket

import pytest

from desktop.storage import LocalStore
import desktop.research_bundle_manifest as bundle


@pytest.fixture
def sample(tmp_path):
    store = LocalStore(tmp_path / 'company.sqlite')
    store.setup_owner('owner', 'owner-recheck-password')
    first = tmp_path / 'a.txt'
    second = tmp_path / 'b.txt'
    first.write_text('Source A', encoding='utf-8')
    second.write_text('Source B', encoding='utf-8')
    manifest = tmp_path / 'sources.json'
    receipt = tmp_path / 'custody.json'
    store.create_offline_research_bundle_manifest([
        (first, 'https://example.org/a', 'One'),
        (second, 'https://example.org/b', 'Two'),
    ], manifest)
    store.create_offline_research_bundle_receipt(manifest, receipt)
    return store, first, second, manifest, receipt


def test_stable_receipt_returns_existing_match_status(sample):
    store, _first, _second, _manifest, receipt = sample
    before = store.path.read_bytes()
    result = store.verify_offline_research_bundle_receipt(receipt)
    assert result['passed'] is True
    assert result['changed_during_check'] is False
    assert result['counts'] == {'match': 2, 'changed': 0, 'unavailable': 0}
    assert store.path.read_bytes() == before


def test_early_file_mutated_after_second_file_read_cannot_pass(sample, monkeypatch):
    store, first, _second, _manifest, receipt = sample
    reader = bundle.read_local_snapshot
    seen = {'n': 0}
    before = store.path.read_bytes()

    def changing_reader(path):
        found = reader(path)
        seen['n'] += 1
        if seen['n'] == 2:  # a.txt was already read as matching
            first.write_text('Altered while verifying', encoding='utf-8')
        return found

    monkeypatch.setattr(bundle, 'read_local_snapshot', changing_reader)
    result = store.verify_offline_research_bundle_receipt(receipt)
    assert seen['n'] == 4
    assert result['passed'] is False
    assert result['changed_during_check'] is True
    assert result['items'][0]['status'] == 'changed'
    assert result['counts'] == {'match': 1, 'changed': 1, 'unavailable': 0}
    assert store.path.read_bytes() == before


def test_manifest_changed_during_source_reads_cannot_pass(sample, monkeypatch):
    store, _first, _second, manifest, receipt = sample
    reader = bundle.read_local_snapshot
    calls = {'n': 0}

    def rewrite_manifest(path):
        result = reader(path)
        calls['n'] += 1
        if calls['n'] == 1:
            manifest.write_bytes(manifest.read_bytes() + b' ')
        return result

    monkeypatch.setattr(bundle, 'read_local_snapshot', rewrite_manifest)
    result = store.verify_offline_research_bundle_receipt(receipt)
    assert not result['passed'] and result['changed_during_check']
    assert result['manifest_status'] == 'changed'
    assert result['counts']['match'] == 2


def test_source_removed_between_verification_passes_is_unavailable(sample, monkeypatch):
    store, first, _second, _manifest, receipt = sample
    reader = bundle.read_local_snapshot
    calls = {'n': 0}

    def delete_early_file(path):
        result = reader(path)
        calls['n'] += 1
        if calls['n'] == 2:
            first.unlink()
        return result

    monkeypatch.setattr(bundle, 'read_local_snapshot', delete_early_file)
    result = store.verify_offline_research_bundle_receipt(receipt)
    assert result['changed_during_check'] and not result['passed']
    assert result['items'][0]['status'] == 'unavailable'
    assert result['counts']['unavailable'] == 1


def test_previous_static_drift_is_not_mistaken_for_midcheck_change(sample):
    store, first, _second, _manifest, receipt = sample
    first.write_text('Prior edit', encoding='utf-8')
    result = store.verify_offline_research_bundle_receipt(receipt)
    assert not result['passed']
    assert not result['changed_during_check']
    assert result['items'][0]['status'] == 'changed'


def test_no_network_in_reverification(sample):
    store, *_unused, receipt = sample
    def deny(*args, **kwargs):
        raise AssertionError('No network allowed')
    with patch.object(socket.socket, 'connect', deny), \
         patch.object(socket.socket, 'sendto', deny), \
         patch.object(socket, 'getaddrinfo', deny):
        assert store.verify_offline_research_bundle_receipt(receipt)['passed']
