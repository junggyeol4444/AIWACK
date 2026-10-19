"""Stage54 follow-on: opt-in live HTTPS research; all test I/O is mocked.

Passing tests DO NOT prove this sandbox can reach actual internet hosts.
"""
import hashlib
import sqlite3

import pytest

from desktop.public_web_research import (
    PublicFetchError, check_public_url, checked_dns, initialize,
    read_public_https, MAX_RESPONSE_BYTES,
)
from desktop.storage import LocalStore, AuthenticationError


class DummyResponse:
    def __init__(self, body=b'<title>ignored</title><p>Hello world</p>', status=200,
                 content_type='text/html', extra=None):
        self.body = body
        self.status = status
        self.headers = {'Content-Type': content_type, 'Content-Length': str(len(body))}
        if extra:
            self.headers.update(extra)

    def getheader(self, name, default=None):
        return self.headers.get(name, default)

    def read(self, max_bytes):
        return self.body[:max_bytes]


class DummyConnection:
    def __init__(self, hostname, pinned_ip, timeout, response=None):
        self.hostname, self.ip, self.timeout = hostname, pinned_ip, timeout
        self.response = response or DummyResponse()
        self.request_call = None
        self.closed = False

    def request(self, method, target, headers):
        self.request_call = method, target, headers

    def getresponse(self):
        return self.response

    def close(self):
        self.closed = True


def fake_resolver(host, port, type):
    assert host == 'docs.python.org'
    assert port == 443
    return [(None, None, None, None, ('8.8.8.8', 443))]


def dummy_read(url='https://docs.python.org/3/library/ssl.html', **kwargs):
    calls = []
    def factory(hostname, ip, timeout):
        con = DummyConnection(hostname, ip, timeout, **kwargs)
        calls.append(con)
        return con
    result = read_public_https(url, 'docs.python.org', consent=True,
                               resolver=fake_resolver, connection_factory=factory)
    return result, calls[0]


def test_public_get_pinned_dns_tls_hostname_and_metadata():
    result, conn = dummy_read()
    assert result['fetched_over_https'] is True
    assert result['independently_fact_checked'] is False
    assert result['pinned_ip'] == '8.8.8.8'
    assert result['raw_sha256'] == hashlib.sha256(conn.response.body).hexdigest()
    assert conn.hostname == 'docs.python.org' and conn.ip == '8.8.8.8'
    assert conn.request_call[0:2] == ('GET', '/3/library/ssl.html')
    assert 'Authorization' not in conn.request_call[2]
    assert 'Cookie' not in conn.request_call[2]
    assert conn.closed


@pytest.mark.parametrize('url,host', [
    ('http://docs.python.org/', 'docs.python.org'),
    ('file:///etc/passwd', 'docs.python.org'),
    ('https://user:password@docs.python.org/', 'docs.python.org'),
    ('https://docs.python.org:8443/', 'docs.python.org'),
    ('https://docs.python.org/#fragment', 'docs.python.org'),
    ('https://docs.python.org/a', 'other.org'),
    ('https://127.0.0.1/secret', '127.0.0.1'),
    ('https://169.254.169.254/latest/meta-data', '169.254.169.254'),
    ('https://localhost.local/', 'localhost.local'),
    ('https://evil.internal/a', 'evil.internal'),
    ('https://github.com/', 'github.com'),
    ('https://raw.githubusercontent.com/x', 'raw.githubusercontent.com'),
    ('https://foo.github.io/', 'foo.github.io'),
    ('https://docs.python.org\\@evil.org/', 'docs.python.org'),
    ('https://docs.python.org/', 'DOCS.PYTHON.ORG'),
    ('https://docs.python.org', ''),
])
def test_invalid_urls_no_dns_or_network(url, host):
    def do_not_resolve(*args, **kwargs):
        raise AssertionError('DNS must never be called for invalid input')
    with pytest.raises(PublicFetchError):
        read_public_https(url, host, consent=True, resolver=do_not_resolve)


def test_no_consent_no_dns_or_network():
    with pytest.raises(PublicFetchError, match='Explicit consent'):
        read_public_https('https://docs.python.org/', 'docs.python.org',
                          resolver=lambda *args: pytest.fail('DNS called'))


