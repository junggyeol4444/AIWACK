"""Stage54: recheck a user-selected local file against stored import custody metadata.

No path is stored; no network, source retrieval, DB changes or claim of web
provenance. A match is *only* byte equality with the recorded SHA-256 digest.
"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import sqlite3
import stat

from desktop.research_captures import MAX_RAW_BYTES


def _read_selected_file(path: str | os.PathLike) -> tuple[str, str, int]:
    if not isinstance(path, (str, os.PathLike)):
        raise ValueError('재검사할 로컬 파일의 절대 경로가 필요합니다.')
    value = os.fspath(path)
    if not isinstance(value, str) or not value or '\x00' in value or value.startswith(('\\\\', '//')):
        raise ValueError('네트워크 공유 경로 또는 잘못된 경로는 사용할 수 없습니다.')
    item = Path(value)
    if not item.is_absolute() or len(item.name) > 255:
        raise ValueError('로컬 파일의 절대 경로와 올바른 이름이 필요합니다.')
    if os.name == 'nt':
        # Windows mapped drives can also refer to SMB shares.
        import ctypes
        from ctypes import wintypes
        if ctypes.windll.kernel32.GetDriveTypeW(wintypes.LPCWSTR(item.anchor)) in (0, 1, 4):
            raise ValueError('네트워크 드라이브 또는 확인되지 않은 드라이브는 사용할 수 없습니다.')
    # Reject symlink parents and symlink files; reading a chosen file must not
    # implicitly traverse through a link to a remote share or another location.
    if item.is_symlink() or any(parent.is_symlink() for parent in item.parents):
        raise ValueError('심볼릭 링크 파일이나 폴더는 사용할 수 없습니다.')
    if hasattr(item, 'is_junction') and (item.is_junction() or any(
            parent.is_junction() for parent in item.parents)):
        raise ValueError('Windows 접합점 경로는 사용할 수 없습니다.')
    fd = None
    try:
        flags = os.O_RDONLY | getattr(os, 'O_BINARY', 0) | getattr(os, 'O_NOFOLLOW', 0)
        fd = os.open(item, flags)
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode):
            raise ValueError('일반 파일만 검사할 수 있습니다.')
        if before.st_size > MAX_RAW_BYTES:
            raise ValueError('256KB 초과 파일은 검사할 수 없습니다.')
        with os.fdopen(fd, 'rb', closefd=False) as handle:
            data = handle.read(MAX_RAW_BYTES + 1)
        after = os.fstat(fd)
        path_after = item.stat(follow_symlinks=False)
        def signature(info):
            return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns,
                    getattr(info, 'st_ctime_ns', 0))
        if (len(data) > MAX_RAW_BYTES or len(data) != before.st_size or
                signature(before) != signature(after) or
                signature(after) != signature(path_after)):
            raise ValueError('파일을 읽는 동안 내용 또는 파일 경로가 변경되었습니다.')
        return item.name, hashlib.sha256(data).hexdigest(), len(data)
    except OSError as exc:
        raise ValueError('로컬 파일을 안전하게 열거나 검사할 수 없습니다.') from exc
    finally:
        if fd is not None:
            os.close(fd)


def recheck_import_file(con: sqlite3.Connection, capture_id: int,
                        selected_path: str | os.PathLike) -> dict:
    """Read-only comparison to a *previously imported* file's recorded bytes.

    Files originally imported through a JSON bundle use the same provenance
    table and are supported. Manual-only records have no original byte digest.
    """
    if type(capture_id) is not int or capture_id <= 0:
        raise ValueError('올바른 자료 ID를 선택해 주세요.')
    con.row_factory = sqlite3.Row
    row = con.execute('''SELECT c.id, c.source_url, c.archived_at,
                               i.original_filename, i.raw_sha256, i.raw_size
        FROM offline_research_captures AS c
        LEFT JOIN offline_research_local_imports AS i ON i.capture_id=c.id
        WHERE c.id=?''', (capture_id,)).fetchone()
    if row is None:
        raise ValueError('해당 자료 ID를 찾을 수 없습니다.')
    if row['original_filename'] is None:
        raise ValueError('이 자료는 로컬 파일에서 가져온 기록이 없어 바이트 재검사를 할 수 없습니다.')
    filename, raw_sha256, raw_size = _read_selected_file(selected_path)
    name_match = filename == row['original_filename']
    size_match = raw_size == row['raw_size']
    bytes_match = size_match and raw_sha256 == row['raw_sha256']
    return {
        'capture_id': capture_id,
        'archived': row['archived_at'] is not None,
        'claimed_source_url': row['source_url'],
        'recorded_filename': row['original_filename'],
        'selected_filename': filename,
        'filename_match': name_match,
        'recorded_size': row['raw_size'],
        'selected_size': raw_size,
        'size_match': size_match,
        'recorded_sha256': row['raw_sha256'],
        'selected_sha256': raw_sha256,
        'bytes_match': bytes_match,
        'original_file_bytes_rechecked': True,
        'web_source_verified': False,
        'network_accessed': False,
        'database_modified': False,
    }
