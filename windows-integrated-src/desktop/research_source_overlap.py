"""Stage54 partial: bounded *offline* overlap checks of stored research evidence.

Equal local text hashes or imported-file hashes can expose repeated material;
multiple body hashes for a claimed URL can flag local version differences.
None of these facts proves independent sources, website identity, or truth.
No file is reopened, no URL is resolved, and no network connection is made.
"""
from __future__ import annotations

from collections import defaultdict
import sqlite3

MAX_SCANNED_CAPTURES = 2000
MAX_DISPLAYED_GROUPS = 50
MAX_SAMPLE_IDS = 5
MAX_SAMPLE_URLS = 3


def build_source_overlap_report(con: sqlite3.Connection, *,
                                include_archived: bool = False,
                                limit: int = 25) -> dict:
    """Find overlaps within newest N local captures, never a full source audit."""
    if type(include_archived) is not bool or type(limit) is not int or not 1 <= limit <= MAX_DISPLAYED_GROUPS:
        raise ValueError('자료 중복 점검 옵션이 유효하지 않습니다.')
    con.row_factory = sqlite3.Row
    rows = con.execute('''SELECT c.id, c.source_url, c.content_sha256,
                                  i.raw_sha256
        FROM offline_research_captures AS c
        LEFT JOIN offline_research_local_imports AS i ON i.capture_id=c.id
        WHERE (? OR c.archived_at IS NULL)
        ORDER BY c.id DESC LIMIT ?''',
        (int(include_archived), MAX_SCANNED_CAPTURES + 1)).fetchall()
    truncated = len(rows) > MAX_SCANNED_CAPTURES
    rows = rows[:MAX_SCANNED_CAPTURES]
    by_body: dict[str, list[sqlite3.Row]] = defaultdict(list)
    by_source: dict[str, list[sqlite3.Row]] = defaultdict(list)
    by_raw: dict[str, list[sqlite3.Row]] = defaultdict(list)
    for row in rows:
        by_body[row['content_sha256']].append(row)
        by_source[row['source_url']].append(row)
        if row['raw_sha256'] is not None:
            by_raw[row['raw_sha256']].append(row)

    categories = ('same_body_different_claimed_urls',
                  'different_bodies_same_claimed_url',
                  'same_imported_bytes_different_claimed_urls')
    groups: list[dict] = []
    counts = dict.fromkeys(categories, 0)

    def collect(category: str, groups_by_key: dict, distinct_field: str):
        for key, members in groups_by_key.items():
            distinct = {row[distinct_field] for row in members}
            if len(distinct) < 2:
                continue
            counts[category] += 1
            groups.append({
                'category': category,
                # Hashes are local equality markers, never signed attestations.
                'key': key if category == 'different_bodies_same_claimed_url' else key[:12],
                'capture_count': len(members),
                'distinct_value_count': len(distinct),
                'capture_ids': [row['id'] for row in members[:MAX_SAMPLE_IDS]],
                'claimed_urls': sorted({row['source_url'] for row in members})[:MAX_SAMPLE_URLS],
            })

    collect(categories[0], by_body, 'source_url')
    collect(categories[1], by_source, 'content_sha256')
    collect(categories[2], by_raw, 'source_url')
    rank = {category: index for index, category in enumerate(categories)}
    groups.sort(key=lambda g: (rank[g['category']], -g['distinct_value_count'],
                               -g['capture_count'], g['key']))
    return {
        'items': groups[:limit],
        'category_counts': counts,
        'group_count': len(groups),
        'displayed_group_count': min(len(groups), limit),
        'groups_truncated': len(groups) > limit,
        'scanned_capture_count': len(rows),
        'scan_truncated': truncated,
        'sample_limit': MAX_SCANNED_CAPTURES,
        'include_archived': include_archived,
        'source_independence_verified': False,
        'source_authenticity_verified': False,
        'original_file_bytes_rechecked': False,
        'network_accessed': False,
    }
