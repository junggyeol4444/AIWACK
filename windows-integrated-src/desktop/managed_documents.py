"""Stage53: owner-operated, offline UTF-8 documents in a fixed local workspace.

Not an AI tool executor. The SQLite copy is an audit/recovery reference; the
visible artifact is a real UTF-8 file on disk. A crash between file replacement
and SQLite commit may need operator repair; no automatic destructive recovery.
"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import re
import sqlite3
import stat
import tempfile

MAX_BYTES = 128 * 1024
EXTENSIONS = frozenset({'.txt', '.md', '.csv', '.json'})
NAME_PATTERN = re.compile(r'[A-Za-z0-9가-힣_-][A-Za-z0-9가-힣_.-]{0,94}\.(?:txt|md|csv|json)', re.ASCII | re.IGNORECASE)


def initialize(con: sqlite3.Connection) -> None:
    con.execute('''CREATE TABLE IF NOT EXISTS managed_documents (
        id INTEGER PRIMARY KEY,
        filename TEXT NOT NULL UNIQUE COLLATE NOCASE,
        version INTEGER NOT NULL DEFAULT 1 CHECK(version>=1),
        digest TEXT NOT NULL CHECK(length(digest)=64),
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    )''')
    con.execute('''CREATE TABLE IF NOT EXISTS managed_document_revisions (
        id INTEGER PRIMARY KEY,
        document_id INTEGER NOT NULL REFERENCES managed_documents(id) ON DELETE RESTRICT,
        version INTEGER NOT NULL CHECK(version>=1),
        content TEXT NOT NULL,
        digest TEXT NOT NULL CHECK(length(digest)=64),
        action TEXT NOT NULL CHECK(action IN ('created','updated')),
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(document_id, version)
    )''')
    for table in ('managed_document_revisions',):
        for operation in ('UPDATE', 'DELETE'):
            con.execute(f'''CREATE TRIGGER IF NOT EXISTS {table}_no_{operation.lower()}
                BEFORE {operation} ON {table} BEGIN
                SELECT RAISE(ABORT, 'document revision history is immutable'); END''')
    con.execute('''CREATE TRIGGER IF NOT EXISTS managed_documents_no_delete
        BEFORE DELETE ON managed_documents BEGIN
        SELECT RAISE(ABORT,'managed documents must not be deleted'); END''')
    con.execute('''CREATE TRIGGER IF NOT EXISTS managed_documents_guard_update
        BEFORE UPDATE ON managed_documents BEGIN
        SELECT RAISE(ABORT,'document identity is immutable')
            WHERE NEW.filename != OLD.filename OR NEW.id != OLD.id OR NEW.created_at != OLD.created_at
            OR NEW.version != OLD.version + 1; END''')


def _name(value: str) -> str:
    if not isinstance(value, str) or not NAME_PATTERN.fullmatch(value) or len(value.encode('utf-8')) > 180:
        raise ValueError('파일명은 확장자 txt/md/csv/json의 단일 파일명(영문·숫자·한글·_·-)이어야 합니다.')
    if Path(value).suffix.lower() not in EXTENSIONS or '..' in value:
        raise ValueError('허용되지 않은 파일명입니다.')
    return value


def _content(value: str) -> bytes:
    if not isinstance(value, str) or '\x00' in value:
        raise ValueError('UTF-8 텍스트만 저장할 수 있습니다.')
    result = value.encode('utf-8')
    if len(result) > MAX_BYTES:
        raise ValueError('문서 최대 크기는 128KiB입니다.')
    return result


def _identifier(value: int) -> int:
    if type(value) is not int or value <= 0:
        raise ValueError('문서 ID는 양의 정수여야 합니다.')
    return value


def _workspace(path: Path) -> Path:
    path = Path(path)
    # Do not traverse a symlinked managed workspace. The parent is the store's
    # configured data directory, not a path supplied by a message/AI response.
    if path.is_symlink():
        raise PermissionError('문서 작업 공간은 심볼릭 링크일 수 없습니다.')
    if not path.exists():
        path.mkdir(mode=0o700)  # no recursive creation from user content
    if not path.is_dir() or path.is_symlink():
        raise PermissionError('문서 작업 공간이 유효하지 않습니다.')
    return path


def _safe_disk_file(path: Path) -> bytes:
    # Prevent external files being overwritten through symlinks or hardlinks.
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
        raise PermissionError('외부 연결 파일이나 일반 파일이 아닌 대상은 수정할 수 없습니다.')
    flags = os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0) | getattr(os, 'O_BINARY', 0)
    descriptor = os.open(path, flags)
    try:
        open_info = os.fstat(descriptor)
        if not stat.S_ISREG(open_info.st_mode) or open_info.st_nlink != 1 or open_info.st_ino != info.st_ino:
            raise PermissionError('파일이 검사 중 교체되었습니다.')
        with os.fdopen(descriptor, 'rb', closefd=False) as file:
            data = file.read(MAX_BYTES + 1)
        if len(data) > MAX_BYTES:
            raise ValueError('외부에서 변경된 파일이 크기 제한을 초과합니다.')
        return data
    finally:
        os.close(descriptor)


def _write_temp(folder: Path, data: bytes) -> Path:
    descriptor, filename = tempfile.mkstemp(prefix='.aiwack-stage53-', suffix='.tmp', dir=folder)
    path = Path(filename)
    try:
        with os.fdopen(descriptor, 'wb') as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        return path
    except BaseException:
        path.unlink(missing_ok=True)
        raise


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def get(con: sqlite3.Connection, document_id: int) -> dict:
    con.row_factory = sqlite3.Row
    row = con.execute('SELECT * FROM managed_documents WHERE id=?', (_identifier(document_id),)).fetchone()
    if row is None:
        raise ValueError('등록된 문서가 없습니다.')
    return dict(row)


def list_documents(con: sqlite3.Connection, limit: int = 200) -> list[dict]:
    if type(limit) is not int or not 1 <= limit <= 1000:
        raise ValueError('조회 제한은 1~1000의 정수여야 합니다.')
    con.row_factory = sqlite3.Row
    return [dict(x) for x in con.execute('SELECT * FROM managed_documents ORDER BY id DESC LIMIT ?', (limit,))]


def revisions(con: sqlite3.Connection, document_id: int) -> list[dict]:
    get(con, document_id)
    con.row_factory = sqlite3.Row
    return [dict(x) for x in con.execute('''SELECT version, content, digest, action, created_at
        FROM managed_document_revisions WHERE document_id=? ORDER BY version''', (document_id,))]


def create(con: sqlite3.Connection, folder: Path, filename: str, content: str) -> int:
    filename = _name(filename)
    data = _content(content)
    folder = _workspace(folder)
    target = folder / filename
    # A file already present on disk is NEVER adopted or overwritten.
    if target.exists() or target.is_symlink():
        raise ValueError('이미 작업 공간에 존재하는 파일입니다.')
    if con.execute('SELECT 1 FROM managed_documents WHERE filename=? COLLATE NOCASE', (filename,)).fetchone():
        raise ValueError('등록된 문서명이 중복됩니다.')
    digest = _digest(data)
    created = False
    try:
        cursor = con.execute('INSERT INTO managed_documents(filename,digest) VALUES(?,?)', (filename, digest))
        doc_id = int(cursor.lastrowid)
        con.execute('''INSERT INTO managed_document_revisions(document_id,version,content,digest,action)
            VALUES(?,1,?,?,'created')''', (doc_id,content,digest))
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, 'O_BINARY', 0)
        fd = os.open(target, flags, 0o600)
        created = True
        with os.fdopen(fd, 'wb') as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        return doc_id
    except BaseException:
        if created:
            target.unlink(missing_ok=True)
        raise


def update(con: sqlite3.Connection, folder: Path, document_id: int,
           content: str, expected_version: int) -> int:
    if type(expected_version) is not int or expected_version < 1:
        raise ValueError('정확한 기존 문서 버전이 필요합니다.')
    row = get(con, document_id)
    if row['version'] != expected_version:
        raise ValueError('다른 변경이 먼저 저장되었습니다. 다시 불러와 확인하세요.')
    data = _content(content)
    folder = _workspace(folder)
    target = folder / row['filename']
    try:
        original = _safe_disk_file(target)
    except FileNotFoundError as exc:
        raise ValueError('실제 파일이 없어 덮어쓰기를 중단했습니다.') from exc
    if _digest(original) != row['digest']:
        raise ValueError('파일이 외부에서 변경되어 수정을 중단했습니다.')
    digest = _digest(data)
    if digest == row['digest']:
        raise ValueError('변경 내용이 없습니다.')
    temporary = _write_temp(folder, data)
    replaced = False
    try:
        result = con.execute('''UPDATE managed_documents SET version=version+1,digest=?,updated_at=CURRENT_TIMESTAMP
            WHERE id=? AND version=? AND digest=?''',
            (digest, document_id, expected_version, row['digest']))
        if result.rowcount != 1:
            raise ValueError('문서가 다른 처리 중 변경되었습니다.')
        con.execute('''INSERT INTO managed_document_revisions(document_id,version,content,digest,action)
            VALUES(?,?,?,?,'updated')''', (document_id,expected_version+1,content,digest))
        # Last recheck before atomic replacement. No external path is accepted.
        if _digest(_safe_disk_file(target)) != row['digest']:
            raise ValueError('파일이 외부에서 변경되어 수정을 중단했습니다.')
        os.replace(temporary, target)
        replaced = True
        return expected_version + 1
    except BaseException:
        if replaced:
            # Best-effort rollback for SQLite failure before the caller commits.
            restore = _write_temp(folder, original)
            try:
                os.replace(restore, target)
            finally:
                restore.unlink(missing_ok=True)
        raise
    finally:
        temporary.unlink(missing_ok=True)


def read_content(con: sqlite3.Connection, folder: Path, document_id: int) -> dict:
    row = get(con, document_id)
    try:
        disk = _safe_disk_file(_workspace(folder) / row['filename'])
    except FileNotFoundError as exc:
        raise ValueError('파일이 누락되었습니다. SQLite 이력은 유지됩니다.') from exc
    if _digest(disk) != row['digest']:
        raise ValueError('파일 내용이 SQLite 기록과 일치하지 않습니다. 자동으로 덮어쓰지 않습니다.')
    result = dict(row)
    result['content'] = disk.decode('utf-8')
    return result
