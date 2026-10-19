"""Owner-triggered, bounded public-site crawler and portable plugin-result ingest.

Site crawling is an actual opt-in HTTPS GET path, not a mocked business API.
External ChatGPT plugins are NOT magically embedded in a standalone EXE: their
results can be imported through a local, schema-checked JSON handoff.
No credentials, checkout, publication, GitHub, or background network work.
"""
from __future__ import annotations

import hashlib
from html.parser import HTMLParser
import json
import sqlite3
import time
from urllib.robotparser import RobotFileParser
from urllib.parse import urldefrag, urljoin, urlsplit

from desktop.public_web_research import (check_public_url, read_public_https,
                                          save_success, PublicFetchError)

MAX_PAGES = 6
ROBOTS_USER_AGENT = 'AIWACK-public-research'
MAX_ROBOTS_SIZE = 24_000
MAX_CRAWL_DELAY = 15.0
MIN_CRAWL_DELAY = 0.5
MAX_DEPTH = 2
MAX_TOTAL_BYTES = 512_000
MAX_PROVIDER_RECORDS = 10
MAX_PROVIDER_TEXT = 60_000
MAX_JSON_BYTES = 800_000
PROVIDERS = frozenset({'tinyfish', 'firecrawl', 'tavily', 'browser_export'})


