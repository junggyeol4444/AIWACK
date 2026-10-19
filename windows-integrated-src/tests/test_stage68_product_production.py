"""Stage68 offline artifact prototype: no model, network, code execution or release."""
import hashlib
from pathlib import Path
import socket
import sqlite3
from unittest.mock import patch

import pytest

from desktop.storage import LocalStore
from desktop.product_production import render_static_preview, artifact_directory


@pytest.fixture
def store(tmp_path):
    s = LocalStore(tmp_path / 'owner.sqlite3')
    s.setup_owner('owner68', 'stage68-long-password')
    return s


def catalog(store, kind='product', name='로컬 초안', description='고객 가정'):
    b = store.create_business(1, '사업', '목표')
    return store.create_catalog_item(b, kind, name, description, 1234, '제공 계획')


def test_create_real_local_html_and_hash(store):
    c = catalog(store)
    p = store.create_product_prototype(c)
    item = store.product_prototype(p)
    data = Path(item['artifact_path']).read_bytes()
    assert data.startswith(b'<!doctype html>')
    assert hashlib.sha256(data).hexdigest() == item['sha256']
    assert len(data) == item['byte_count']
    assert '로컬 초안'.encode() in data
    assert item['catalog_version'] == 1
    assert item['created_by_ai'] is False
    assert item['release_approved'] is False
    assert item['external_actions_executed'] is False
    assert item['state'] == 'prototype'
    assert len(store.product_prototype_events(p)) == 1
    assert len(store.product_prototypes()) == 1
    assert artifact_directory(store.path) == Path(item['artifact_path']).parent


def test_escape_untrusted_text_and_block_resources(store):
    c = catalog(store, name='<script>alert(1)</script>',
                description='"<img src=https://example.invalid/x onerror=alert(1)>')
    p = store.create_product_prototype(c)
    html = Path(store.product_prototype(p)['artifact_path']).read_text('utf-8')
    assert '<script>' not in html
    assert '<img' not in html
    assert '&lt;script&gt;' in html
    assert '&lt;img' in html
    assert "default-src 'none'" in html
    assert 'AI 제작 아님' in html


def test_review_only_and_no_release(store):
    c = catalog(store)
    p = store.create_product_prototype(c)
    assert store.set_product_prototype_state(p, 'review_requested')['state'] == 'review_requested'
    with pytest.raises(ValueError): store.set_product_prototype_state(p, 'released')
    with pytest.raises(ValueError): store.set_product_prototype_state(p, 'prototype')
    assert store.set_product_prototype_state(p, 'withdrawn')['state'] == 'withdrawn'
    with pytest.raises(ValueError): store.set_product_prototype_state(p, 'review_requested')
    assert [e['action'] for e in store.product_prototype_events(p)] == [
        'created', 'state_changed', 'state_changed']


def test_catalog_version_change_marks_old_preview_stale(store):
    c = catalog(store)
    p = store.create_product_prototype(c)
    store.revise_catalog_item(c, '새 설명', 5000, '새 계획')
    assert store.product_prototype(p)['catalog_changed_since_build'] is True
    with pytest.raises(ValueError, match='카탈로그 변경'):
        store.set_product_prototype_state(p, 'review_requested')
    p2 = store.create_product_prototype(c)
    assert store.product_prototype(p2)['catalog_version'] == 2
    assert store.product_prototype(p2)['catalog_changed_since_build'] is False
    assert store.product_prototype(p)['sha256'] != store.product_prototype(p2)['sha256']


def test_file_tamper_size_and_hash(store):
    p = store.create_product_prototype(catalog(store))
    target = Path(store.product_prototype(p)['artifact_path'])
    original = target.read_bytes()
    target.write_bytes(original.replace(b'<!doctype html>', b'<!DOCTYPE html>'))
    with pytest.raises(ValueError, match='해시'):
        store.product_prototype(p)
    target.write_bytes(b'tampered')
    with pytest.raises(ValueError, match='크기'):
        store.product_prototype(p)
    target.unlink()
    with pytest.raises(ValueError, match='없거나'):
        store.product_prototype(p)


