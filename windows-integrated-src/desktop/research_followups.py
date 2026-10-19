"""Bounded, read-only offline follow-up queue for saved HTML link *strings*.

No DNS, HTTP, browser, local file access, or claim of source authenticity.
An exact stored URL match is only a possible local copy, not a verified link.
"""
from __future__ import annotations

from collections import defaultdict
import sqlite3

MAX_SCANNED_LINKS = 2000
MAX_REPORTED_URLS = 40
MAX_REFERRER_IDS = 5


def build_followup_queue(con: sqlite3.Connection, *, include_archived: bool = False,
                         limit: int = MAX_REPORTED_URLS,
                         review_filter: str = 'all', page: int = 1) -> dict:
    """Prioritize URL strings requiring manual review; never fetch any URL.

    A bounded newest-first link sample is used, not a complete DB audit.
    Statuses distinguish missing local copies, archived-only copies, and
    multiple active copies; a single local match is NOT source validation.
    """
    if (type(include_archived) is not bool or type(limit) is not int or not 1 <= limit <= 40
            or type(review_filter) is not str or review_filter not in ('all', 'pending', 'deferred')
            or type(page) is not int or not 1 <= page <= MAX_SCANNED_LINKS):
        raise ValueError('후속 조사 목록 옵션이 유효하지 않습니다.')
    con.row_factory = sqlite3.Row
    links = con.execute('''SELECT l.capture_id,l.linked_url
        FROM offline_research_html_links AS l
        JOIN offline_research_captures AS c ON c.id=l.capture_id
        WHERE (? OR c.archived_at IS NULL)
        ORDER BY l.capture_id DESC,l.position ASC LIMIT ?''',
        (int(include_archived), MAX_SCANNED_LINKS + 1)).fetchall()
    truncated_scan = len(links) > MAX_SCANNED_LINKS
    # Deduplicate references per capture. The link inventory itself enforces
    # (capture_id,linked_url) uniqueness, but don't rely on that for reporting.
    referrers: dict[str, set[int]] = defaultdict(set)
    for link in links[:MAX_SCANNED_LINKS]:
        referrers[link['linked_url']].add(link['capture_id'])
    counts: dict[str, tuple[int, int]] = {}
    urls = sorted(referrers)
    # SQLite variable count is limited on older Windows builds: use 250 binds.
    for offset in range(0, len(urls), 250):
        chunk = urls[offset:offset + 250]
        if not chunk:
            continue
        placeholders = ','.join('?' for _ in chunk)
        for row in con.execute(f'''SELECT source_url,
            SUM(CASE WHEN archived_at IS NULL THEN 1 ELSE 0 END) AS active_count,
            SUM(CASE WHEN archived_at IS NOT NULL THEN 1 ELSE 0 END) AS archived_count
            FROM offline_research_captures
            WHERE source_url IN ({placeholders}) GROUP BY source_url''', chunk):
            counts[row['source_url']] = (row['active_count'], row['archived_count'])
    priority = {'unregistered': 0, 'archived_only': 1,
                'multiple_active': 2, 'one_active': 3}
    summary = {key: 0 for key in priority}
    entries = []
    for url, ids in referrers.items():
        active, archived = counts.get(url, (0, 0))
        status = ('unregistered' if active + archived == 0 else
                  'archived_only' if active == 0 else
                  'multiple_active' if active > 1 else 'one_active')
        summary[status] += 1
        entries.append({'linked_url': url, 'status': status,
                        'referrer_count': len(ids),
                        'referrer_ids': sorted(ids, reverse=True)[:MAX_REFERRER_IDS],
                        'active_candidate_count': active,
                        'archived_candidate_count': archived})
    entries.sort(key=lambda item: (priority[item['status']],
                                   -item['referrer_count'], item['linked_url']))
    # Manual 'deferred' is only a human workflow marker. Filter before
    # limiting results so the first 40 deferred URLs cannot hide pending URLs.
    from desktop.research_followup_notes import latest_for_urls, latest_actions_for_queue
    actions = latest_actions_for_queue(con, urls)
    deferred_count = sum(actions.get(url) == 'deferred' for url in urls)
    if review_filter == 'pending':
        selected = [entry for entry in entries if actions.get(entry['linked_url']) != 'deferred']
    elif review_filter == 'deferred':
        selected = [entry for entry in entries if actions.get(entry['linked_url']) == 'deferred']
    else:
        selected = entries
    # One-based pages are applied AFTER priority sorting and manual triage filtering.
    # A page is a bounded view of the sampled inventory, never a remote audit.
    page_count = max(1, (len(selected) + limit - 1) // limit)
    start = (page - 1) * limit
    displayed = selected[start:start + limit]
    latest = latest_for_urls(con, [entry['linked_url'] for entry in displayed])
    for entry in displayed:
        entry['manual_review'] = latest.get(entry['linked_url'])
    return {'items': displayed, 'status_counts': summary,
            'scanned_link_count': min(len(links), MAX_SCANNED_LINKS),
            'unique_url_count': len(urls),
            'scan_truncated': truncated_scan,
            'results_truncated': start + limit < len(selected),
            'page': page, 'page_count': page_count,
            'filtered_url_count': len(selected),
            'has_previous_page': page > 1,
            'has_next_page': start + limit < len(selected),
            'page_out_of_range': page > page_count,
            'review_filter': review_filter,
            'review_counts': {'pending': len(urls) - deferred_count,
                              'deferred': deferred_count},
            'include_archived_referrers': include_archived,
            'source_authenticity_verified': False,
            'network_accessed': False}
