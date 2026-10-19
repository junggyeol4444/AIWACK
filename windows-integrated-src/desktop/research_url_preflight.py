"""Passive, offline preflight of *stored* research URLs (stage 54 partial).

This is a triage aid, NOT an allowlist or a safe-to-fetch decision. Even a
normal-looking public hostname may resolve to a private address or change after
DNS resolution; no hostname is resolved and no connection is ever made here.
"""
from __future__ import annotations

from collections import Counter
import ipaddress
import re
import sqlite3
from urllib.parse import urlsplit

from desktop.research_followup_exports import build_full_queue_report

MAX_DISPLAYED = 40
# A numeric hostname can be interpreted as an IPv4 address by some clients
# even when Python's ipaddress module rejects its non-canonical spelling.
_NUMERIC_HOST = re.compile(r'(?i)(?:0x[0-9a-f]+|0[0-7]+|[0-9]+)(?:\.(?:0x[0-9a-f]+|0[0-7]+|[0-9]+))*\.?\Z')


def classify_stored_url(value: str) -> tuple[str, ...]:
    """Return stable warning codes without opening, resolving, or trusting URL.

    Empty flags only mean this conservative *string check* saw no listed issue.
    They NEVER mean that opening the URL would be safe or authorized.
    """
    if type(value) is not str or not 1 <= len(value) <= 2048:
        return ('invalid_url',)
    try:
        parsed = urlsplit(value)
        host = parsed.hostname
        if (parsed.scheme.lower() not in ('http', 'https') or not host or
                any(ord(c) < 33 or ord(c) == 127 for c in value)):
            return ('invalid_url',)
        port = parsed.port  # Forces validation of malformed port strings.
    except (ValueError, UnicodeError):
        return ('invalid_url',)
    flags: list[str] = []
    if parsed.username is not None or parsed.password is not None:
        flags.append('embedded_credentials')
    if port is not None and port not in (80, 443):
        flags.append('nonstandard_port')
    normalized = host.lower().rstrip('.')
    if host.endswith('.'):
        flags.append('trailing_dot_hostname')
    if '%' in host:
        flags.append('encoded_or_scoped_hostname')
    if any(ord(c) > 127 for c in host) or 'xn--' in host.lower():
        flags.append('internationalized_hostname')
    try:
        address = ipaddress.ip_address(normalized)
    except ValueError:
        address = None
    if address is not None:
        # A globally-routable literal IP is still a manual-review candidate.
        flags.append('ip_literal')
        if not address.is_global:
            flags.append('non_global_ip_literal')
    elif _NUMERIC_HOST.fullmatch(normalized):
        flags.append('ambiguous_numeric_hostname')
    elif (normalized == 'localhost' or normalized.endswith('.localhost') or
          normalized == 'localdomain' or normalized.endswith('.localdomain') or
          normalized.endswith(('.local', '.internal', '.home.arpa'))):
        flags.append('local_name')
    elif '.' not in normalized:
        flags.append('single_label_hostname')
    return tuple(flags)


def build_followup_url_preflight(con: sqlite3.Connection, *,
                                 include_archived: bool = False,
                                 review_filter: str = 'all',
                                 limit: int = MAX_DISPLAYED) -> dict:
    """Summarize warnings across ALL URLs in the bounded SQLite snapshot.

    Filtering is applied before scanning. Warning rows are sorted by number of
    distinct warning codes then URL; the returned counts cover all filtered
    URLs even when the displayed warning list is truncated.
    """
    if type(limit) is not int or not 1 <= limit <= MAX_DISPLAYED:
        raise ValueError('URL 경고 표시 개수는 1~40이어야 합니다.')
    report = build_full_queue_report(con, include_archived=include_archived,
                                     review_filter=review_filter)
    counts: Counter[str] = Counter()
    warnings: list[dict] = []
    for item in report['items']:
        flags = classify_stored_url(item['linked_url'])
        if flags:
            counts.update(flags)
            warnings.append({'linked_url': item['linked_url'],
                             'warning_codes': list(flags),
                             'status': item['status']})
    warnings.sort(key=lambda item: (-len(item['warning_codes']), item['linked_url']))
    return {
        'items': warnings[:limit],
        'warning_url_count': len(warnings),
        'warning_counts': dict(sorted(counts.items())),
        'displayed_warning_count': min(limit, len(warnings)),
        'warnings_truncated': len(warnings) > limit,
        'filtered_url_count': report['filtered_url_count'],
        'scanned_link_count': report['scanned_link_count'],
        'scan_truncated': report['scan_truncated'],
        'review_filter': report['review_filter'],
        'include_archived_referrers': report['include_archived_referrers'],
        'sample_limit': report['sample_limit'],
        'dns_checked': False,
        'network_accessed': False,
        'source_authenticity_verified': False,
        'safe_to_fetch_verified': False,
    }
