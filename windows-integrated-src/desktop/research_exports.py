"""Explicit, offline JSON export of quoted local evidence.

The checksum detects accidental changes to the exported JSON *only*; it is
not a signature, proof of original online provenance, or verification of facts.
No network access, database writes, or automatic destinations.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

EXPORT_FORMAT = 'aiwack.offline_evidence.v1'
MAX_EXPORT_BYTES = 1_000_000


def _canonical(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(',', ':'), allow_nan=False).encode('utf-8')


def encode_evidence_export(report: dict) -> bytes:
    """Produce deterministic, checksum-bound UTF-8 JSON from a local report."""
    if (not isinstance(report, dict) or
            report.get('source_authenticity_verified') is not False or
            report.get('network_accessed') is not False or
            not isinstance(report.get('hits'), list) or
            not isinstance(report.get('report_text'), str) or
            not isinstance(report.get('query'), str)):
        raise ValueError('미검증 오프라인 근거 보고서만 내보낼 수 있습니다.')
    digest = hashlib.sha256(_canonical(report)).hexdigest()
    envelope = {
        'format': EXPORT_FORMAT,
        'report': report,
        'report_sha256': digest,
        'checksum_scope': 'canonical UTF-8 JSON report only; not a signature',
        'source_authenticity': 'unverified; no online verification',
    }
    encoded = (json.dumps(envelope, ensure_ascii=False, sort_keys=True,
                          indent=2, allow_nan=False) + '\n').encode('utf-8')
    if len(encoded) > MAX_EXPORT_BYTES:
        raise ValueError('내보내기 데이터가 허용 크기를 초과했습니다.')
    return encoded


def verify_evidence_export(raw: bytes) -> dict:
    """Check exported byte structure/checksum, not online source authenticity."""
    if not isinstance(raw, bytes) or len(raw) > MAX_EXPORT_BYTES or not raw:
        raise ValueError('근거 파일 크기 또는 형식이 올바르지 않습니다.')
    try:
        envelope = json.loads(raw.decode('utf-8'))
    except (UnicodeError, ValueError) as exc:
        raise ValueError('근거 JSON을 읽을 수 없습니다.') from exc
    if (not isinstance(envelope, dict) or envelope.get('format') != EXPORT_FORMAT or
            envelope.get('checksum_scope') != 'canonical UTF-8 JSON report only; not a signature' or
            envelope.get('source_authenticity') != 'unverified; no online verification' or
            not isinstance(envelope.get('report_sha256'), str)):
        raise ValueError('지원하지 않는 근거 내보내기 형식입니다.')
    report = envelope.get('report')
    if (not isinstance(report, dict) or
            report.get('source_authenticity_verified') is not False or
            report.get('network_accessed') is not False or
            not isinstance(report.get('hits'), list) or
            not isinstance(report.get('report_text'), str) or
            not isinstance(report.get('query'), str)):
        raise ValueError('오프라인 근거 보고서 형식이 올바르지 않습니다.')
    if hashlib.sha256(_canonical(report)).hexdigest() != envelope['report_sha256']:
        raise ValueError('근거 JSON 체크섬이 일치하지 않습니다.')
    return report


def save_evidence_export(report: dict, destination: str | Path) -> Path:
    """Write only to an explicitly selected, previously non-existent file.

    Exclusive creation prevents silent overwrite and following existing symlinks.
    Parent directories are never created implicitly.
    """
    if not isinstance(destination, (str, Path)) or not str(destination).strip():
        raise ValueError('내보낼 파일 경로를 직접 선택해야 합니다.')
    path = Path(destination).expanduser()
    raw = encode_evidence_export(report)
    created = False
    try:
        with path.open('xb') as stream:
            created = True
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
    except Exception:
        if created:
            path.unlink(missing_ok=True)
        raise
    return path
