"""Bounded live-HTTPS crawler and portable plugin import security tests.

All unit tests replace the network transport; actual connector fetches are
recorded separately, and sandbox DNS availability is independently reported.
"""
import hashlib
import json
import sqlite3

import pytest

from desktop.public_site_crawler import (crawl_site, import_plugin_records,
    load_plugin_export, _same_site_link, MAX_PAGES)
from desktop.public_web_research import PublicFetchError
from desktop.storage import LocalStore, AuthenticationError

BASE='https://docs.python.org/3/library/urllib.request.html'
HOST='docs.python.org'


def page(url, body, media='text/html'):
    b=body.encode()
    return {'url':url,'hostname':HOST,'http_status':200,'fetched_over_https':True,
            'raw_sha256':hashlib.sha256(b).hexdigest(),'raw_size':len(b),
            'content':body,'media_type':media,'pinned_ip':'8.8.8.8'}


def make_reader(seen):
    def read(url, host, *, consent):
        assert consent is True and host == HOST
        seen.append(url)
        if url == BASE:
            return page(url,'''<html><body><a href="urllib.robotparser.html">robots</a>
                <a href="https://evil.example/privacy">external</a>
                <a href="https://github.com/private">github prohibited</a>
                <a href="javascript:alert(1)">bad</a>
                <a href="/3/library/urllib.request.html#top">repeat</a>
                <a href="urllib.error.html">extra</a></body></html>''')
        return page(url,'<html><body><h1>Article</h1></body></html>')
    return read


def store(tmp_path):
    s=LocalStore(tmp_path/'owner.sqlite3')
    s.setup_owner('owner','a-secure-test-password')
    return s


def test_bounded_bfs_follows_only_same_host_and_deduplicates():
    seen=[]
    result=crawl_site(BASE,HOST,consent=True,max_pages=2,max_depth=1,
                     reader=make_reader(seen))
    assert result['hostname']==HOST
    assert len(seen)==2
    assert seen[0]==BASE
    assert seen[1]=='https://docs.python.org/3/library/urllib.robotparser.html'
    assert len(result['pages'])==2
    assert result['source_truth_verified'] is False


def test_crawl_no_consent_never_contacts_network():
    with pytest.raises(PublicFetchError,match='explicit'):
        crawl_site(BASE,HOST, reader=lambda *a,**k: pytest.fail('network touched'))


@pytest.mark.parametrize('pages,depth',[(0,0),(7,1),(1,3),(True,0),(1,-1)])
def test_crawl_rejects_out_of_bound_requests_before_network(pages,depth):
    with pytest.raises(ValueError):
        crawl_site(BASE,HOST,consent=True,max_pages=pages,max_depth=depth,
                   reader=lambda *a,**k: pytest.fail('network touched'))


@pytest.mark.parametrize('url,host',[
    ('https://github.com/public','github.com'),
    ('https://127.0.0.1/','127.0.0.1'),
    ('http://docs.python.org/','docs.python.org'),
    (BASE,'evil.example')
])
def test_invalid_start_rejected_before_network(url,host):
    with pytest.raises(PublicFetchError):
        crawl_site(url,host,consent=True,reader=lambda *a,**k: pytest.fail('network'))


@pytest.mark.parametrize('link',[
    'https://github.com/','https://evil.example/','javascript:alert(1)',
    'mailto:a@b.com','file:///etc/passwd','//evil.example/','https://docs.python.org:8443/',
    'https://127.0.0.1/','https://docs.python.org\\@evil.example/'
])
def test_unsafe_discovered_links_are_skipped(link):
    assert _same_site_link(BASE,link,HOST) is None


def test_fetch_failures_partial_success_recorded():
    seen=[]
    reader=make_reader(seen)
    def mixed(url, host, **kwargs):
        if url != BASE:raise PublicFetchError('HTTP 429')
        return reader(url,host,**kwargs)
    result=crawl_site(BASE,HOST,consent=True,max_pages=3,reader=mixed)
    assert len(result['pages'])==1 and len(result['errors'])==2
    assert all('429' in e['reason'] for e in result['errors'])


def test_no_page_failure_is_not_claimed_as_success():
    with pytest.raises(PublicFetchError,match='No public pages'):
        crawl_site(BASE,HOST,consent=True,reader=lambda *a,**k: (_ for _ in ()).throw(PublicFetchError('DNS failed')))


def test_mismatched_reader_metadata_rejected():
    with pytest.raises(PublicFetchError):
        crawl_site(BASE,HOST,consent=True,
                   reader=lambda *a,**k:dict(page(BASE,'<p>Hi</p>'),hostname='evil.example'))


def test_atomic_crawl_ingestion_append_only_and_owner_required(tmp_path,monkeypatch):
    s=store(tmp_path)
    monkeypatch.setattr('desktop.public_site_crawler.read_public_https',make_reader([]))
    result=s.crawl_public_site(BASE,HOST,consent=True,max_pages=2,max_depth=1)
    assert result['pages']==2 and result['source_verified'] is False
    assert len(result['capture_ids'])==2
    for ident in result['capture_ids']:
        doc=s.read_offline_research(ident)
        assert doc['source_verification']=='unverified'
    with sqlite3.connect(s.path) as con:
        assert con.execute('SELECT count(*) FROM public_site_crawl_runs').fetchone()[0]==1
        assert con.execute('SELECT count(*) FROM public_web_research_receipts').fetchone()[0]==2
        with pytest.raises(sqlite3.IntegrityError):
            con.execute('DELETE FROM public_site_crawl_runs')
        with pytest.raises(sqlite3.IntegrityError):
            con.execute('UPDATE public_site_crawl_pages SET page_url=?',('bad',))
    s.logout()
    with pytest.raises(AuthenticationError):
        s.crawl_public_site(BASE,HOST,consent=True)


