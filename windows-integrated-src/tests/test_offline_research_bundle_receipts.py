"""Stage54: local-only pre-import bundle custody receipts."""
import hashlib
import json
import socket
from pathlib import Path
from unittest.mock import patch
import pytest
from desktop.storage import LocalStore, AuthenticationError


@pytest.fixture
def local(tmp_path):
    store=LocalStore(tmp_path/'company.sqlite')
    store.setup_owner('owner','owner-test-password')
    (tmp_path/'a.txt').write_text('Alpha evidence',encoding='utf-8')
    (tmp_path/'b.html').write_text('<p>Beta content</p>',encoding='utf-8')
    manifest=tmp_path/'bundle.json'
    store.create_offline_research_bundle_manifest([
        (tmp_path/'a.txt','https://example.org/a','Alpha'),
        (tmp_path/'b.html','https://example.org/b','Beta')],manifest)
    return store,tmp_path,manifest,tmp_path/'receipt.json'


def test_create_verify_roundtrip_no_db_change(local):
    store, folder, manifest, receipt=local
    original=store.path.read_bytes()
    created=store.create_offline_research_bundle_receipt(manifest,receipt)
    assert created['item_count']==2
    assert created['signed'] is False and created['web_source_verified'] is False
    doc=json.loads(receipt.read_text(encoding='utf-8'))
    assert set(doc)=={'format','manifest_filename','manifest_sha256','items','receipt_sha256'}
    assert doc['items'][0]['raw_sha256']==hashlib.sha256((folder/'a.txt').read_bytes()).hexdigest()
    assert 'example.org' not in receipt.read_text(encoding='utf-8')
    assert 'Alpha evidence' not in receipt.read_text(encoding='utf-8')
    result=store.verify_offline_research_bundle_receipt(receipt)
    assert result['passed'] and result['manifest_status']=='match'
    assert result['counts']=={'match':2,'changed':0,'unavailable':0}
    assert store.path.read_bytes()==original


def test_changed_file_and_missing_file(local):
    store,folder,manifest,receipt=local
    store.create_offline_research_bundle_receipt(manifest,receipt)
    (folder/'a.txt').write_text('Modified evidence',encoding='utf-8')
    (folder/'b.html').unlink()
    result=store.verify_offline_research_bundle_receipt(receipt)
    assert not result['passed']
    assert result['counts']=={'match':0,'changed':1,'unavailable':1}
    assert result['manifest_status']=='match'


def test_manifest_changed_or_missing(local):
    store,folder,manifest,receipt=local
    store.create_offline_research_bundle_receipt(manifest,receipt)
    manifest.write_text(manifest.read_text(encoding='utf-8')+' ', encoding='utf-8')
    assert store.verify_offline_research_bundle_receipt(receipt)['manifest_status']=='changed'
    manifest.unlink()
    assert store.verify_offline_research_bundle_receipt(receipt)['manifest_status']=='unavailable'


def test_tampering_rejected(local):
    store,folder,manifest,receipt=local
    store.create_offline_research_bundle_receipt(manifest,receipt)
    content=json.loads(receipt.read_text(encoding='utf-8'))
    content['items'][0]['raw_size']=10
    receipt.write_text(json.dumps(content),encoding='utf-8')
    with pytest.raises(ValueError, match='체크섬'):
        store.verify_offline_research_bundle_receipt(receipt)


def test_invalid_filename_even_with_recomputed_digest_rejected(local):
    store,folder,manifest,receipt=local
    store.create_offline_research_bundle_receipt(manifest,receipt)
    content=json.loads(receipt.read_text(encoding='utf-8'))
    content['items'][0]['file']='../../private.txt'
    receipt.write_text(json.dumps(content),encoding='utf-8')
    with pytest.raises(ValueError,match='잘못된 파일'):
        store.verify_offline_research_bundle_receipt(receipt)


def test_no_overwrite_or_remote_destination(local):
    store,folder,manifest,receipt=local
    receipt.write_text('do not overwrite',encoding='utf-8')
    with pytest.raises(ValueError,match='덮어쓰기'):
        store.create_offline_research_bundle_receipt(manifest,receipt)
    assert receipt.read_text()=='do not overwrite'
    with pytest.raises(ValueError):
        store.create_offline_research_bundle_receipt(manifest,'//somehost/share/receipt.json')
    with pytest.raises(ValueError):
        store.create_offline_research_bundle_receipt(manifest,folder/'elsewhere'/'receipt.json')


