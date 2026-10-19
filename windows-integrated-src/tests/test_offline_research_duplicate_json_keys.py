"""Stage54: never reinterpret ambiguous local evidence JSON by last-key-wins."""
import json
import socket
from unittest.mock import patch

import pytest

from desktop.research_bundle_manifest import _receipt_digest
from desktop.storage import LocalStore


@pytest.fixture
def offline_bundle(tmp_path):
    store = LocalStore(tmp_path / 'company.sqlite3')
    store.setup_owner('owner', 'offline-json-key-password')
    (tmp_path / 'evidence.txt').write_text('Local evidence body', encoding='utf-8')
    manifest = tmp_path / 'bundle.json'
    store.create_offline_research_bundle_manifest([
        (tmp_path / 'evidence.txt', 'https://example.org/original', 'Original')
    ], manifest)
    return store, manifest, tmp_path / 'receipt.json'


@pytest.mark.parametrize('where', ['root_format', 'root_items', 'item_url', 'item_file', 'item_title'])
def test_manifest_rejects_duplicate_keys_before_preview_or_import(offline_bundle, where):
    store, manifest, _receipt = offline_bundle
    original = store.path.read_bytes()
    document = manifest.read_text(encoding='utf-8')
    if where == 'root_format':
        document = document.replace('"format":', '"format": "fake", "format":', 1)
    elif where == 'root_items':
        document = document.replace('"items":', '"items": [], "items":', 1)
    else:
        key = where.removeprefix('item_')
        document = document.replace('"' + key + '":', '"' + key + '": "decoy", "' + key + '":', 1)
    manifest.write_text(document, encoding='utf-8')
    with pytest.raises(ValueError, match='중복된 키'):
        store.preview_offline_research_bundle(manifest)
    with pytest.raises(ValueError, match='중복된 키'):
        store.import_offline_research_bundle(manifest)
    assert not store.search_offline_research()
    assert store.path.read_bytes() == original


@pytest.mark.parametrize('where', ['root_sha', 'root_items', 'item_file', 'item_size'])
def test_receipt_rejects_duplicate_keys_even_with_recomputed_checksum(offline_bundle, where):
    store, manifest, receipt = offline_bundle
    store.create_offline_research_bundle_receipt(manifest, receipt)
    baseline = store.path.read_bytes()
    payload = json.loads(receipt.read_text(encoding='utf-8'))
    # Build a valid checksum for the ordinary last-key-wins interpretation,
    # proving that a matching self-checksum alone cannot detect duplicate keys.
    base = {k: v for k, v in payload.items() if k != 'receipt_sha256'}
    payload['receipt_sha256'] = _receipt_digest(base)
    raw = json.dumps(payload, ensure_ascii=False)
    if where == 'root_sha':
        raw = raw.replace('"manifest_sha256":', '"manifest_sha256": "decoy", "manifest_sha256":', 1)
    elif where == 'root_items':
        raw = raw.replace('"items":', '"items": [], "items":', 1)
    elif where == 'item_file':
        raw = raw.replace('"file":', '"file": "decoy", "file":', 1)
    else:
        raw = raw.replace('"raw_size":', '"raw_size": 999, "raw_size":', 1)
    receipt.write_text(raw, encoding='utf-8')
    with pytest.raises(ValueError, match='중복된 키'):
        store.verify_offline_research_bundle_receipt(receipt)
    assert store.path.read_bytes() == baseline


def test_valid_manifest_and_receipt_still_roundtrip_without_network(offline_bundle):
    store, manifest, receipt = offline_bundle
    original = store.path.read_bytes()
    def deny(*args, **kwargs):
        raise AssertionError('Network access not allowed')
    with patch.object(socket.socket, 'connect', deny), patch.object(socket.socket, 'sendto', deny), \
         patch.object(socket, 'getaddrinfo', deny):
        assert store.preview_offline_research_bundle(manifest)['importable']
        store.create_offline_research_bundle_receipt(manifest, receipt)
        assert store.verify_offline_research_bundle_receipt(receipt)['passed']
    assert store.path.read_bytes() == original
