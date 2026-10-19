"""Stage54: offline research material custody; no HTTP fetch supported."""
import sqlite3
from concurrent.futures import ThreadPoolExecutor
import pytest
from desktop.storage import LocalStore, AuthenticationError
from desktop.research_captures import extract_html, MAX_CONTENT

@pytest.fixture
def owner(tmp_path):
    s=LocalStore(tmp_path/'company.sqlite3')
    s.setup_owner('research-owner','strong-password-for-research')
    return s


def test_text_capture_search_read_and_restart(owner):
    ident=owner.add_offline_research('https://example.org/report?x=1#part','매출 자료','자료 출처를 검증하지 않았습니다.')
    doc=owner.read_offline_research(ident)
    assert doc['source_url']=='https://example.org/report?x=1'
    assert doc['source_verification']=='unverified'
    assert len(doc['content_sha256'])==64
    assert owner.search_offline_research('매출')[0]['id']==ident
    assert owner.search_offline_research('검증하지')[0]['id']==ident
    owner.logout()
    with pytest.raises(AuthenticationError):owner.read_offline_research(ident)
    restarted=LocalStore(owner.path)
    restarted.login('research-owner','strong-password-for-research')
    assert restarted.read_offline_research(ident)==doc


def test_html_inert_extraction_and_no_script(owner):
    page='<html><style>evil {}</style><h1>매출 보고</h1><script>dangerous()</script><p>10 &amp; 20</p></html>'
    ident=owner.add_offline_research('https://example.org/info','사본',page,'html_snapshot')
    doc=owner.read_offline_research(ident)
    assert '매출 보고' in doc['body'] and '10 & 20' in doc['body']
    assert 'dangerous' not in doc['body'] and 'evil' not in doc['body']
    assert doc['capture_kind']=='html_snapshot'
    assert doc['source_verification']=='unverified'


def test_archive_preserves_original_and_is_immutable(owner):
    ident=owner.add_offline_research('https://example.com/','test','original')
    assert owner.archive_offline_research(ident) is True
    assert owner.search_offline_research()==[]
    assert owner.search_offline_research(include_archived=True)[0]['id']==ident
    assert owner.read_offline_research(ident)['body']=='original'
    with pytest.raises(ValueError):owner.archive_offline_research(ident)
    with sqlite3.connect(owner.path) as con:
        with pytest.raises(sqlite3.IntegrityError):
            con.execute('UPDATE offline_research_captures SET body=? WHERE id=?',('tampered',ident))
        with pytest.raises(sqlite3.IntegrityError):
            con.execute('DELETE FROM offline_research_captures WHERE id=?',(ident,))


def test_duplicate_and_later_revision(owner):
    ident=owner.add_offline_research('https://example.org/page','t','same')
    with pytest.raises(ValueError,match='이미'):
        owner.add_offline_research('https://example.org/page','t2','same')
    later=owner.add_offline_research('https://example.org/page','t','changed')
    assert later!=ident
    assert len(owner.search_offline_research())==2


@pytest.mark.parametrize('url', [None,'','file:///etc/passwd','javascript:alert(1)',
    'https://user:pass@example.com/','https://localhost/test','https://example.com:9000/a',
    'https://bad example.com','ftp://example.com/a','http://example.com:bad/'])
def test_bad_urls_refused(owner,url):
    with pytest.raises(ValueError):owner.add_offline_research(url,'title','body')
    assert owner.search_offline_research()==[]


@pytest.mark.parametrize('bad', ['',None,123,'x\x00y', 'A'*(MAX_CONTENT+1)], ids=['empty','none','integer','nul','over_max'])
def test_invalid_content(owner,bad):
    with pytest.raises(ValueError):owner.add_offline_research('https://example.com','title',bad)


def test_invalid_modes_query_limit_id(owner):
    for kind in ('remote','fetch','',None):
        with pytest.raises(ValueError):owner.add_offline_research('https://example.com','t','body',kind)
    for query in ('a'*201,None,'\x00'):
        with pytest.raises(ValueError):owner.search_offline_research(query)
    for limit in (0,501,True):
        with pytest.raises(ValueError):owner.search_offline_research(limit=limit)
    for ident in (0,'1',True,None):
        with pytest.raises(ValueError):owner.read_offline_research(ident)
    for text in ('<script>alert(1)</script>', '<style>a</style>'):
        with pytest.raises(ValueError):extract_html(text)


def test_literal_search_wildcards(owner):
    owner.add_offline_research('https://example.org/a','profit 25%','literal_underscore')
    owner.add_offline_research('https://example.org/b','profit 250','text')
    assert len(owner.search_offline_research('25%'))==1
    assert len(owner.search_offline_research('literal_'))==1


def test_concurrent_duplicate_exactly_once(owner):
    def insert(_):
        try:
            owner.add_offline_research('https://example.org/a','test','same')
            return 'ok'
        except ValueError:
            return 'duplicate'
    with ThreadPoolExecutor(max_workers=3) as pool:
        assert sorted(pool.map(insert,range(3)))==['duplicate','duplicate','ok']


def test_owner_only_guard(owner):
    ident=owner.add_offline_research('https://example.org','t','data')
    owner.logout()
    for call in (lambda:owner.add_offline_research('https://example.com','title','body'),
                 lambda:owner.search_offline_research(),
                 lambda:owner.read_offline_research(ident),
                 lambda:owner.archive_offline_research(ident)):
        with pytest.raises(AuthenticationError):call()


def test_no_network_used(monkeypatch,owner):
    import socket
    def prohibited(*args,**kwargs):raise AssertionError('network call')
    monkeypatch.setattr(socket.socket,'connect',prohibited)
    monkeypatch.setattr(socket,'create_connection',prohibited)
    ident=owner.add_offline_research('https://example.com/report','연구', '<h2>결론</h2>','html_snapshot')
    assert owner.read_offline_research(ident)['body']=='결론'
