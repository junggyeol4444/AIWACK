"""Stage54: reject Windows-unportable bundle names even during Linux development."""
import json
import os
from pathlib import Path
import socket
from unittest.mock import patch

import pytest

from desktop.research_captures import _portable_bundle_filename
from desktop.storage import LocalStore


@pytest.fixture
def base(tmp_path):
    store = LocalStore(tmp_path / 'company.sqlite3')
    store.setup_owner('owner', 'offline-windows-name-password')
    source = tmp_path / 'report.txt'
    source.write_text('Local offline evidence', encoding='utf-8')
    return store, tmp_path, source


@pytest.mark.parametrize('filename', [
    'CON.txt', 'prn.HTML', 'AUX.md', 'nul.txt', 'com1.txt', 'LPT9.json',
    'COM¹.md', 'lpt³.txt', 'bad?.txt', 'bad|.txt', 'bad<.txt',
    'bad:.txt', 'bad".txt', 'bad\\name.txt', 'bad/name.txt',
    'trailing.', 'trailing ', 'control\x01.txt', '../outside.txt',
])
def test_portable_filename_rejects_windows_unsafe_names(filename):
    with pytest.raises(ValueError):
        _portable_bundle_filename(filename)


@pytest.mark.parametrize('filename', ['보고서.TXT', 'résumé.md', 'a-b_1.html'])
def test_portable_name_preserves_normal_unicode(filename):
    assert _portable_bundle_filename(filename) == filename.casefold()


def test_manifest_builder_rejects_reserved_source_without_write(base):
    store, folder, source = base
    if os.name == 'nt':
        pytest.skip('Windows cannot create DOS device filenames')
    reserved = folder / 'CON.txt'
    reserved.write_text('Data', encoding='utf-8')
    baseline = store.path.read_bytes()
    target = folder / 'bundle.json'
    with pytest.raises(ValueError, match='예약'):
        store.create_offline_research_bundle_manifest(
            [(reserved, 'https://example.org/evidence', 'Title')], target)
    assert not target.exists() and baseline == store.path.read_bytes()


def test_manifest_builder_rejects_windows_casefold_collision(base):
    store, folder, source = base
    if os.name == 'nt':
        pytest.skip('Windows case-insensitive filesystem cannot create both')
    upper = folder / 'REPORT.TXT'
    upper.write_text('Other evidence', encoding='utf-8')
    target = folder / 'bundle.json'
    baseline = store.path.read_bytes()
    with pytest.raises(ValueError, match='중복'):
        store.create_offline_research_bundle_manifest([
            (source, 'https://example.org/a', 'A'),
            (upper, 'https://example.org/b', 'B'),
        ], target)
    assert not target.exists() and baseline == store.path.read_bytes()


def test_manifest_builder_rejects_casefold_target_name(base):
    store, folder, source = base
    if os.name == 'nt':
        pytest.skip('Windows case-insensitive filesystem cannot create this pair')
    target = folder / 'REPORT.TXT'
    # Invalid .json destination when using a .txt entry; exercise collision via JSON file
    source_json = folder / 'BUNDLE.JSON'
    source_json.write_text('JSON content', encoding='utf-8')
    with pytest.raises(ValueError):
        store.create_offline_research_bundle_manifest([
            (source_json, 'https://example.org/a', 'A')], folder / 'bundle.json')
    assert not (folder / 'bundle.json').exists()


def _write_manifest(folder, names):
    target = folder / 'bundle.json'
    target.write_text(json.dumps({'format': 'aiwack-offline-research-bundle-v1', 'items': [
        {'file': name, 'url': 'https://example.org/a', 'title': 'Example'} for name in names
    ]}), encoding='utf-8')
    return target


def test_handwritten_manifest_rejects_casefold_aliases_before_read(base):
    store, folder, source = base
    target = _write_manifest(folder, ['report.txt', 'REPORT.TXT'])
    baseline = store.path.read_bytes()
    with pytest.raises(ValueError, match='중복'):
        store.preview_offline_research_bundle(target)
    assert store.path.read_bytes() == baseline


@pytest.mark.parametrize('name', ['CON.txt', 'bad?.txt', 'trailing.'])
def test_handwritten_manifest_rejects_unportable_names(base, name):
    store, folder, _ = base
    target = _write_manifest(folder, [name])
    baseline = store.path.read_bytes()
    with pytest.raises(ValueError):
        store.preview_offline_research_bundle(target)
    assert store.path.read_bytes() == baseline


def test_receipt_creation_rejects_manifest_alias_and_reserved_output(base):
    store, folder, source = base
    manifest = _write_manifest(folder, ['report.txt'])
    before = store.path.read_bytes()
    with pytest.raises(ValueError):
        store.create_offline_research_bundle_receipt(manifest, folder / 'BUNDLE.JSON')
    with pytest.raises(ValueError):
        store.create_offline_research_bundle_receipt(manifest, folder / 'CON.json')
    assert before == store.path.read_bytes()


def test_receipt_verify_rejects_casefold_duplicate_even_with_valid_digest(base):
    # A checksum by itself is not a signature: manually recomputing it should
    # not permit a receipt to smuggle two colliding source names through.
    import desktop.research_bundle_manifest as module
    store, folder, source = base
    manifest = _write_manifest(folder, ['report.txt'])
    receipt = folder / 'receipt.json'
    store.create_offline_research_bundle_receipt(manifest, receipt)
    payload = json.loads(receipt.read_text(encoding='utf-8'))
    duplicate = dict(payload['items'][0])
    duplicate['file'] = 'REPORT.TXT'
    payload['items'].append(duplicate)
    payload['receipt_sha256'] = module._receipt_digest({
        key: value for key, value in payload.items() if key != 'receipt_sha256'
    })
    receipt.write_text(json.dumps(payload), encoding='utf-8')
    with pytest.raises(ValueError, match='중복'):
        store.verify_offline_research_bundle_receipt(receipt)


def test_portable_path_still_works_with_network_disabled(base):
    store, folder, source = base
    before = store.path.read_bytes()
    def deny(*args, **kwargs):
        raise AssertionError('network forbidden')
    with patch.object(socket.socket, 'connect', deny), patch.object(socket.socket, 'sendto', deny), \
         patch.object(socket, 'getaddrinfo', deny):
        manifest = folder / 'bundle.json'
        store.create_offline_research_bundle_manifest([
            (source, 'https://example.org/a', 'Example')], manifest)
        assert store.preview_offline_research_bundle(manifest)['importable']
        receipt = folder / 'receipt.json'
        store.create_offline_research_bundle_receipt(manifest, receipt)
        assert store.verify_offline_research_bundle_receipt(receipt)['passed']
    assert store.path.read_bytes() == before
