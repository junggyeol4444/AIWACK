"""Stage48: company knowledge storage, immutable content, owner access and persistence."""
import sqlite3
import socket
import pytest
from desktop.storage import LocalStore, AuthenticationError


@pytest.fixture
def store(tmp_path):
    db = LocalStore(tmp_path/'company.sqlite3')
    db.setup_owner('stage48-owner','stage48-strong-password')
    return db


def test_create_list_read_restart_archive(store):
    first = store.create_company_knowledge('policy', '보안 정책', '외부 지출은 별도 승인', '관리자 지침')
    second = store.create_company_knowledge('research', '수요 조사', '고객 반응 기록', '시장조사 자료')
    assert [x['id'] for x in store.list_company_knowledge()] == [second, first]
    assert store.read_company_knowledge(first)['content'] == '외부 지출은 별도 승인'
    assert store.archive_company_knowledge(first)
    assert [x['id'] for x in store.list_company_knowledge()] == [second]
    assert [x['id'] for x in store.list_company_knowledge(include_archived=True)] == [second,first]
    assert store.read_company_knowledge(first)['archived_at']
    with pytest.raises(ValueError):store.archive_company_knowledge(first)
    store.logout()
    restarted = LocalStore(store.path)
    with pytest.raises(AuthenticationError):restarted.list_company_knowledge()
    restarted.login('stage48-owner','stage48-strong-password')
    assert restarted.read_company_knowledge(first)['source'] == '관리자 지침'
    assert restarted.list_company_knowledge()[0]['id'] == second


def test_sqlite_immutability_and_archive(store):
    doc = store.create_company_knowledge('development','로컬 개발','SQLite 사용','테스트')
    with sqlite3.connect(store.path) as con:
        con.execute('PRAGMA foreign_keys=ON')
        for sql in (f"UPDATE company_knowledge_documents SET content='changed' WHERE id={doc}",
                    f"DELETE FROM company_knowledge_documents WHERE id={doc}",
                    f"UPDATE company_knowledge_documents SET archived_at=NULL WHERE id={doc}"):
            with pytest.raises(sqlite3.IntegrityError): con.execute(sql)
    store.archive_company_knowledge(doc)
    with sqlite3.connect(store.path) as con:
        with pytest.raises(sqlite3.IntegrityError):
            con.execute('UPDATE company_knowledge_documents SET archived_at=CURRENT_TIMESTAMP WHERE id=?',(doc,))
    assert store.read_company_knowledge(doc)['content']=='SQLite 사용'


@pytest.mark.parametrize('field,value', [
    ('kind','unrecognized'),('kind',None),('title',''),('title','  '),('title','x'*161),
    ('content',''),('content','x'*10001),('source',''),('source','x'*501),
    ('source',None),('title',42),('kind',1)
])
def test_create_validation(store,field,value):
    args=dict(kind='policy',title='지침',content='본문',source='원본')
    args[field]=value
    with pytest.raises(ValueError):store.create_company_knowledge(**args)
    assert store.list_company_knowledge()==[]


def test_read_archive_validation_and_limits(store):
    doc=store.create_company_knowledge('other','제목','본문','출처')
    for wrong in (0,True,'1',None,-1,999999):
        with pytest.raises(ValueError):store.read_company_knowledge(wrong)
        with pytest.raises(ValueError):store.archive_company_knowledge(wrong)
    for kwargs in ({'include_archived':1},{'limit':0},{'limit':True},{'limit':501}):
        with pytest.raises(ValueError):store.list_company_knowledge(**kwargs)
    assert store.read_company_knowledge(doc)['kind']=='other'


def test_owner_permission_and_no_remote_network(store,monkeypatch):
    def forbidden(*args,**kwargs):raise AssertionError('External connections forbidden')
    monkeypatch.setattr(socket.socket,'connect',forbidden)
    doc=store.create_company_knowledge('policy','로컬','네트워크 없이 실행','내부')
    assert store.read_company_knowledge(doc)['title']=='로컬'
    store.logout()
    for fn in (lambda:store.create_company_knowledge('policy','a','b','c'),
               lambda:store.list_company_knowledge(),
               lambda:store.read_company_knowledge(doc),
               lambda:store.archive_company_knowledge(doc)):
        with pytest.raises(AuthenticationError):fn()
