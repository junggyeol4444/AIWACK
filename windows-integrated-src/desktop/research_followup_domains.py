"""Offline host-level triage of stored HTML link *strings* (stage 54 partial).

No DNS, HTTP, domain ownership lookup, or website validation occurs. A hostname
is derived solely from the claimed URL; equal hostnames do not prove trust.
"""
from __future__ import annotations

from collections import defaultdict
from urllib.parse import urlsplit
import sqlite3

from desktop.research_followup_exports import build_full_queue_report

MAX_DOMAINS_DISPLAYED = 50
SAMPLE_URLS_PER_HOST = 3


def build_followup_domain_summary(con: sqlite3.Connection, *,
                                  include_archived: bool = False,
                                  review_filter: str = 'all',
                                  limit: int = 25) -> dict:
    """Group all URLs in the same capped SQLite snapshot by literal hostname.

    The queue's 2,000-link cap, status priority, and human review filter are
    preserved. This is an overview of the *sample*, not a full domain audit.
    """
    if type(limit) is not int or not 1 <= limit <= MAX_DOMAINS_DISPLAYED:
        raise ValueError('호스트 표시 개수는 1~50이어야 합니다.')
    # build_full_queue_report validates filter/scope and owns its read snapshot.
    report = build_full_queue_report(con, include_archived=include_archived,
                                     review_filter=review_filter)
    grouped: dict[str, list[dict]] = defaultdict(list)
    for item in report['items']:
        try:
            url = urlsplit(item['linked_url'])
            if url.scheme.lower() not in ('http', 'https') or not url.hostname:
                raise ValueError('유효하지 않은 URL')
            hostname = url.hostname.lower()
        except (ValueError, UnicodeError) as exc:
            raise ValueError('저장된 후속 조사 URL의 호스트를 분석할 수 없습니다.') from exc
        grouped[hostname].append(item)

    rows = []
    for host, items in grouped.items():
        status_counts = {status: sum(i['status'] == status for i in items)
                         for status in ('unregistered', 'archived_only',
                                        'multiple_active', 'one_active')}
        deferred = sum(bool(i['manual_review']) and
                       i['manual_review']['action'] == 'deferred' for i in items)
        rows.append({
            'hostname': host,
            'url_count': len(items),
            'referrer_count_total': sum(i['referrer_count'] for i in items),
            'status_counts': status_counts,
            'deferred_url_count': deferred,
            'pending_url_count': len(items) - deferred,
            'sample_urls': sorted(i['linked_url'] for i in items)[:SAMPLE_URLS_PER_HOST],
        })
    # Unregistered / archived-only candidates first; stable ties by hostname.
    rows.sort(key=lambda r: (-(r['status_counts']['unregistered'] +
                               r['status_counts']['archived_only']),
                             -r['url_count'], r['hostname']))
    return {
        'items': rows[:limit],
        'domain_count': len(rows),
        'displayed_domain_count': min(limit, len(rows)),
        'domains_truncated': len(rows) > limit,
        'filtered_url_count': report['filtered_url_count'],
        'scanned_link_count': report['scanned_link_count'],
        'scan_truncated': report['scan_truncated'],
        'review_filter': report['review_filter'],
        'include_archived_referrers': report['include_archived_referrers'],
        'sample_limit': report['sample_limit'],
        'source_authenticity_verified': False,
        'network_accessed': False,
    }
