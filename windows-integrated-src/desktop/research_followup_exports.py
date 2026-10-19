"""Explicit local-only JSON handoff for the bounded HTML follow-up inventory.

This exports stored URL *strings* and owner-entered review notes, not web
research, live URL validation, or trusted evidence of website authenticity.
No network access, imports, database writes, or automatic file destinations.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import sqlite3

from desktop.research_followups import (
    MAX_REPORTED_URLS, MAX_SCANNED_LINKS, build_followup_queue,
)

FORMAT = 'aiwack.offline_followups.v1'
MAX_EXPORT_BYTES = 12_000_000
DISCLAIMER = 'offline URL strings and manual annotations only; no source authentication'


def _canonical(data: dict) -> bytes:
    return json.dumps(data, ensure_ascii=False, sort_keys=True,
                      separators=(',', ':'), allow_nan=False).encode('utf-8')


def build_full_queue_report(con: sqlite3.Connection, *,
                            include_archived: bool = False,
                            review_filter: str = 'all') -> dict:
    """Snapshot all pages of the same capped sample and human triage filter.

    BEGIN gives every page one SQLite read snapshot even if another connection
    changes review notes while the report is being assembled. No DB mutations.
    """
    if con.in_transaction:
        raise ValueError('독립적인 읽기 전용 트랜잭션이 필요합니다.')
    con.execute('BEGIN')
    try:
        first = build_followup_queue(con, include_archived=include_archived,
                                     review_filter=review_filter, page=1)
        items = list(first['items'])
        for page in range(2, first['page_count'] + 1):
            part = build_followup_queue(con, include_archived=include_archived,
                                        review_filter=review_filter, page=page)
            if (part['filtered_url_count'] != first['filtered_url_count'] or
                    part['page_count'] != first['page_count'] or part['page_out_of_range']):
                raise ValueError('후속 조사 목록의 페이지 정보가 일치하지 않습니다.')
            items.extend(part['items'])
        if len(items) != first['filtered_url_count'] or len(items) > MAX_SCANNED_LINKS:
            raise ValueError('후속 조사 목록 개수가 일치하지 않습니다.')
        return {
            'items': items,
            'include_archived_referrers': first['include_archived_referrers'],
            'review_filter': first['review_filter'],
            'status_counts': first['status_counts'],
            'review_counts': first['review_counts'],
            'scanned_link_count': first['scanned_link_count'],
            'unique_url_count': first['unique_url_count'],
            'filtered_url_count': first['filtered_url_count'],
            'scan_truncated': first['scan_truncated'],
            'sample_limit': MAX_SCANNED_LINKS,
            'page_size': MAX_REPORTED_URLS,
            'source_authenticity_verified': False,
            'network_accessed': False,
        }
    finally:
        # End our read-only snapshot; never commit or mutate the database.
        con.rollback()


def _validate_report(report: dict) -> None:
    if (type(report) is not dict or report.get('network_accessed') is not False or
            report.get('source_authenticity_verified') is not False or
            report.get('review_filter') not in ('all', 'pending', 'deferred') or
            type(report.get('include_archived_referrers')) is not bool or
            report.get('sample_limit') != MAX_SCANNED_LINKS or
            report.get('page_size') != MAX_REPORTED_URLS or
            type(report.get('scan_truncated')) is not bool):
        raise ValueError('오프라인 후속 조사 보고서 형식이 올바르지 않습니다.')
    items = report.get('items')
    if (type(items) is not list or len(items) > MAX_SCANNED_LINKS or
            type(report.get('filtered_url_count')) is not int or
            len(items) != report['filtered_url_count'] or
            type(report.get('unique_url_count')) is not int or
            not len(items) <= report['unique_url_count'] <= MAX_SCANNED_LINKS or
            type(report.get('scanned_link_count')) is not int or
            not 0 <= report['scanned_link_count'] <= MAX_SCANNED_LINKS or
            type(report.get('status_counts')) is not dict or
            type(report.get('review_counts')) is not dict):
        raise ValueError('후속 조사 보고서 항목 수가 올바르지 않습니다.')
    seen = set()
    for item in items:
        if (type(item) is not dict or type(item.get('linked_url')) is not str or
                not 8 <= len(item['linked_url']) <= 2048 or
                item['linked_url'] in seen or
                item.get('status') not in ('unregistered', 'archived_only',
                                          'multiple_active', 'one_active') or
                type(item.get('referrer_count')) is not int or
                type(item.get('referrer_ids')) is not list or
                type(item.get('active_candidate_count')) is not int or
                type(item.get('archived_candidate_count')) is not int or
                (item.get('manual_review') is not None and
                 type(item['manual_review']) is not dict)):
            raise ValueError('후속 조사 보고서 URL 항목이 올바르지 않습니다.')
        seen.add(item['linked_url'])


def encode_followup_export(report: dict) -> bytes:
    """Deterministic UTF-8 export with a self-checksum, NOT a signature."""
    _validate_report(report)
    envelope = {
        'format': FORMAT,
        'report': report,
        'report_sha256': hashlib.sha256(_canonical(report)).hexdigest(),
        'checksum_scope': 'canonical UTF-8 JSON report only; not a signature',
        'source_authenticity': DISCLAIMER,
    }
    encoded = (json.dumps(envelope, ensure_ascii=False, sort_keys=True,
                          indent=2, allow_nan=False) + '\n').encode('utf-8')
    if len(encoded) > MAX_EXPORT_BYTES:
        raise ValueError('후속 조사 JSON이 허용 크기를 초과했습니다.')
    return encoded


def verify_followup_export(raw: bytes) -> dict:
    """Verify structural flags and checksum only; never contact a website."""
    if type(raw) is not bytes or not 0 < len(raw) <= MAX_EXPORT_BYTES:
        raise ValueError('후속 조사 JSON 크기가 올바르지 않습니다.')
    try:
        envelope = json.loads(raw.decode('utf-8'))
    except (UnicodeError, ValueError) as exc:
        raise ValueError('후속 조사 JSON을 읽을 수 없습니다.') from exc
    if (type(envelope) is not dict or envelope.get('format') != FORMAT or
            envelope.get('checksum_scope') != 'canonical UTF-8 JSON report only; not a signature' or
            envelope.get('source_authenticity') != DISCLAIMER or
            type(envelope.get('report_sha256')) is not str):
        raise ValueError('지원하지 않는 후속 조사 JSON 형식입니다.')
    report = envelope.get('report')
    _validate_report(report)
    if hashlib.sha256(_canonical(report)).hexdigest() != envelope['report_sha256']:
        raise ValueError('후속 조사 JSON 체크섬이 일치하지 않습니다.')
    return report


def save_followup_export(report: dict, destination: str | Path) -> Path:
    """Exclusive creation at an owner-selected local path; no overwrites."""
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
    raw = encode_followup_export(report)
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
