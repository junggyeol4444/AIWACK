"""Stage54 partial continuation: local evidence audit and deterministic comparisons."""
import json
import socket
import sqlite3
import hashlib
import pytest
from desktop.storage import LocalStore, AuthenticationError


@pytest.fixture
def owner(tmp_path):
    store = LocalStore(tmp_path / 'audit.sqlite3')
    store.setup_owner('audit-owner','audit-long-password-2026')
    return store


def make_bundle(owner, tmp_path):
    (tmp_path / 'a.txt').write_text('Same offline body',encoding='utf-8')
    (tmp_path / 'b.txt').write_text('Different offline body',encoding='utf-8')
    manifest = tmp_path / 'audit.json'
    manifest.write_text(json.dumps({'format':'aiwack-offline-research-bundle-v1',
       'items':[{'file':'a.txt','url':'https://example.org/one','title':'first'},
                {'file':'b.txt','url':'https://example.org/two','title':'second'}]}),encoding='utf-8')
    return owner.import_offline_research_bundle(manifest)['capture_ids']


def test_empty_audit_does_not_write(owner):
    result = owner.audit_offline_research()
    assert result == {'checked_captures':0, 'checked_batches':0, 'issues':[],
        'passed':True, 'source_authenticity_verified':False,
        'original_file_bytes_rechecked':False}
    with sqlite3.connect(owner.path) as db:
        assert db.execute('SELECT count(*) FROM offline_research_captures').fetchone()[0] == 0


def test_bundle_audit_and_comparison_across_restart(owner, tmp_path):
    first,second=make_bundle(owner,tmp_path)
    third=owner.add_offline_research('https://example.org/three','duplicate','Same offline body')
    assert owner.audit_offline_research()['checked_batches']==1
    assert owner.audit_offline_research()['checked_captures']==3
    assert owner.audit_offline_research()['passed'] is True
    mismatch=owner.compare_offline_research(first,second)
    assert mismatch['same_body'] is False
    assert mismatch['same_claimed_source'] is False
    assert mismatch['same_local_raw_file'] is False
    assert mismatch['source_authenticity_verified'] is False
    same=owner.compare_offline_research(first,third)
    assert same['same_body'] is True
    assert same['same_claimed_source'] is False
    assert same['same_local_raw_file'] is False # manual text has no raw-file hash
    owner.archive_offline_research(second)
    owner.logout()
    other=LocalStore(owner.path)
    other.login('audit-owner','audit-long-password-2026')
    assert other.audit_offline_research()['passed']
    assert other.compare_offline_research(first,second)==mismatch


def test_raw_file_same_hash_not_website_authenticity(owner,tmp_path):
    raw=b'copied bytes from some local document'
    one=tmp_path/'one.md';two=tmp_path/'two.md'
    one.write_bytes(raw);two.write_bytes(raw)
    a=owner.import_offline_research_file('https://example.org/a','first',one)
    b=owner.import_offline_research_file('https://example.net/b','second',two)
    pair=owner.compare_offline_research(a,b)
    assert pair['same_body'] and pair['same_local_raw_file']
    assert not pair['same_claimed_source']
    assert not pair['source_authenticity_verified']
    assert owner.read_offline_research(a)['local_import']['raw_sha256']==hashlib.sha256(raw).hexdigest()


def test_detect_tampered_body_hash_if_triggers_turned_off(owner):
    ident=owner.add_offline_research('https://example.org/a','original','normal')
    with sqlite3.connect(owner.path) as db:
        db.execute('DROP TRIGGER offline_research_immutable')
        db.execute('UPDATE offline_research_captures SET body=? WHERE id=?',('tampered',ident))
    result=owner.audit_offline_research()
    assert not result['passed']
    assert {'capture_id':ident, 'issue':'저장 본문 SHA-256 불일치'} in result['issues']


def test_detect_missing_bundle_rows_even_with_deleted_trigger(owner,tmp_path):
    first,second=make_bundle(owner,tmp_path)
    with sqlite3.connect(owner.path) as db:
        db.execute('DROP TRIGGER offline_research_batch_items_no_delete')
        db.execute('DELETE FROM offline_research_batch_items WHERE capture_id=?',(second,))
    result=owner.audit_offline_research()
    assert not result['passed']
    assert any('묶음' in issue['issue'] for issue in result['issues'])


def test_detect_missing_capture_reference_without_foreign_keys(owner,tmp_path):
    first,second=make_bundle(owner,tmp_path)
    with sqlite3.connect(owner.path) as db:
        db.execute('DROP TRIGGER offline_research_no_delete')
        db.execute('PRAGMA foreign_keys=OFF')
        db.execute('DELETE FROM offline_research_captures WHERE id=?',(first,))
    report=owner.audit_offline_research()
    assert not report['passed']
    assert any('참조 ID' in issue['issue'] for issue in report['issues'])


@pytest.mark.parametrize('first,second', [(1,1),(0,2),(1,0),('1',2),(True,2),(1,False),(1,'2')])
def test_invalid_comparison_identifiers(owner,first,second):
    with pytest.raises(ValueError): owner.compare_offline_research(first,second)


def test_missing_id_rejected(owner):
    ident=owner.add_offline_research('https://example.org','title','body')
    with pytest.raises(ValueError,match='찾을 수 없'):
        owner.compare_offline_research(ident,200)


def test_owner_authentication_before_access(owner):
    ident=owner.add_offline_research('https://example.org','title','body')
    owner.logout()
    with pytest.raises(AuthenticationError):owner.audit_offline_research()
    with pytest.raises(AuthenticationError):owner.compare_offline_research(ident,ident+1)


def test_no_network_access(owner, monkeypatch):
    def prohibit(*a,**kw): raise AssertionError('network access')
    monkeypatch.setattr(socket.socket,'connect',prohibit)
    monkeypatch.setattr(socket.socket,'connect_ex',prohibit)
    monkeypatch.setattr(socket,'create_connection',prohibit)
    a=owner.add_offline_research('https://example.org/a','a','offline')
    b=owner.add_offline_research('https://example.org/b','b','offline')
    assert owner.audit_offline_research()['passed']
    assert owner.compare_offline_research(a,b)['same_body']
