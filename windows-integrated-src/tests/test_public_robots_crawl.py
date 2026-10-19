"""Public crawling respects robots.txt before loading any content.

The transport is mocked here. A separate connector test is required to claim
real internet reachability from a Windows installation.
"""
import hashlib
import sqlite3

import pytest

from desktop.public_site_crawler import crawl_site_with_robots
from desktop.public_web_research import PublicFetchError
from desktop.storage import LocalStore, AuthenticationError

HOST='docs.python.org'
BASE='https://docs.python.org/3/library/urllib.request.html'
ROBOT='https://docs.python.org/robots.txt'
DENIED='https://docs.python.org/private/sales'
ALLOWED='https://docs.python.org/3/library/urllib.robotparser.html'


def result(url,text,media):
    raw=text.encode('utf-8')
    return dict(url=url,hostname=HOST,content=text,media_type=media,
                http_status=200,fetched_over_https=True,raw_size=len(raw),
                raw_sha256=hashlib.sha256(raw).hexdigest(),pinned_ip='8.8.8.8')


def reader(log, rules='User-agent: AIWACK-public-research\nDisallow: /private/\nCrawl-delay: 1\n'):
    def fetch(url,host,*,consent):
        assert consent is True and host==HOST
        log.append(url)
        if url == ROBOT:
            return result(url,rules,'text/plain')
        if url == BASE:
            return result(url,'<a href="/private/sales">deny</a><a href="urllib.robotparser.html">allow</a>','text/html')
        if url == ALLOWED:
            return result(url,'<p>Document for business research</p>','text/html')
        pytest.fail(f'Disallowed or unrelated page fetched: {url}')
    return fetch


def test_robots_disallows_page_and_honors_delay():
    network=[]; delays=[]
    r=crawl_site_with_robots(BASE,HOST,consent=True,max_pages=3,max_depth=1,
                             reader=reader(network),sleeper=delays.append)
    assert network==[ROBOT,BASE,ALLOWED]
    assert r['robots_checked'] is True and r['robots_denied_count']==1
    assert r['pages'][0]['url']==BASE and r['pages'][1]['url']==ALLOWED
    assert len(delays)==2 and delays == [1,1]
    assert len(r['robots_sha256'])==64


def test_nonconsenting_call_never_reads_robots():
    with pytest.raises(PublicFetchError):
        crawl_site_with_robots(BASE,HOST,reader=lambda *a,**k:pytest.fail('Unexpected connection'))


def test_disallowed_start_never_fetches_any_page():
    log=[]
    with pytest.raises(PublicFetchError,match='denied'):
        crawl_site_with_robots(DENIED,HOST,consent=True,reader=reader(log),sleeper=lambda x:None)
    assert log==[ROBOT]


@pytest.mark.parametrize('bad',[
    '', 'User-agent: *\nCrawl-delay: 200\n',
    'User-agent: *\nDisallow: /3/library/\n',
])
def test_invalid_or_restrictive_policy_fails_closed(bad):
    log=[]
    with pytest.raises(PublicFetchError):
        crawl_site_with_robots(BASE,HOST,consent=True,reader=reader(log,bad),sleeper=lambda x:None)
    assert log==[ROBOT]


def test_missing_robots_fails_closed():
    log=[]
    def failing(url,host,*,consent):
        log.append(url)
        raise PublicFetchError('Robots returned 404')
    with pytest.raises(PublicFetchError):
        crawl_site_with_robots(BASE,HOST,consent=True,reader=failing,sleeper=lambda x:None)
    assert log==[ROBOT]


def test_robots_checked_result_audited_in_sqlite(tmp_path,monkeypatch):
    s=LocalStore(tmp_path/'staff.db')
    s.setup_owner('owner','long-test-owner-password')
    monkeypatch.setattr('desktop.public_site_crawler.read_public_https',reader([]))
    monkeypatch.setattr('desktop.public_site_crawler.time.sleep',lambda _:None)
    r=s.crawl_public_site_robots_checked(BASE,HOST,consent=True,max_pages=3,max_depth=1)
    assert r['robots_checked'] and r['robots_denied_count']==1 and r['pages']==2
    with sqlite3.connect(s.path) as db:
        row=db.execute('SELECT robots_sha256,robots_denied_count FROM public_site_crawl_runs').fetchone()
        assert len(row[0])==64 and row[1]==1
        with pytest.raises(sqlite3.IntegrityError):
            db.execute('UPDATE public_site_crawl_runs SET robots_denied_count=0')
    s.logout()
    with pytest.raises(AuthenticationError):
        s.crawl_public_site_robots_checked(BASE,HOST,consent=True)


def test_storage_migrates_existing_crawl_run_rows(tmp_path):
    s=LocalStore(tmp_path/'v1.db')
    with sqlite3.connect(s.path) as db:
        db.execute('DROP TABLE public_site_crawl_runs')
        db.execute('''CREATE TABLE public_site_crawl_runs(
           id INTEGER PRIMARY KEY AUTOINCREMENT,start_url TEXT NOT NULL,
           hostname TEXT NOT NULL,page_count INTEGER NOT NULL,
           total_bytes INTEGER NOT NULL,errors_json TEXT NOT NULL,
           created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)''')
        db.execute("INSERT INTO public_site_crawl_runs(start_url,hostname,page_count,total_bytes,errors_json) VALUES(?,?,?,?,?)",
                   (BASE,HOST,1,100,'[]'))
    LocalStore(s.path)
    with sqlite3.connect(s.path) as db:
        row=db.execute('SELECT start_url,robots_sha256,robots_denied_count FROM public_site_crawl_runs').fetchone()
        assert row==(BASE,None,0)
