"""Stage59: actual offline drafts and audit, never network delivery."""
import hashlib
import json
import sqlite3
import socket
from unittest.mock import patch

import pytest

from desktop.offline_service_integrations import available_contracts, validate_draft
from desktop.storage import LocalStore, AuthenticationError


def owner(tmp_path):
    store=LocalStore(tmp_path/'owner.sqlite3')
    store.setup_owner('owner59','stage59-owner-long-password')
    return store


def test_contracts_explicitly_disabled():
    specs=available_contracts()
    assert {x['key'] for x in specs} == {'email','post','service'}
    assert all(x['requires_owner_approval'] for x in specs)
    assert all(not x['connection_enabled'] and not x['dispatch_enabled'] and
               not x['credential_storage_enabled'] for x in specs)
    assert all(x['planned_permissions'] and x['planned_auth'] and x['recovery_policy']
               and x['planned_rate_limit_per_minute'] > 0 for x in specs)


@pytest.mark.parametrize('kind,target', [('email','writer@example.com'),('post','@company'),('service','inventory_check')])
def test_owner_local_draft_review_persists_without_network(tmp_path,kind,target):
    store=owner(tmp_path)
    def forbidden(*args,**kwargs):
        raise AssertionError('network operation forbidden')
    with patch.object(socket,'socket',side_effect=forbidden), patch.object(socket,'getaddrinfo',side_effect=forbidden):
        result=store.prepare_service_draft(kind,target,'Sample title','Body for local review')
        assert result['state']=='prepared' and result['transport_enabled'] is False
        assert store.service_draft_history()[0]['state']=='prepared'
        assert 'body' not in store.service_draft_history()[0]
        draft=store.service_draft_detail(result['id'])
        assert draft['sha256']==result['sha256']
        assert len(draft['events'])==1
        reviewed=store.review_service_draft(result['id'],True,'Local only')
        assert reviewed['state']=='reviewed_local_only'
        assert store.service_draft_detail(result['id'])['state']=='reviewed_local_only'
        with pytest.raises(ValueError):store.review_service_draft(result['id'],False)
    store.logout()
    reopened=LocalStore(tmp_path/'owner.sqlite3')
    reopened.login('owner59','stage59-owner-long-password')
    assert reopened.service_draft_history()[0]['state']=='reviewed_local_only'
    assert len(reopened.service_draft_detail(result['id'])['events'])==2


def test_cancelled_review_does_not_create_extra_event(tmp_path):
    store=owner(tmp_path)
    draft=store.prepare_service_draft('post','@company','A','Content')
    assert store.review_service_draft(draft['id'],False)['state']=='rejected'
    with pytest.raises(ValueError):store.review_service_draft(draft['id'],True)
    assert [e['action'] for e in store.service_draft_detail(draft['id'])['events']]==['prepared','rejected']


@pytest.mark.parametrize('kind,target,title,body', [
    ('unknown','a','title','body'), ('email','nope','title','body'),
    ('email','one@example.com\r\nBcc:bad@example.com','title','body'),
    ('email','x@bad..com','title','body'), ('post','https://example.com','title','body'),
    ('service','../../passwd','title','body'), ('post','@company','', 'body'),
    ('post','@company','title',''), ('post','@company','title','x'*5001),
    ('post','@company','title','Authorization: Bearer SECRET'),
    ('post','@company','title','password=abc'),
    ('post','@company','title','-----BEGIN PRIVATE KEY-----'),
    ('post','@company','title','x\0y'),
    ('post','@company','title','a\rbody'),
])
def test_invalid_or_sensitive_drafts_rejected(tmp_path,kind,target,title,body):
    store=owner(tmp_path)
    with pytest.raises(ValueError):store.prepare_service_draft(kind,target,title,body)
    assert store.service_draft_history()==[]


def test_unauthenticated_access_denied(tmp_path):
    store=owner(tmp_path)
    draft=store.prepare_service_draft('email','a@example.com','hello','world')
    store.logout()
    for action in [store.list_service_contracts,
                   lambda:store.prepare_service_draft('post','@a','hi','text'),
                   lambda:store.review_service_draft(draft['id'],True),
                   lambda:store.service_draft_detail(draft['id']),
                   store.service_draft_history]:
        with pytest.raises(AuthenticationError):action()


def test_append_only_tables_and_foreign_key(tmp_path):
    store=owner(tmp_path)
    draft=store.prepare_service_draft('post','@a','hi','text')
    with store._connect() as con:
        for table in ('service_drafts','service_draft_events'):
            with pytest.raises(sqlite3.DatabaseError):con.execute(f'DELETE FROM {table}')
            with pytest.raises(sqlite3.DatabaseError):con.execute(f'UPDATE {table} SET id=id')
        with pytest.raises(sqlite3.IntegrityError):
            con.execute("INSERT INTO service_draft_events(draft_id,action) VALUES (99999,'prepared')")
    assert store.service_draft_detail(draft['id'])['state']=='prepared'


def test_hash_detects_tampering_even_if_database_trigger_removed(tmp_path):
    store=owner(tmp_path)
    draft=store.prepare_service_draft('email','a@example.com','hi','text')
    with store._connect() as con:
        con.execute('DROP TRIGGER service_drafts_no_update')
        con.execute("UPDATE service_drafts SET body='changed' WHERE id=?",(draft['id'],))
    with pytest.raises(ValueError,match='해시'):
        store.service_draft_detail(draft['id'])
    with pytest.raises(ValueError):store.review_service_draft(draft['id'],True)


def test_reject_bad_review_types_and_ids(tmp_path):
    store=owner(tmp_path)
    draft=store.prepare_service_draft('service','inventory','hello','text')
    for args in [(0,True,''),('1',True,''),(draft['id'],1,''),(draft['id'],True,'x'*201)]:
        with pytest.raises(ValueError):store.review_service_draft(*args)
    with pytest.raises(ValueError):store.review_service_draft(draft['id'],True,'api_key=secret')
    with pytest.raises(ValueError):store.service_draft_history(0)
    with pytest.raises(ValueError):store.service_draft_history(True)
    assert store.service_draft_detail(draft['id'])['state']=='prepared'


def test_unknown_non_string_kind_rejected():
    with pytest.raises(ValueError):validate_draft([], 'target', 'title', 'body')


def test_plaintext_storage_is_documented_and_not_exported_automatically(tmp_path):
    store=owner(tmp_path)
    store.prepare_service_draft('post','@a','local','Only local text')
    assert store.path.exists()
    assert b'Only local text' in store.path.read_bytes()
    assert not hasattr(store,'send_service_draft')
    assert not hasattr(store,'dispatch_service_draft')


def test_independent_drafts_and_history_order(tmp_path):
    store=owner(tmp_path)
    first=store.prepare_service_draft('email','a@example.com','one','body')
    second=store.prepare_service_draft('post','@b','two','body')
    assert [r['id'] for r in store.service_draft_history(2)] == [second['id'],first['id']]
    store.review_service_draft(first['id'],True)
    assert store.service_draft_history(1)[0]['state']=='prepared'
    assert store.service_draft_detail(first['id'])['state']=='reviewed_local_only'
