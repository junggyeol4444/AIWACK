"""Owner-approved, offline JSON audit of ALL sampled stored-URL warning flags.

This exports only URL strings, local copy status and passive warning codes.
No DNS, fetching, automatic destinations, trusted-origin claims or DB writes.
The SHA-256 is an accidental-change check, NOT a signature or attestation.
"""
from __future__ import annotations

from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import sqlite3

from desktop.research_followup_exports import (
    MAX_EXPORT_BYTES, MAX_SCANNED_LINKS, _canonical, build_full_queue_report,
)
from desktop.research_url_preflight import classify_stored_url
from desktop.research_verification import _read_local_json

FORMAT = 'aiwack.offline_url_preflight.v1'
CHECKSUM_SCOPE = 'canonical UTF-8 JSON report only; not a signature'
STATUS_CODES = ('unregistered', 'archived_only', 'multiple_active', 'one_active')
PREVIEW_LIMIT = 20


def build_preflight_export_report(con: sqlite3.Connection, *,
                                  include_archived: bool = False,
                                  review_filter: str = 'all') -> dict:
    """Use one SQLite snapshot for all pages; never truncate to GUI's 40."""
    queue = build_full_queue_report(con, include_archived=include_archived,
                                    review_filter=review_filter)
    warnings = []
    counts: Counter[str] = Counter()
    for item in queue['items']:
        flags = classify_stored_url(item['linked_url'])
        if flags:
            counts.update(flags)
            warnings.append({'linked_url': item['linked_url'],
                             'status': item['status'], 'warning_codes': list(flags)})
    warnings.sort(key=lambda item: (-len(item['warning_codes']), item['linked_url']))
    return {
        'items': warnings,
        'warning_url_count': len(warnings),
        'warning_counts': dict(sorted(counts.items())),
        'filtered_url_count': queue['filtered_url_count'],
        'scanned_link_count': queue['scanned_link_count'],
        'scan_truncated': queue['scan_truncated'],
        'sample_limit': MAX_SCANNED_LINKS,
        'review_filter': queue['review_filter'],
        'include_archived_referrers': queue['include_archived_referrers'],
        'dns_checked': False,
        'network_accessed': False,
        'source_authenticity_verified': False,
        'safe_to_fetch_verified': False,
    }


def _validate_report(report: dict) -> None:
    if (type(report) is not dict or
            report.get('review_filter') not in ('all', 'pending', 'deferred') or
            type(report.get('include_archived_referrers')) is not bool or
            type(report.get('scan_truncated')) is not bool or
            type(report.get('sample_limit')) is not int or
            report['sample_limit'] != MAX_SCANNED_LINKS or
            any(report.get(key) is not False for key in (
                'dns_checked', 'network_accessed',
                'source_authenticity_verified', 'safe_to_fetch_verified'))):
        raise ValueError('URL 사전 점검 보고서 메타데이터가 올바르지 않습니다.')
    items = report.get('items')
    filtered = report.get('filtered_url_count')
    scanned = report.get('scanned_link_count')
    if (type(items) is not list or len(items) > MAX_SCANNED_LINKS or
            type(filtered) is not int or not len(items) <= filtered <= MAX_SCANNED_LINKS or
            type(scanned) is not int or not filtered <= scanned <= MAX_SCANNED_LINKS or
            type(report.get('warning_url_count')) is not int or
            report['warning_url_count'] != len(items) or
            type(report.get('warning_counts')) is not dict):
        raise ValueError('URL 사전 점검 보고서 개수가 올바르지 않습니다.')
    seen: set[str] = set()
    counts: Counter[str] = Counter()
    order = []
    for item in items:
        if (type(item) is not dict or type(item.get('linked_url')) is not str or
                item['linked_url'] in seen or len(item['linked_url']) > 2048 or
                item.get('status') not in STATUS_CODES or
                type(item.get('warning_codes')) is not list):
            raise ValueError('URL 사전 점검 항목 형식이 올바르지 않습니다.')
        url = item['linked_url']
        expected = classify_stored_url(url)
        if not expected or item['warning_codes'] != list(expected):
            raise ValueError('URL 사전 점검 경고 코드가 현재 분류 규칙과 일치하지 않습니다.')
        seen.add(url)
        counts.update(expected)
        order.append((-len(expected), url))
    if (order != sorted(order) or
            report['warning_counts'] != dict(sorted(counts.items()))):
        raise ValueError('URL 사전 점검 집계 또는 정렬이 올바르지 않습니다.')


