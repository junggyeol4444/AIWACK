"""Read-only inspection of explicitly selected offline evidence JSON.

Self-checksum, local-DB equality and *candidate* differences are separate
checks. None authenticates an author, website or the underlying facts.
"""
from __future__ import annotations

import os
from pathlib import Path
import stat

from desktop.research_exports import MAX_EXPORT_BYTES, verify_evidence_export


def _read_local_json(filename: str | Path, *, max_bytes: int = MAX_EXPORT_BYTES) -> tuple[Path, bytes]:
    """Read bounded bytes from one regular local file, never a URL or share.

    On POSIX O_NOFOLLOW prevents final-component symlink substitution between
    lstat and open. Windows has no equivalent stdlib guarantee; fstat and
    second lstat reduce, but cannot eliminate, replacement races there.
    """
    if type(max_bytes) is not int or not 0 < max_bytes <= 20_000_000:
        raise ValueError('JSON 파일 크기 제한이 올바르지 않습니다.')
    if not isinstance(filename, (str, Path)) or not str(filename).strip():
        raise ValueError('검사할 로컬 JSON 파일을 직접 선택해야 합니다.')
    raw_path = os.fspath(filename)
    if '\x00' in raw_path or raw_path.startswith(('\\\\', '//')):
        raise ValueError('네트워크 공유 경로는 허용하지 않습니다.')
    path = Path(filename).expanduser()
    if not path.is_absolute():
        raise ValueError('절대 경로의 로컬 JSON 파일만 검사할 수 있습니다.')
    if os.name == 'nt':
        import ctypes
        from ctypes import wintypes
        drive_type = ctypes.windll.kernel32.GetDriveTypeW(wintypes.LPCWSTR(path.anchor))
        if drive_type in (0, 1, 4):
            raise ValueError('네트워크 드라이브 또는 확인되지 않은 드라이브는 허용하지 않습니다.')
    metadata = path.lstat()
    if not stat.S_ISREG(metadata.st_mode):
        raise ValueError('일반 로컬 JSON 파일만 검사할 수 있습니다 (링크 제외).')
    if not 0 < metadata.st_size <= max_bytes:
        raise ValueError('근거 JSON 파일 크기가 허용 범위를 벗어났습니다.')
    flags = (os.O_RDONLY | getattr(os, 'O_BINARY', 0) |
             getattr(os, 'O_NOFOLLOW', 0) | getattr(os, 'O_NONBLOCK', 0))
    try:
        fd = os.open(path, flags)
    except OSError as exc:
        raise ValueError('일반 로컬 JSON 파일만 안전하게 검사할 수 있습니다.') from exc
    try:
        before = os.fstat(fd)
        if (not stat.S_ISREG(before.st_mode) or
                (before.st_dev, before.st_ino) != (metadata.st_dev, metadata.st_ino)):
            raise ValueError('검사 중 파일이 변경되었거나 일반 파일이 아닙니다.')
        if not 0 < before.st_size <= max_bytes:
            raise ValueError('근거 JSON 파일 크기가 허용 범위를 벗어났습니다.')
        with os.fdopen(fd, 'rb', closefd=False) as stream:
            raw = stream.read(max_bytes + 1)
        after = os.fstat(fd)
        if (len(raw) != before.st_size or
                (before.st_size, before.st_mtime_ns, before.st_ino) !=
                (after.st_size, after.st_mtime_ns, after.st_ino)):
            raise ValueError('읽는 동안 파일이 변경되었습니다.')
        # Also reject a pathname replaced after opening (not just modified FD).
        current = path.lstat()
        if (not stat.S_ISREG(current.st_mode) or
                (current.st_dev, current.st_ino) != (before.st_dev, before.st_ino)):
            raise ValueError('검사 중 파일 경로가 변경되었습니다.')
        return path, raw
    finally:
        os.close(fd)


def _hit_map(report: dict) -> dict[int, dict]:
    """Index untrusted exported hits conservatively; never execute content."""
    result: dict[int, dict] = {}
    for hit in report['hits']:
        if not isinstance(hit, dict) or type(hit.get('capture_id')) is not int:
            raise ValueError('근거 JSON의 자료 ID 형식이 올바르지 않습니다.')
        capture_id = hit['capture_id']
        if capture_id < 1 or capture_id in result or len(result) >= 20:
            raise ValueError('근거 JSON의 자료 ID가 중복되거나 범위를 벗어났습니다.')
        result[capture_id] = hit
    return result


def _candidate_difference(exported: dict, current: dict, scope: str) -> dict:
    """Describe *observed* report differences, not their cause."""
    old = _hit_map(exported)
    now = _hit_map(current)
    common = old.keys() & now.keys()
    return {
        'compared_scope': scope,
        'added_capture_ids': sorted(now.keys() - old.keys()),
        'missing_capture_ids': sorted(old.keys() - now.keys()),
        'changed_capture_ids': sorted(key for key in common if old[key] != now[key]),
        'unchanged_hit_count': sum(old[key] == now[key] for key in common),
        'report_metadata_or_order_differs': (
            exported != current and
            [old[key] for key in old] == [now[key] for key in now] and
            not any(old[key] != now[key] for key in common)
        ),
        'is_causal_explanation': False,
    }


def inspect_export_file(store, filename: str | Path) -> dict:
    """Owner-only, read-only inspection; no imports, writes, or network calls."""
    store.require_permission('company:manage')  # before path existence probing
    path, raw = _read_local_json(filename)
    report = verify_evidence_export(raw)
    exported_hits = _hit_map(report)
    # Both scopes are needed because legacy v1 exports did not encode scope.
    active = store.local_research_evidence_report(report['query'], include_archived=False)
    archived = store.local_research_evidence_report(report['query'], include_archived=True)
    if report == active:
        scope = 'active'
    elif report == archived:
        scope = 'including_archived'
    else:
        scope = None
    # Choose a comparison candidate using ID overlap, then fewer changes.
    # This is NOT a claim about the original export scope or drift cause.
    candidates = [
        _candidate_difference(report, active, 'active'),
        _candidate_difference(report, archived, 'including_archived'),
    ]
    candidates.sort(key=lambda diff: (
        -diff['unchanged_hit_count'],
        len(diff['added_capture_ids']) + len(diff['missing_capture_ids']) +
        len(diff['changed_capture_ids']),
        diff['compared_scope'] != 'active',
    ))
    return {
        'checksum_matches': True,
        'local_report_matches': scope is not None,
        'matching_scope': scope,
        'exported_hit_count': len(exported_hits),
        'filename': path.name,
        'candidate_difference': candidates[0] if scope is None else None,
        'source_authenticity_verified': False,
        'network_accessed': False,
    }
