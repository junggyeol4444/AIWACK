"""Stage49: literal search, immutable provenance, owner-preview ACL and safe upgrades."""
import socket
import sqlite3
import pytest
from desktop.storage import LocalStore, AuthenticationError


@pytest.fixture
def case(tmp_path):
    db = LocalStore(tmp_path/'company.sqlite3')
    db.setup_owner('owner49', 'local-stage49-secret')
    a = db.add_employee_draft('stage49_analyst', '시장조사 직원')
    b = db.add_employee_draft('stage49_writer', '문서 직원')
    d = db.create_company_knowledge('research', '수요 변화', '표본 30명, % 확인', '로컬 조사 문서')
    return db, a, b, d


def test_owner_literal_search_and_sources(case):
    db,a,b,d=case
    other=db.create_company_knowledge('procedure','반복 절차','반복 단계','내부')
    assert [r['id'] for r in db.search_company_knowledge('변화')]==[d]
    assert [r['id'] for r in db.search_company_knowledge('%')]==[d]
    assert db.search_company_knowledge('_')==[]
    assert db.search_company_knowledge('없는 문구')==[]
    sid=db.add_company_knowledge_source(d,'local_file','보고서 #42')
    assert [r['id'] for r in db.search_company_knowledge('#42')]==[d]
    source=db.list_company_knowledge_sources(d)[0]
    assert source['id']==sid and source['validation_status']=='unverified'
    assert source['source_type']=='local_file'
    assert db.read_company_knowledge(d)['content']=='표본 30명, % 확인'
    assert [r['id'] for r in db.search_company_knowledge('')]==[other,d]


def test_fail_closed_legacy_and_restricted_grants(case):
    db,a,b,d=case
    assert db.read_company_knowledge_access(d)['mode']=='owner_only'
    assert db.preview_employee_knowledge_search(a)==[]
    with pytest.raises(PermissionError):db.preview_employee_knowledge_read(a,d)
    with pytest.raises(ValueError):db.grant_company_knowledge_read(d,a)
    assert db.set_company_knowledge_visibility(d,'restricted')
    assert db.preview_employee_knowledge_search(a)==[]
    assert db.grant_company_knowledge_read(d,a)
    assert not db.grant_company_knowledge_read(d,a)
    assert [r['id'] for r in db.preview_employee_knowledge_search(a,'수요')]==[d]
    assert db.preview_employee_knowledge_read(a,d)['title']=='수요 변화'
    assert db.preview_employee_knowledge_search(b)==[]
    with pytest.raises(PermissionError):db.preview_employee_knowledge_read(b,d)
    assert db.revoke_company_knowledge_read(d,a)
    assert not db.revoke_company_knowledge_read(d,a)
    assert db.preview_employee_knowledge_search(a)==[]
    assert [x['action'] for x in db.read_company_knowledge_access(d)['audit']]==['mode','grant','revoke']


def test_company_publication_and_mode_changes_clear_grants(case):
    db,a,b,d=case
    db.set_company_knowledge_visibility(d,'restricted')
    db.grant_company_knowledge_read(d,a)
    db.set_company_knowledge_visibility(d,'company')
    assert db.read_company_knowledge_access(d)['employees']==[]
    assert db.preview_employee_knowledge_read(b,d)['title']=='수요 변화'
    db.set_company_knowledge_visibility(d,'owner_only')
    with pytest.raises(PermissionError):db.preview_employee_knowledge_read(a,d)
    db.set_company_knowledge_visibility(d,'restricted')
    assert db.preview_employee_knowledge_search(a)==[]  # no old grant resurrection


def test_inactive_employee_and_archive_fail_closed(case):
    db,a,b,d=case
    db.set_company_knowledge_visibility(d,'restricted')
    db.grant_company_knowledge_read(d,a)
    db.set_employee_inactive(a)
    with pytest.raises(ValueError):db.preview_employee_knowledge_search(a)
    with pytest.raises(ValueError):db.preview_employee_knowledge_read(a,d)
    with pytest.raises(ValueError):db.grant_company_knowledge_read(d,a)
    db.restore_employee_draft(a)
    assert db.preview_employee_knowledge_read(a,d)['id']==d
    db.archive_company_knowledge(d)
    assert db.search_company_knowledge('')==[]
    assert len(db.search_company_knowledge('',include_archived=True))==1
    assert db.preview_employee_knowledge_search(a)==[]
    with pytest.raises(ValueError):db.preview_employee_knowledge_read(a,d)
    for operation in (lambda:db.set_company_knowledge_visibility(d,'company'),
                      lambda:db.grant_company_knowledge_read(d,a),
                      lambda:db.add_company_knowledge_source(d,'manual','새 자료')):
        with pytest.raises(ValueError):operation()
    assert db.list_company_knowledge_sources(d)==[]