class _Anchors(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.hrefs: list[str] = []
        self.in_hidden = 0

    def handle_starttag(self, tag, attrs):
        if tag in ('script', 'style', 'template', 'noscript'):
            self.in_hidden += 1
        if tag == 'a' and not self.in_hidden:
            for name, value in attrs:
                if name == 'href' and isinstance(value, str) and len(value) <= 2048:
                    self.hrefs.append(value)
                    break

    def handle_endtag(self, tag):
        if tag in ('script', 'style', 'template', 'noscript') and self.in_hidden:
            self.in_hidden -= 1


def _same_site_link(base: str, href: str, hostname: str) -> str | None:
    if not href or any(ord(c) < 32 or ord(c) == 127 for c in href) or '\\' in href:
        return None
    try:
        # Absolute references can only enter the queue after the same-host check.
        url, _ = urldefrag(urljoin(base, href))
        host, _ = check_public_url(url, hostname)
        if host != hostname:
            return None
        return url
    except (ValueError, UnicodeError):
        return None


def crawl_site(start_url: str, confirmed_hostname: str, *, consent: bool = False,
               max_pages: int = 3, max_depth: int = 1, reader=None,
               allowed_url=None, request_delay: float = 0.0, sleeper=None,
               robots_digest: str | None = None) -> dict:
    """Bounded BFS; only successfully retrieved pages enter the result.

    Network traffic is limited to one confirmed host. Every read independently
    pins/validates DNS and uses TLS from the existing fetcher. No redirects.
    The caller is responsible for checking the site's access rules and usage
    permission; this utility does not bypass login, robots, or rate limits.
    """
    if consent is not True:
        raise PublicFetchError('Site crawling requires explicit administrator confirmation')
    if type(max_pages) is not int or not 1 <= max_pages <= MAX_PAGES:
        raise ValueError('max_pages outside bounded range')
    if type(max_depth) is not int or not 0 <= max_depth <= MAX_DEPTH:
        raise ValueError('max_depth outside bounded range')
    hostname, _ = check_public_url(start_url, confirmed_hostname)
    reader = reader or read_public_https
    if type(request_delay) not in (float, int) or not 0 <= request_delay <= MAX_CRAWL_DELAY:
        raise ValueError('Crawl delay outside bounded range')
    sleeper = sleeper or time.sleep
    if allowed_url is not None and not callable(allowed_url):
        raise ValueError('Invalid robots access policy')
    if robots_digest is not None and (not isinstance(robots_digest, str) or len(robots_digest) != 64):
        raise ValueError('Invalid robots policy hash')
    queue = [(start_url, 0)]
    queued = {start_url}
    results = []
    errors = []
    total_bytes = 0
    attempts = 0
    blocked_by_robots = 0
    while queue and len(results) < max_pages:
        url, depth = queue.pop(0)
        try:
            if allowed_url is not None and allowed_url(url) is not True:
                blocked_by_robots += 1
                errors.append({'url': url, 'reason': 'Denied by robots.txt access policy'})
                continue
            if attempts:
                sleeper(request_delay)
            attempts += 1
            result = reader(url, hostname, consent=True)
            if result.get('url') != url or result.get('hostname') != hostname or result.get('http_status') != 200 or result.get('fetched_over_https') is not True:
                raise PublicFetchError('Fetcher returned mismatched source metadata')
            raw_size = result.get('raw_size')
            if type(raw_size) is not int or not 1 <= raw_size <= 131072:
                raise PublicFetchError('Invalid fetched page byte count')
            if total_bytes + raw_size > MAX_TOTAL_BYTES:
                errors.append({'url': url, 'reason': 'Total crawl byte budget reached'})
                break
            content = result.get('content')
            if not isinstance(content, str) or not content:
                raise PublicFetchError('Invalid fetched page content')
            total_bytes += raw_size
            results.append(result)
            if depth < max_depth and result['media_type'] == 'text/html':
                parser = _Anchors()
                parser.feed(content[:131072])
                for href in parser.hrefs[:150]:
                    new_url = _same_site_link(url, href, hostname)
                    if new_url and new_url not in queued and len(queued) < 80:
                        queue.append((new_url, depth + 1))
                        queued.add(new_url)
        except (PublicFetchError, ValueError, OSError) as exc:
            errors.append({'url': url, 'reason': str(exc)[:200]})
    if not results:
        raise PublicFetchError('No public pages were retrieved; ' + (errors[0]['reason'] if errors else 'empty site'))
    return {'start_url': start_url, 'hostname': hostname, 'pages': results,
            'errors': errors, 'total_bytes': total_bytes, 'bounded': True,
            'source_truth_verified': False, 'robots_checked': robots_digest is not None,
            'robots_sha256': robots_digest, 'robots_denied_count': blocked_by_robots}



def crawl_site_with_robots(start_url: str, confirmed_hostname: str, *, consent: bool = False,
                           max_pages: int = 3, max_depth: int = 1,
                           reader=None, sleeper=None) -> dict:
    """Owner-initiated, robots.txt-checked crawl (fail closed on unavailable policy).

    robots.txt is retrieved with the *same* pinned TLS, no-redirect transport.
    Denied paths never reach the page reader, including URLs discovered in HTML.
    Missing/invalid/unreachable robots.txt aborts rather than assuming permission.
    The robots directive is access guidance, not authorization or copyright clearance.
    """
    if consent is not True:
        raise PublicFetchError('Explicit administrator confirmation is required')
    hostname, _ = check_public_url(start_url, confirmed_hostname)
    reader = reader or read_public_https
    robots_url = 'https://' + hostname + '/robots.txt'
    rules = reader(robots_url, hostname, consent=True)
    if (rules.get('url') != robots_url or rules.get('hostname') != hostname or
            rules.get('http_status') != 200 or rules.get('fetched_over_https') is not True or
            rules.get('media_type') != 'text/plain' or
            type(rules.get('raw_size')) is not int or not 1 <= rules['raw_size'] <= MAX_ROBOTS_SIZE):
        raise PublicFetchError('Untrusted or unsupported robots.txt response')
    txt = rules.get('content')
    if not isinstance(txt, str) or not txt or len(txt.encode('utf-8')) > MAX_ROBOTS_SIZE:
        raise PublicFetchError('Invalid robots.txt content')
    if not any(line.lstrip().lower().startswith('user-agent:') and line.split(':',1)[1].strip()
               for line in txt.splitlines()):
        raise PublicFetchError('robots.txt missing valid User-agent directives')
    digest = rules.get('raw_sha256')
    if not isinstance(digest, str) or len(digest) != 64:
        raise PublicFetchError('Missing robots.txt byte digest')
    parser = RobotFileParser()
    parser.parse(txt.splitlines())
    delay = parser.crawl_delay(ROBOTS_USER_AGENT)
    if delay is None:
        delay = parser.crawl_delay('*')
    if delay is None:
        delay = 0
    if type(delay) not in (float, int) or delay < 0 or delay > MAX_CRAWL_DELAY:
        raise PublicFetchError('Unacceptable robots.txt crawl delay')
    pause = max(MIN_CRAWL_DELAY, delay)
    if not parser.can_fetch(ROBOTS_USER_AGENT, start_url):
        raise PublicFetchError('Start URL denied by robots.txt')
    # robots retrieval is itself a request: wait before retrieving the first page.
    (sleeper or time.sleep)(pause)
    result = crawl_site(start_url, hostname, consent=True, max_pages=max_pages,
                        max_depth=max_depth, reader=reader,
                        allowed_url=lambda u: parser.can_fetch(ROBOTS_USER_AGENT, u),
                        request_delay=pause, sleeper=sleeper, robots_digest=digest)
    result['robots_url'] = robots_url
    result['crawl_delay_seconds'] = pause
    return result


def _json_digest(value) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                       separators=(',', ':')).encode('utf-8')).hexdigest()