def test_logout_mid_crawl_discards_all_rows(tmp_path,monkeypatch):
    s=store(tmp_path)
    def logout_reader(url,host,**kw):
        s.logout()
        return page(url,'<html>hello</html>')
    monkeypatch.setattr('desktop.public_site_crawler.read_public_https',logout_reader)
    with pytest.raises(AuthenticationError):
        s.crawl_public_site(BASE,HOST,consent=True)
    with sqlite3.connect(s.path) as con:
        assert con.execute('SELECT count(*) FROM public_site_crawl_runs').fetchone()[0]==0


def test_plugin_json_import_two_real_source_example_records(tmp_path):
    s=store(tmp_path)
    doc={'provider':'tinyfish','results':[
        {'url':BASE,'title':'Python urllib.request documentation','text':'urllib.request supports HTTP resource requests.'},
        {'url':'https://docs.python.org/3/library/urllib.robotparser.html',
         'title':'Python robots.txt parser documentation','text':'RobotFileParser is used to evaluate robots.txt rules.'}]}
    raw=json.dumps(doc).encode()
    assert load_plugin_export(raw)[0]=='tinyfish'
    result=s.import_web_plugin_export(raw)
    assert len(result['capture_ids'])==2
    assert result['direct_plugin_authentication'] is False
    assert all(s.read_offline_research(i)['source_verification']=='unverified' for i in result['capture_ids'])
    with sqlite3.connect(s.path) as con:
        assert con.execute('SELECT count(*) FROM public_plugin_imports').fetchone()[0]==2
        with pytest.raises(sqlite3.IntegrityError):
            con.execute('DELETE FROM public_plugin_imports')


@pytest.mark.parametrize('invalid',[
    {'provider':'github','results':[{'url':BASE,'title':'A','text':'B'}]},
    {'provider':'tinyfish','results':[]},
    {'provider':'tinyfish','results':[{'url':'https://github.com','title':'A','text':'B'}]},
    {'provider':'tinyfish','results':[{'url':'http://docs.python.org','title':'A','text':'B'}]},
    {'provider':'tinyfish','results':[{'url':BASE,'title':'','text':'B'}]},
    {'provider':'tinyfish','results':[{'url':BASE,'title':'A','text':'x'*60001}]},
    {'provider':'tinyfish','results':[{'url':BASE,'title':'A','text':'B'}]*11},
    {'provider':'tinyfish','results':[{'url':BASE,'title':'A','text':'B'}],'token':'not allowed'},
])
def test_invalid_plugin_import_is_transactionally_rejected(tmp_path, invalid):
    s=store(tmp_path)
    with pytest.raises(ValueError):
        s.import_web_plugin_export(json.dumps(invalid).encode())
    with sqlite3.connect(s.path) as con:
        assert con.execute('SELECT count(*) FROM public_plugin_imports').fetchone()[0]==0


def test_bad_plugin_json_or_oversize_refused():
    for raw in (b'{oops', b'{}', b'', b' '*800001):
        with pytest.raises(ValueError):
            load_plugin_export(raw)


@pytest.mark.parametrize('provider,record',[
    ('tinyfish', {'url':BASE,'title':'TinyFish fetch','text':'Real plugin payload'}),
    ('firecrawl', {'url':BASE,'metadata':{'title':'Firecrawl scrape'},'markdown':'## Page text'}),
    ('tavily', {'url':BASE,'title':'Tavily crawl','raw_content':'Crawled page content'}),
])
def test_native_plugin_records_normalized_and_imported(tmp_path,provider,record):
    payload=json.dumps({'provider':provider,'results':[record]}).encode()
    normalized_provider, normalized=load_plugin_export(payload)
    assert normalized_provider==provider
    assert normalized[0]['text']
    s=store(tmp_path)
    assert len(s.import_web_plugin_export(payload)['capture_ids'])==1



def test_repeat_crawl_reuses_byte_identical_captures(tmp_path, monkeypatch):
    s=store(tmp_path)
    monkeypatch.setattr('desktop.public_site_crawler.read_public_https',make_reader([]))
    a=s.crawl_public_site(BASE,HOST,consent=True,max_pages=2,max_depth=1)
    b=s.crawl_public_site(BASE,HOST,consent=True,max_pages=2,max_depth=1)
    assert a['capture_ids']==b['capture_ids']
    assert b['reused_pages']==2
    with sqlite3.connect(s.path) as con:
        assert con.execute('SELECT COUNT(*) FROM public_site_crawl_runs').fetchone()[0]==2
        assert con.execute('SELECT COUNT(*) FROM public_site_crawl_pages').fetchone()[0]==4
        assert con.execute('SELECT COUNT(*) FROM public_web_research_receipts').fetchone()[0]==2


def test_long_html_is_indexed_as_excerpt_with_raw_hash(tmp_path,monkeypatch):
    s=store(tmp_path)
    body='<html><body>'+('Sample document text. '*4000)+'</body></html>'
    monkeypatch.setattr('desktop.public_site_crawler.read_public_https',lambda url,host,**k:page(url,body))
    receipt=s.crawl_public_site(BASE,HOST,consent=True,max_pages=1,max_depth=0)
    assert receipt['index_truncated_pages']==1
    with sqlite3.connect(s.path) as con:
        row=con.execute('SELECT raw_sha256,raw_size FROM public_web_research_receipts').fetchone()
        assert row==(hashlib.sha256(body.encode()).hexdigest(),len(body.encode()))