def test_symlink_rejected(store, tmp_path):
    p = store.create_product_prototype(catalog(store))
    target = Path(store.product_prototype(p)['artifact_path'])
    original = target.read_bytes()
    backup = tmp_path / 'backup.html'
    backup.write_bytes(original)
    target.unlink()
    try:
        target.symlink_to(backup)
    except (OSError, NotImplementedError):
        pytest.skip('symlinks unavailable')
    with pytest.raises(ValueError, match='심볼릭'):
        store.product_prototype(p)


def test_database_audit_guards_and_tamper(store):
    p = store.create_product_prototype(catalog(store))
    with store._connect() as con:
        for sql in (
            'DELETE FROM local_product_prototypes',
            'DELETE FROM local_product_prototype_events',
            "UPDATE local_product_prototypes SET filename='bad'",
            "UPDATE local_product_prototype_events SET digest='bad'",
        ):
            with pytest.raises(sqlite3.DatabaseError):
                con.execute(sql)
        con.execute('DROP TRIGGER local_product_prototype_events_no_update')
        con.execute("UPDATE local_product_prototype_events SET snapshot_json='{}' WHERE prototype_id=?", (p,))
    with pytest.raises(ValueError, match='감사'):
        store.product_prototype(p)


def test_current_snapshot_tamper(store):
    p = store.create_product_prototype(catalog(store))
    with store._connect() as con:
        con.execute("UPDATE local_product_prototypes SET state='withdrawn' WHERE id=?", (p,))
    with pytest.raises(ValueError, match='불일치'):
        store.product_prototype(p)


def test_transaction_rollback_cleans_file(store):
    c = catalog(store)
    with store._connect() as con:
        con.execute('''CREATE TRIGGER fail68 BEFORE INSERT ON local_product_prototype_events
            BEGIN SELECT RAISE(ABORT,'forced'); END''')
    with pytest.raises(sqlite3.DatabaseError):
        store.create_product_prototype(c)
    assert list(artifact_directory(store.path).glob('*.html')) == []
    with store._connect() as con:
        assert con.execute('SELECT count(*) FROM local_product_prototypes').fetchone()[0] == 0


@pytest.mark.parametrize('bad', [0, -1, True, '1', None, 999999])
def test_invalid_catalog(store, bad):
    with pytest.raises(ValueError): store.create_product_prototype(bad)


@pytest.mark.parametrize('bad', ['published', 'approved', 'sold', '', 1, None])
def test_invalid_state(store, bad):
    p = store.create_product_prototype(catalog(store))
    with pytest.raises(ValueError): store.set_product_prototype_state(p, bad)


def test_archived_catalog_rejected(store):
    c = catalog(store)
    store.set_catalog_item_state(c, 'archived')
    with pytest.raises(ValueError, match='보관'):
        store.create_product_prototype(c)


def test_persistence_and_auth(store):
    c = catalog(store, kind='service')
    p = store.create_product_prototype(c)
    store.logout()
    for action in (lambda: store.create_product_prototype(c),
                   lambda: store.product_prototype(p),
                   lambda: store.product_prototypes(),
                   lambda: store.set_product_prototype_state(p, 'review_requested'),
                   lambda: store.product_prototype_events(p)):
        with pytest.raises(PermissionError): action()
    other = LocalStore(store.path)
    other.login('owner68', 'stage68-long-password')
    assert other.product_prototype(p)['id'] == p


def test_offline_socket_dns_blocked(store):
    def forbidden(*args, **kwargs):
        raise AssertionError('network forbidden')
    with patch.object(socket, 'socket', side_effect=forbidden), \
         patch.object(socket, 'getaddrinfo', side_effect=forbidden):
        p = store.create_product_prototype(catalog(store))
        store.set_product_prototype_state(p, 'review_requested')
        assert len(store.product_prototypes()) == 1
        assert len(store.product_prototype_events(p)) == 2


def test_invalid_limit(store):
    for value in (0, 201, True, '10'):
        with pytest.raises(ValueError): store.product_prototypes(limit=value)


def test_no_mutation_to_original_catalog(store):
    c = catalog(store)
    original = store.catalog_item(c)
    store.create_product_prototype(c)
    assert store.catalog_item(c) == original


def test_render_is_deterministic(store):
    c = catalog(store)
    item = store.catalog_item(c)
    assert render_static_preview(item) == render_static_preview(item)