def initialize(con: sqlite3.Connection) -> None:
    con.execute('''CREATE TABLE IF NOT EXISTS public_site_crawl_runs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        start_url TEXT NOT NULL, hostname TEXT NOT NULL,
        page_count INTEGER NOT NULL, total_bytes INTEGER NOT NULL,
        errors_json TEXT NOT NULL, robots_sha256 TEXT,
        robots_denied_count INTEGER NOT NULL DEFAULT 0,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)''')
    columns = {row[1] for row in con.execute('PRAGMA table_info(public_site_crawl_runs)')}
    if 'robots_sha256' not in columns:
        con.execute('ALTER TABLE public_site_crawl_runs ADD COLUMN robots_sha256 TEXT')
    if 'robots_denied_count' not in columns:
        con.execute('ALTER TABLE public_site_crawl_runs ADD COLUMN robots_denied_count INTEGER NOT NULL DEFAULT 0')
    con.execute('''CREATE TABLE IF NOT EXISTS public_site_crawl_pages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        run_id INTEGER NOT NULL REFERENCES public_site_crawl_runs(id),
        capture_id INTEGER NOT NULL REFERENCES offline_research_captures(id),
        page_url TEXT NOT NULL, raw_sha256 TEXT NOT NULL, UNIQUE(run_id, page_url))''')
    con.execute('''CREATE TABLE IF NOT EXISTS public_plugin_imports (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        provider TEXT NOT NULL, capture_id INTEGER NOT NULL REFERENCES offline_research_captures(id),
        source_url TEXT NOT NULL, content_sha256 TEXT NOT NULL,
        provenance TEXT NOT NULL DEFAULT 'locally_imported_external_claim',
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)''')
    for table in ('public_site_crawl_runs','public_site_crawl_pages','public_plugin_imports'):
        for op in ('UPDATE', 'DELETE'):
            con.execute(f'''CREATE TRIGGER IF NOT EXISTS {table}_no_{op.lower()}
                BEFORE {op} ON {table} BEGIN
                SELECT RAISE(ABORT,'web research audit is append only'); END''')


def save_crawl(con: sqlite3.Connection, crawl: dict) -> dict:
    if not crawl.get('pages') or len(crawl['pages']) > MAX_PAGES:
        raise ValueError('Invalid bounded crawl results')
    check_public_url(crawl['start_url'], crawl['hostname'])
    errors = crawl.get('errors', [])
    robots_sha256 = crawl.get('robots_sha256')
    robots_denied = crawl.get('robots_denied_count', 0)
    if robots_sha256 is not None and (type(robots_sha256) is not str or len(robots_sha256) != 64):
        raise ValueError('Invalid robots provenance')
    if type(robots_denied) is not int or not 0 <= robots_denied <= 80:
        raise ValueError('Invalid robots denial count')
    cur = con.execute('''INSERT INTO public_site_crawl_runs
       (start_url,hostname,page_count,total_bytes,errors_json,robots_sha256,robots_denied_count)
       VALUES(?,?,?,?,?,?,?)''',
                      (crawl['start_url'], crawl['hostname'], len(crawl['pages']),
                       crawl['total_bytes'], json.dumps(errors, ensure_ascii=False),
                       robots_sha256, robots_denied))
    run_id = cur.lastrowid
    capture_ids = []
    reused = 0
    truncated = 0
    seen = set()
    for page in crawl['pages']:
        url = page['url']
        check_public_url(url, crawl['hostname'])
        if url in seen or page.get('http_status') != 200 or page.get('fetched_over_https') is not True:
            raise ValueError('Duplicated or unverified site result')
        seen.add(url)
        # The existing SQLite capture index is 60k characters; retain the
        # original fetched raw byte digest even when only an excerpt fits.
        indexed = dict(page)
        if len(indexed['content']) > 59_000:
            indexed['content'] = indexed['content'][:59_000]
            truncated += 1
        try:
            receipt = save_success(con, indexed, 'Crawled public page: ' + url[:150])
            capture_id = receipt['capture_id']
        except ValueError:
            # Reuse only if this is exactly the same source AND raw byte hash.
            row = con.execute('''SELECT c.id FROM offline_research_captures c
                JOIN public_web_research_receipts r ON r.capture_id=c.id
                WHERE c.source_url=? AND r.raw_sha256=? ORDER BY c.id LIMIT 1''',
                (url, page['raw_sha256'])).fetchone()
            if row is None:
                raise
            capture_id = row[0]
            reused += 1
        con.execute('INSERT INTO public_site_crawl_pages(run_id,capture_id,page_url,raw_sha256) VALUES(?,?,?,?)',
                    (run_id, capture_id, url, page['raw_sha256']))
        capture_ids.append(capture_id)
    return {'run_id': run_id, 'capture_ids': capture_ids, 'pages': len(capture_ids),
            'failures': len(errors), 'reused_pages': reused, 'index_truncated_pages': truncated,
            'source_verified': False, 'robots_checked': robots_sha256 is not None,
            'robots_denied_count': robots_denied}


