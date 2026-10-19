"""Owner-authorized read-only recheck of an explicitly selected queue JSON.

The self-checksum is NOT an authenticated signature. Only local records are
compared; no DNS/HTTP, URL fetching, imports, or database modifications.
"""
from __future__ import annotations

from pathlib import Path

from desktop.research_followup_exports import (
    MAX_EXPORT_BYTES, build_full_queue_report, verify_followup_export,
)
from desktop.research_verification import _read_local_json

PREVIEW_LIMIT = 20


def _index_items(report: dict) -> dict[str, dict]:
    return {item['linked_url']: item for item in report['items']}


def inspect_followup_export_file(store, filename: str | Path) -> dict:
    """Check one bounded JSON and compare using the saved filter/scope.

    URL lists are truncated in the UI result, but counts use the entire capped
    2,000-link sample. Report equality includes counts, order and review notes.
    """
    store.require_permission('company:manage')  # before probing the path
    path, raw = _read_local_json(filename, max_bytes=MAX_EXPORT_BYTES)
    exported = verify_followup_export(raw)
    with store._connect() as con:
        current = build_full_queue_report(
            con, include_archived=exported['include_archived_referrers'],
            review_filter=exported['review_filter'])
    old = _index_items(exported)
    now = _index_items(current)
    added = sorted(now.keys() - old.keys())
    missing = sorted(old.keys() - now.keys())
    changed = sorted(url for url in old.keys() & now.keys() if old[url] != now[url])
    unchanged = len(old.keys() & now.keys()) - len(changed)
    return {
        'filename': path.name,
        'checksum_matches': True,
        'local_report_matches': exported == current,
        'exported_url_count': len(old),
        'current_url_count': len(now),
        'added_url_count': len(added),
        'missing_url_count': len(missing),
        'changed_url_count': len(changed),
        'unchanged_url_count': unchanged,
        'added_urls_preview': added[:PREVIEW_LIMIT],
        'missing_urls_preview': missing[:PREVIEW_LIMIT],
        'changed_urls_preview': changed[:PREVIEW_LIMIT],
        'metadata_or_order_differs': exported != current and not (added or missing or changed),
        'review_filter': exported['review_filter'],
        'include_archived_referrers': exported['include_archived_referrers'],
        'source_authenticity_verified': False,
        'network_accessed': False,
    }
