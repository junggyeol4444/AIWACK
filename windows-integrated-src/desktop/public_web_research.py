"""Owner-initiated public HTTPS GET for research, with pinned public DNS results.

No crawler, payment, login, posting, credential header, script execution, or
browser. A successful TLS transfer is NOT independent fact/source verification.
No network activity occurs on import or LocalStore initialization.
"""
from __future__ import annotations

import hashlib
import http.client
import ipaddress
import re
import socket
import sqlite3
import ssl
from urllib.parse import urlsplit

MAX_RESPONSE_BYTES = 128 * 1024
MAX_TIMEOUT = 8
HOST_PATTERN = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?(?:\.[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)+$")
FORBIDDEN_DOMAINS = ('github.com', 'githubusercontent.com', 'github.io', 'githubassets.com', 'githubcopilot.com')

class PublicFetchError(ValueError):
    """A public read was refused, or the remote request failed."""


def check_public_url(url: str, permitted_hostname: str) -> tuple[str, str]:
    """URL and exact owner-confirmed hostname MUST match (no implicit redirect)."""
    if type(url) is not str or not 1 <= len(url) <= 2048 or any(ord(c) < 33 or ord(c) == 127 for c in url) or '\\' in url:
        raise PublicFetchError('Invalid HTTPS URL')
    if type(permitted_hostname) is not str or permitted_hostname != permitted_hostname.lower():
        raise PublicFetchError('Explicit lowercase hostname confirmation is required')
    try:
        parts = urlsplit(url)
        host = parts.hostname
        port = parts.port
    except (ValueError, UnicodeError) as exc:
        raise PublicFetchError('Malformed HTTPS URL') from exc
    if (parts.scheme != 'https' or not host or parts.username is not None or
            parts.password is not None or parts.fragment or port not in (None, 443) or
            parts.netloc != host and parts.netloc != host + ':443'):
        raise PublicFetchError('Only plain public HTTPS hosts/ports are permitted')
    if not HOST_PATTERN.fullmatch(host) or host != permitted_hostname:
        raise PublicFetchError('URL hostname does not match owner confirmation')
    if host.endswith(('.local', '.internal', '.test', '.invalid', '.localhost', '.onion', '.home.arpa')) or any(host == d or host.endswith('.' + d) for d in FORBIDDEN_DOMAINS):
        raise PublicFetchError('Restricted or non-public hostname')
    # Reject direct IP literals and ambiguous numeric hostname spellings.
    if host.split('.')[-1].isdigit() or host.startswith('xn--') or '.xn--' in host:
        raise PublicFetchError('Ambiguous hostname')
    target = (parts.path or '/') + ('?' + parts.query if parts.query else '')
    return host, target


def checked_dns(hostname: str, *, resolver=None) -> str:
    """Fail closed if *any* DNS answer is not globally routable; pin one IP."""
    resolver = resolver or socket.getaddrinfo
    try:
        records = resolver(hostname, 443, type=socket.SOCK_STREAM)
    except (OSError, ValueError) as exc:
        raise PublicFetchError('DNS lookup failed; no internet transfer completed') from exc
    if not records:
        raise PublicFetchError('No resolved hostname addresses')
    ips = []
    for record in records:
        try:
            addr = ipaddress.ip_address(record[4][0])
        except (ValueError, IndexError, TypeError) as exc:
            raise PublicFetchError('Malformed DNS response') from exc
        if not addr.is_global:
            raise PublicFetchError('Private or reserved DNS address refused')
        ips.append(str(addr))
    return ips[0]


class PinnedHTTPSConnection(http.client.HTTPSConnection):
    def __init__(self, hostname: str, pinned_ip: str, timeout: int):
        super().__init__(hostname, port=443, timeout=timeout,
                         context=ssl.create_default_context())
        self._pinned_ip = pinned_ip

    def connect(self):
        # Critical: use the already checked IP, do NOT re-resolve on connect.
        plain = socket.create_connection((self._pinned_ip, 443), self.timeout)
        try:
            self.sock = self._context.wrap_socket(plain, server_hostname=self.host)
        except BaseException:
            plain.close()
            raise


def read_public_https(url: str, confirmed_hostname: str, *, consent: bool = False,
                      resolver=None, connection_factory=None, timeout: int = 6) -> dict:
    if consent is not True:
        raise PublicFetchError('Explicit consent for this one GET request is required')
    if type(timeout) is not int or not 1 <= timeout <= MAX_TIMEOUT:
        raise PublicFetchError('Invalid request timeout')
    hostname, target = check_public_url(url, confirmed_hostname)
    ip = checked_dns(hostname, resolver=resolver)
    conn = (connection_factory or PinnedHTTPSConnection)(hostname, ip, timeout)
    try:
        conn.request('GET', target, headers={
            'Host': hostname, 'Accept': 'text/html,text/plain',
            'Accept-Encoding': 'identity', 'User-Agent': 'AIWACK-public-research/1.0',
            'Connection': 'close',
        })
        response = conn.getresponse()
        if response.status != 200:
            raise PublicFetchError('HTTP status is not 200 (redirects are never followed)')
        content_type = response.getheader('Content-Type', '').split(';')[0].strip().lower()
        if content_type not in ('text/plain', 'text/html'):
            raise PublicFetchError('Only HTML or plain text responses are permitted')
        if response.getheader('Content-Encoding', 'identity').strip().lower() not in ('', 'identity'):
            raise PublicFetchError('Encoded responses are not accepted')
        size_text = response.getheader('Content-Length')
        if size_text:
            try:
                size = int(size_text)
            except (TypeError, ValueError) as exc:
                raise PublicFetchError('Invalid Content-Length') from exc
            if not 0 <= size <= MAX_RESPONSE_BYTES:
                raise PublicFetchError('Response is over size limit')
        raw = response.read(MAX_RESPONSE_BYTES + 1)
        if not 1 <= len(raw) <= MAX_RESPONSE_BYTES:
            raise PublicFetchError('Empty or over-size response')
        # Decode conservative UTF-8; never treat pages as executable code.
        charset = response.getheader('Content-Type', '').lower()
        if 'charset=' in charset and 'charset=utf-8' not in charset and 'charset="utf-8"' not in charset:
            raise PublicFetchError('Only UTF-8 charset is supported')
        text = raw.decode('utf-8-sig', 'replace')
        return {'url': url, 'hostname': hostname, 'pinned_ip': ip,
                'media_type': content_type, 'raw_sha256': hashlib.sha256(raw).hexdigest(),
                'raw_size': len(raw), 'content': text, 'http_status': 200,
                'fetched_over_https': True, 'independently_fact_checked': False,
                'server_identity': 'TLS-hostname-validated; source assertions unverified'}
    except (OSError, ssl.SSLError, http.client.HTTPException) as exc:
        raise PublicFetchError('HTTPS read failed; no verified source record') from exc
    finally:
        conn.close()


def initialize(con: sqlite3.Connection) -> None:
    con.execute('''CREATE TABLE IF NOT EXISTS public_web_research_receipts (
         id INTEGER PRIMARY KEY AUTOINCREMENT,
         capture_id INTEGER NOT NULL UNIQUE REFERENCES offline_research_captures(id),
         hostname TEXT NOT NULL, pinned_ip TEXT NOT NULL, http_status INTEGER NOT NULL CHECK(http_status=200),
         raw_sha256 TEXT NOT NULL CHECK(length(raw_sha256)=64),
         raw_size INTEGER NOT NULL CHECK(raw_size BETWEEN 1 AND 131072),
         source_authenticity TEXT NOT NULL DEFAULT 'unverified' CHECK(source_authenticity='unverified'),
         created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)''')
    for action in ('UPDATE', 'DELETE'):
        con.execute(f'''CREATE TRIGGER IF NOT EXISTS public_web_receipt_no_{action.lower()}
          BEFORE {action} ON public_web_research_receipts BEGIN
          SELECT RAISE(ABORT,'public web research receipts are append only'); END''')


def save_success(con: sqlite3.Connection, result: dict, title: str) -> dict:
    """Persist only successfully obtained bytes; retain 'unverified' source label."""
    from desktop.research_captures import add
    kind = 'html_snapshot' if result['media_type'] == 'text/html' else 'manual_text'
    capture_id = add(con, result['url'], title, result['content'], kind)
    con.execute('''INSERT INTO public_web_research_receipts
        (capture_id,hostname,pinned_ip,http_status,raw_sha256,raw_size)
        VALUES(?,?,?,?,?,?)''', (capture_id,result['hostname'],result['pinned_ip'],200,
                                  result['raw_sha256'],result['raw_size']))
    return {'capture_id': capture_id, 'http_status': 200,
            'raw_sha256': result['raw_sha256'], 'source_verified': False,
            'bytes': result['raw_size']}