@pytest.mark.parametrize('address', ['127.0.0.1','::1','10.0.0.1','192.168.1.1',
                                    '169.254.169.254','0.0.0.0','fc00::1','fe80::1'])
def test_reject_private_and_metadata_dns(address):
    with pytest.raises(PublicFetchError):
        checked_dns('docs.python.org', resolver=lambda *args, **kwargs: [
            (None, None, None, None, (address, 443))])


def test_reject_mixed_public_private_answer():
    with pytest.raises(PublicFetchError):
        checked_dns('docs.python.org', resolver=lambda *args, **kwargs: [
            (None,None,None,None,('8.8.8.8',443)),
            (None,None,None,None,('10.0.0.2',443))])


@pytest.mark.parametrize('response', [
    DummyResponse(status=301, extra={'Location':'http://127.0.0.1'}),
    DummyResponse(status=403),
    DummyResponse(content_type='application/json'),
    DummyResponse(extra={'Content-Encoding':'gzip'}),
    DummyResponse(extra={'Content-Length':str(MAX_RESPONSE_BYTES+1)}),
    DummyResponse(body=b'x'*(MAX_RESPONSE_BYTES+1)),
    DummyResponse(body=b''),
    DummyResponse(extra={'Content-Type':'text/html; charset=shift_jis'}),
])
def test_reject_response_and_always_close(response):
    conn = DummyConnection('docs.python.org','8.8.8.8',6,response)
    with pytest.raises(PublicFetchError):
        read_public_https('https://docs.python.org/', 'docs.python.org',
            consent=True, resolver=fake_resolver, connection_factory=lambda *args: conn)
    assert conn.closed


def test_initialize_is_idempotent_and_makes_no_network(tmp_path, monkeypatch):
    import socket
    monkeypatch.setattr(socket, 'getaddrinfo', lambda *args, **kwargs: pytest.fail('unexpected DNS'))
    store = LocalStore(tmp_path/'company.db')
    assert store.has_owner() is False
    LocalStore(tmp_path/'company.db')


def test_owner_record_persists_as_unverified_and_append_only(tmp_path, monkeypatch):
    store = LocalStore(tmp_path/'company.db')
    store.setup_owner('owner', 'a-secure-test-password')
    monkeypatch.setattr('desktop.public_web_research.read_public_https',
                        lambda *a, **k: dummy_read()[0])
    receipt = store.fetch_public_research('https://docs.python.org/3/library/ssl.html',
                                          'docs.python.org','Docs sample', consent=True)
    assert receipt['http_status'] == 200 and receipt['source_verified'] is False
    doc = store.read_offline_research(receipt['capture_id'])
    assert doc['source_verification'] == 'unverified'
    assert 'Hello world' in doc['body']
    with sqlite3.connect(store.path) as con:
        row = con.execute('SELECT pinned_ip,raw_sha256 FROM public_web_research_receipts').fetchone()
        assert row[0] == '8.8.8.8'
        with pytest.raises(sqlite3.IntegrityError):
            con.execute('DELETE FROM public_web_research_receipts')
        with pytest.raises(sqlite3.IntegrityError):
            con.execute('UPDATE public_web_research_receipts SET pinned_ip=?',('9.9.9.9',))
    with pytest.raises(ValueError):
        store.fetch_public_research('https://docs.python.org/3/library/ssl.html',
                                    'docs.python.org','Docs sample',consent=True)
    assert store.search_offline_research('Hello world')
    store.logout()
    with pytest.raises(AuthenticationError):
        store.fetch_public_research('https://docs.python.org/','docs.python.org','No',consent=True)


def test_logout_during_network_read_does_not_save(tmp_path, monkeypatch):
    store = LocalStore(tmp_path/'company.db')
    store.setup_owner('owner', 'a-secure-test-password')
    def logout_mid_request(*args, **kwargs):
        store.logout()
        return dummy_read()[0]
    monkeypatch.setattr('desktop.public_web_research.read_public_https', logout_mid_request)
    with pytest.raises(AuthenticationError):
        store.fetch_public_research('https://docs.python.org/','docs.python.org','Test',consent=True)
    with sqlite3.connect(store.path) as con:
        assert con.execute('SELECT count(*) FROM public_web_research_receipts').fetchone()[0] == 0