def test_file_change_during_creation_no_receipt(local):
    store,folder,manifest,receipt=local
    (folder/'b.html').write_bytes(b'')
    with pytest.raises(ValueError):
        store.create_offline_research_bundle_receipt(manifest,receipt)
    assert not receipt.exists()


def test_symlink_receipt_rejected(local):
    store,folder,manifest,receipt=local
    store.create_offline_research_bundle_receipt(manifest,receipt)
    fake=folder/'alias.json'
    try: fake.symlink_to(receipt)
    except (NotImplementedError,OSError):pytest.skip('symlink unavailable')
    with pytest.raises(ValueError,match='심볼릭'):
        store.verify_offline_research_bundle_receipt(fake)
    with pytest.raises(ValueError):
        store.create_offline_research_bundle_receipt(manifest,fake)


def test_logged_out_denied(local):
    store,folder,manifest,receipt=local
    store.logout()
    with pytest.raises((AuthenticationError,PermissionError)):
        store.create_offline_research_bundle_receipt(manifest,receipt)
    with pytest.raises((AuthenticationError,PermissionError)):
        store.verify_offline_research_bundle_receipt(receipt)
    assert not receipt.exists()


def test_network_disabled(local):
    store,folder,manifest,receipt=local
    def deny(*args,**kwargs):raise AssertionError('network forbidden')
    with patch.object(socket.socket,'connect',deny),patch.object(socket.socket,'sendto',deny),\
         patch.object(socket,'getaddrinfo',deny):
        store.create_offline_research_bundle_receipt(manifest,receipt)
        assert store.verify_offline_research_bundle_receipt(receipt)['passed']


def test_receipt_rejects_manifest_replacement_during_collection(local, monkeypatch):
    """Changes after the first manifest read must not create a receipt."""
    store, folder, manifest, receipt = local
    import desktop.research_bundle_manifest as module
    real_read = module.read_local_snapshot
    observed = {'calls': 0}
    original_db = store.path.read_bytes()

    def altering_reader(path):
        value = real_read(path)
        observed['calls'] += 1
        if observed['calls'] == 1:
            manifest.write_text(manifest.read_text(encoding='utf-8') + ' ', encoding='utf-8')
        return value

    monkeypatch.setattr(module, 'read_local_snapshot', altering_reader)
    with pytest.raises(ValueError, match='JSON 목록이 변경'):
        store.create_offline_research_bundle_receipt(manifest, receipt)
    assert not receipt.exists()
    assert store.path.read_bytes() == original_db


def test_receipt_rejects_first_file_changed_after_scanning_next(local, monkeypatch):
    """A previously scanned file cannot silently change during batch scan."""
    store, folder, manifest, receipt = local
    import desktop.research_bundle_manifest as module
    real_read = module.read_local_snapshot
    observed = {'calls': 0}

    def altering_reader(path):
        value = real_read(path)
        observed['calls'] += 1
        if observed['calls'] == 2:
            (folder / 'a.txt').write_text('Altered after initial fingerprint', encoding='utf-8')
        return value

    monkeypatch.setattr(module, 'read_local_snapshot', altering_reader)
    with pytest.raises(ValueError, match='자료 파일이 변경'):
        store.create_offline_research_bundle_receipt(manifest, receipt)
    assert observed['calls'] >= 3
    assert not receipt.exists()


def test_receipt_rejects_source_deleted_during_collection(local, monkeypatch):
    store, folder, manifest, receipt = local
    import desktop.research_bundle_manifest as module
    real_read = module.read_local_snapshot
    observed = {'calls': 0}

    def deleting_reader(path):
        value = real_read(path)
        observed['calls'] += 1
        if observed['calls'] == 2:
            (folder / 'a.txt').unlink()
        return value

    monkeypatch.setattr(module, 'read_local_snapshot', deleting_reader)
    with pytest.raises(ValueError, match='재확인할 수 없습니다'):
        store.create_offline_research_bundle_receipt(manifest, receipt)
    assert not receipt.exists()


def test_receipt_rechecks_unchanged_sources_before_writing(local, monkeypatch):
    store, folder, manifest, receipt = local
    import desktop.research_bundle_manifest as module
    real_read = module.read_local_snapshot
    counter = {'calls': 0}

    def count_reads(path):
        counter['calls'] += 1
        return real_read(path)

    monkeypatch.setattr(module, 'read_local_snapshot', count_reads)
    store.create_offline_research_bundle_receipt(manifest, receipt)
    assert counter['calls'] == 4  # two files, initial and final read
    assert store.verify_offline_research_bundle_receipt(receipt)['passed']