def test_restart_and_owner_logout(case):
    db,a,b,d=case
    db.add_company_knowledge_source(d,'internal_record','회의록 11')
    db.set_company_knowledge_visibility(d,'restricted')
    db.grant_company_knowledge_read(d,b)
    db.logout()
    for action in (lambda:db.search_company_knowledge(''),
                   lambda:db.preview_employee_knowledge_search(b),
                   lambda:db.preview_employee_knowledge_read(b,d),
                   lambda:db.list_company_knowledge_sources(d),
                   lambda:db.read_company_knowledge_access(d),
                   lambda:db.grant_company_knowledge_read(d,a)):
        with pytest.raises(AuthenticationError): action()
    again=LocalStore(db.path)
    again.login('owner49', 'local-stage49-secret')
    assert again.preview_employee_knowledge_read(b,d)['id']==d
    assert again.search_company_knowledge('회의록 11')[0]['id']==d
    with sqlite3.connect(db.path) as con:
        con.execute('PRAGMA foreign_keys=ON')
        assert not con.execute('PRAGMA foreign_key_check').fetchall()
        for sql in ("UPDATE knowledge_provenance SET reference='fake'",
                    'DELETE FROM knowledge_provenance',
                    'DELETE FROM knowledge_access_audit'):
            with pytest.raises(sqlite3.IntegrityError):con.execute(sql)


@pytest.mark.parametrize('bad', [0,-1,True,1.0,'1',None])
def test_invalid_document_and_employee_ids(case,bad):
    db,a,b,d=case
    functions = [lambda:db.read_company_knowledge_access(bad),
                 lambda:db.list_company_knowledge_sources(bad),
                 lambda:db.set_company_knowledge_visibility(bad,'company'),
                 lambda:db.preview_employee_knowledge_read(a,bad),
                 lambda:db.grant_company_knowledge_read(d,bad)]
    functions.append(lambda:db.preview_employee_knowledge_search(bad))
    for fn in functions:
        with pytest.raises(ValueError):fn()


@pytest.mark.parametrize('bad', ['',None,4,'open','owner','OWNER_ONLY'])
def test_invalid_modes(case,bad):
    db,a,b,d=case
    with pytest.raises(ValueError):db.set_company_knowledge_visibility(d,bad)
    assert db.read_company_knowledge_access(d)['mode']=='owner_only'


@pytest.mark.parametrize('source,ref', [('unlisted','test'),('manual',''),('manual','a'*501),
                                        ('manual',None),(None,'test'),('manual',20)])
def test_invalid_source_info(case,source,ref):
    db,a,b,d=case
    with pytest.raises(ValueError):db.add_company_knowledge_source(d,source,ref)
    assert db.list_company_knowledge_sources(d)==[]


@pytest.mark.parametrize('query', [None, 12, 'x'*121])
def test_invalid_search(case,query):
    db,a,b,d=case
    with pytest.raises(ValueError):db.search_company_knowledge(query)
    with pytest.raises(ValueError):db.preview_employee_knowledge_search(a,query)


def test_invalid_search_opts(case):
    db,a,b,d=case
    for kwargs in ({'limit':0},{'limit':True},{'limit':501},{'include_archived':1}):
        with pytest.raises(ValueError):db.search_company_knowledge('',**kwargs)
    with pytest.raises(ValueError):db.preview_employee_knowledge_search(a,limit=True)
    with pytest.raises(ValueError):db.read_company_knowledge_access(999999)
    with pytest.raises(ValueError):db.grant_company_knowledge_read(d,999999)


def test_no_external_network(case,monkeypatch):
    db,a,b,d=case
    def blocked(*args,**kwargs):raise AssertionError('external traffic forbidden')
    monkeypatch.setattr(socket.socket,'connect',blocked)
    db.add_company_knowledge_source(d,'website_reference','https://example.invalid/page')
    db.set_company_knowledge_visibility(d,'company')
    assert db.preview_employee_knowledge_read(b,d)['id']==d
    assert db.search_company_knowledge('example.invalid')[0]['id']==d
    assert db.list_company_knowledge_sources(d)[0]['validation_status']=='unverified'