def encode_preflight_export(report: dict) -> bytes:
    _validate_report(report)
    envelope = {
        'format': FORMAT,
        'report': report,
        'report_sha256': hashlib.sha256(_canonical(report)).hexdigest(),
        'checksum_scope': CHECKSUM_SCOPE,
    }
    raw = (json.dumps(envelope, ensure_ascii=False, sort_keys=True,
                      indent=2, allow_nan=False) + '\n').encode('utf-8')
    if len(raw) > MAX_EXPORT_BYTES:
        raise ValueError('URL 사전 점검 JSON이 허용 크기를 초과했습니다.')
    return raw


def verify_preflight_export(raw: bytes) -> dict:
    if type(raw) is not bytes or not 0 < len(raw) <= MAX_EXPORT_BYTES:
        raise ValueError('URL 사전 점검 JSON 크기가 올바르지 않습니다.')
    try:
        envelope = json.loads(raw.decode('utf-8'))
    except (UnicodeError, ValueError) as exc:
        raise ValueError('URL 사전 점검 JSON을 읽을 수 없습니다.') from exc
    if (type(envelope) is not dict or envelope.get('format') != FORMAT or
            envelope.get('checksum_scope') != CHECKSUM_SCOPE or
            type(envelope.get('report_sha256')) is not str):
        raise ValueError('지원하지 않는 URL 사전 점검 JSON 형식입니다.')
    report = envelope.get('report')
    _validate_report(report)
    if hashlib.sha256(_canonical(report)).hexdigest() != envelope['report_sha256']:
        raise ValueError('URL 사전 점검 JSON 체크섬이 일치하지 않습니다.')
    return report


def save_preflight_export(report: dict, destination: str | Path) -> Path:
    """Only explicitly chosen absolute local files, exclusively created."""
    if not isinstance(destination, (str, Path)) or not str(destination).strip():
        raise ValueError('저장할 로컬 JSON 경로를 직접 선택해야 합니다.')
    raw_path = os.fspath(destination)
    if '\x00' in raw_path or raw_path.startswith(('\\\\', '//')):
        raise ValueError('네트워크 공유 경로에 저장할 수 없습니다.')
    path = Path(destination).expanduser()
    if not path.is_absolute():
        raise ValueError('절대 경로의 로컬 파일만 선택할 수 있습니다.')
    if os.name == 'nt':
        import ctypes
        from ctypes import wintypes
        drive_type = ctypes.windll.kernel32.GetDriveTypeW(wintypes.LPCWSTR(path.anchor))
        if drive_type in (0, 1, 4):
            raise ValueError('네트워크 또는 확인되지 않은 드라이브는 허용하지 않습니다.')
    raw = encode_preflight_export(report)
    created = False
    try:
        with path.open('xb') as stream:
            created = True
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
    except BaseException:
        if created:
            path.unlink(missing_ok=True)
        raise
    return path


def inspect_preflight_export_file(store, filename: str | Path) -> dict:
    """Check owner-selected JSON and compare warning inventory to local DB."""
    store.require_permission('company:manage')  # before path inspection
    path, raw = _read_local_json(filename, max_bytes=MAX_EXPORT_BYTES)
    old_report = verify_preflight_export(raw)
    with store._connect() as con:
        current = build_preflight_export_report(
            con, include_archived=old_report['include_archived_referrers'],
            review_filter=old_report['review_filter'])
    old = {item['linked_url']: item for item in old_report['items']}
    now = {item['linked_url']: item for item in current['items']}
    added = sorted(now.keys() - old.keys())
    missing = sorted(old.keys() - now.keys())
    changed = sorted(url for url in old.keys() & now.keys() if old[url] != now[url])
    return {
        'filename': path.name,
        'checksum_matches': True,
        'local_report_matches': old_report == current,
        'exported_warning_url_count': len(old),
        'current_warning_url_count': len(now),
        'added_warning_url_count': len(added),
        'missing_warning_url_count': len(missing),
        'changed_warning_url_count': len(changed),
        'added_urls_preview': added[:PREVIEW_LIMIT],
        'missing_urls_preview': missing[:PREVIEW_LIMIT],
        'changed_urls_preview': changed[:PREVIEW_LIMIT],
        'metadata_or_order_differs': old_report != current and not (added or missing or changed),
        'review_filter': old_report['review_filter'],
        'include_archived_referrers': old_report['include_archived_referrers'],
        'dns_checked': False,
        'network_accessed': False,
        'source_authenticity_verified': False,
        'safe_to_fetch_verified': False,
    }