def import_plugin_records(con: sqlite3.Connection, provider: str, records: list[dict]) -> dict:
    """Import portable result records exported from a crawling plugin.

    The provider field is an operator-selected label, NOT cryptographic proof
    of origin or web fetch. Content is stored as untrusted research evidence.
    """
    if provider not in PROVIDERS or type(records) is not list or not 1 <= len(records) <= MAX_PROVIDER_RECORDS:
        raise ValueError('Unsupported provider or batch size')
    from desktop.research_captures import add
    ids = []
    for record in records:
        if type(record) is not dict or not {'url','title','text'} <= record.keys():
            raise ValueError('Each plugin record requires url, title, text')
        url, title, body = record['url'], record['title'], record['text']
        if not isinstance(url, str):
            raise ValueError('Invalid source URL')
        host = urlsplit(url).hostname or ''
        check_public_url(url, host)
        if type(title) is not str or not 1 <= len(title) <= 200 or type(body) is not str or not 1 <= len(body) <= MAX_PROVIDER_TEXT:
            raise ValueError('Invalid plugin record text/title')
        capture_id = add(con, url, title, body, 'manual_text')
        con.execute('INSERT INTO public_plugin_imports(provider,capture_id,source_url,content_sha256) VALUES(?,?,?,?)',
                    (provider, capture_id, url, hashlib.sha256(body.encode('utf-8')).hexdigest()))
        ids.append(capture_id)
    return {'provider': provider, 'capture_ids': ids, 'source_verified': False,
            'direct_plugin_authentication': False}


def _unwrap_plugin_result(tool_result, provider: str) -> list[dict]:
    """Accept actual tool envelopes inside an operator-labeled, bounded export.

    The provider label remains an *unverified human claim*, not a credential or
    trusted attestation. Tool JSON is inert, never executed or requested again.
    """
    if type(tool_result) is dict and set(tool_result) == {'text'}:
        tool_result = tool_result['text']
    if type(tool_result) is str:
        if len(tool_result.encode('utf-8')) > MAX_JSON_BYTES:
            raise ValueError('Oversized nested tool result')
        try:
            tool_result = json.loads(tool_result)
        except (ValueError, TypeError) as exc:
            raise ValueError('Invalid nested tool response JSON') from exc
    if type(tool_result) is not dict:
        raise ValueError('Tool response must be a JSON object')
    if 'results' in tool_result:
        records = tool_result['results']
    elif 'data' in tool_result:
        data = tool_result['data']
        if type(data) is list:
            records = data
        elif type(data) is dict:
            records = [data]
        else:
            raise ValueError('Unsupported provider data payload')
    elif provider == 'firecrawl' and ('markdown' in tool_result or 'content' in tool_result):
        records = [tool_result]
    else:
        raise ValueError('Expected bounded tool results or data')
    if type(records) is not list or not 1 <= len(records) <= MAX_PROVIDER_RECORDS:
        raise ValueError('Invalid nested result count')
    return records


def load_plugin_export(raw: bytes) -> tuple[str, list[dict]]:
    """Read bounded JSON, including native tool results nested in a local label.

    Accepted local envelope: {provider,results} or {provider,tool_result}.
    This is a file handoff. It is NOT an authenticated plugin RPC from EXE.
    """
    if type(raw) is not bytes or not 1 <= len(raw) <= MAX_JSON_BYTES:
        raise ValueError('Invalid or oversized plugin export JSON')
    try:
        data = json.loads(raw.decode('utf-8-sig'))
    except (ValueError, UnicodeError) as exc:
        raise ValueError('Plugin export is not UTF-8 JSON') from exc
    if type(data) is not dict or set(data) not in ({'provider','results'}, {'provider','tool_result'}):
        raise ValueError('Expected a provider with results or tool_result')
    provider = data['provider']
    if type(provider) is not str or provider not in PROVIDERS:
        raise ValueError('Unknown or missing plugin provider label')
    records = (data['results'] if 'results' in data else
               _unwrap_plugin_result(data['tool_result'], provider))
    if type(records) is not list or not 1 <= len(records) <= MAX_PROVIDER_RECORDS:
        raise ValueError('Invalid plugin provider or record count')
    normalized = []
    for item in records:
        if type(item) is not dict:
            raise ValueError('Malformed plugin page record')
        metadata = item.get('metadata') or {}
        if type(metadata) is not dict:
            raise ValueError('Invalid plugin metadata')
        title = item['title'] if 'title' in item else metadata.get('title', 'Public web page')
        body = item.get('text') or item.get('markdown') or item.get('raw_content') or item.get('content')
        url = item.get('url') or item.get('source_url') or metadata.get('sourceURL') or metadata.get('url')
        if not isinstance(url,str) or not isinstance(title,str) or not isinstance(body,str):
            raise ValueError('Missing supported URL, title or content text')
        normalized.append({'url': url, 'title': title, 'text': body})
    return provider, normalized
