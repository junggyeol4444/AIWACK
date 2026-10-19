"""Stage58: local-only media/document adapter boundary.

Fixed, non-executable adapter descriptors and read-only file inspection.
No plugin imports, shell commands, codecs, network, or automatic publishing.
This is NOT image/video generation or a full editing/rendering integration.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import os
import stat
from pathlib import Path
import sqlite3
import struct
import zipfile

MAX_BYTES = 20 * 1024 * 1024


@dataclass(frozen=True)
class Adapter:
    key: str
    category: str
    extensions: tuple[str, ...]
    operation: str = 'inspect_local_file'
    needs_owner_confirmation: bool = True
    executes_external_program: bool = False


ADAPTERS = (
    Adapter('image_png', 'image', ('.png',)),
    Adapter('image_jpeg', 'image', ('.jpg', '.jpeg')),
    Adapter('video_mp4', 'video', ('.mp4',)),
    Adapter('video_webm', 'video', ('.webm',)),
    Adapter('document_text', 'document', ('.txt', '.md')),
    Adapter('document_pdf', 'document', ('.pdf',)),
    Adapter('document_docx', 'document', ('.docx',)),
)


def available_adapters() -> list[dict]:
    return [dict(key=a.key, category=a.category, extensions=list(a.extensions),
                 operation=a.operation, needs_owner_confirmation=a.needs_owner_confirmation,
                 executes_external_program=a.executes_external_program) for a in ADAPTERS]


def _inspect_png(raw: bytes) -> str:
    if len(raw) < 33 or raw[:8] != b'\x89PNG\r\n\x1a\n' or raw[12:16] != b'IHDR' or raw[8:12] != b'\x00\x00\x00\r':
        raise ValueError('PNG 파일 헤더가 유효하지 않습니다.')
    width, height = struct.unpack('>II', raw[16:24])
    if not (1 <= width <= 100000 and 1 <= height <= 100000):
        raise ValueError('PNG 크기가 유효하지 않습니다.')
    return f'PNG 헤더 {width}x{height} (이미지 디코딩·편집 없음)'


def _inspect_jpeg(raw: bytes) -> str:
    if len(raw) < 4 or raw[:2] != b'\xff\xd8' or raw[-2:] != b'\xff\xd9':
        raise ValueError('JPEG 시작/종료 마커가 없습니다.')
    # Header-only classification, not a claim that all scan segments decode.
    return 'JPEG 시작/종료 마커 확인 (이미지 디코딩·편집 없음)'


def _inspect_mp4(raw: bytes) -> str:
    if len(raw) < 16 or raw[4:8] != b'ftyp':
        raise ValueError('MP4 ftyp 헤더가 없습니다.')
    box_size = int.from_bytes(raw[:4], 'big')
    if box_size < 16 or box_size > len(raw) or box_size > 4096:
        raise ValueError('MP4 ftyp 박스 크기가 유효하지 않습니다.')
    brand = raw[8:12]
    if not all(32 <= b < 127 for b in brand):
        raise ValueError('MP4 브랜드가 유효하지 않습니다.')
    return 'MP4 ftyp 브랜드 ' + brand.decode('ascii') + ' (영상 디코딩·렌더링 없음)'


def _inspect_webm(raw: bytes) -> str:
    if len(raw) < 8 or raw[:4] != b'\x1a\x45\xdf\xa3':
        raise ValueError('WebM EBML 헤더가 없습니다.')
    # EBML header alone cannot prove valid WebM: explicitly say preliminary.
    return 'EBML 헤더 확인 (WebM 스트림 전체 유효성·렌더링 미검증)'


def _inspect_text(raw: bytes) -> str:
    try:
        value = raw.decode('utf-8-sig')
    except UnicodeError as exc:
        raise ValueError('UTF-8 문서만 지원합니다.') from exc
    if '\x00' in value:
        raise ValueError('NUL이 포함된 텍스트를 거부합니다.')
    return f'UTF-8 텍스트 {len(value)}자 / {len(value.splitlines())}줄 (읽기 전용)'


def _inspect_pdf(raw: bytes) -> str:
    if not raw.startswith(b'%PDF-') or b'%%EOF' not in raw[-2048:]:
        raise ValueError('PDF 시작/종료 마커가 없습니다.')
    return 'PDF 시작/종료 마커 확인 (본문 파싱·렌더링 없음)'


def _inspect_docx(raw: bytes) -> str:
    from io import BytesIO
    try:
        with zipfile.ZipFile(BytesIO(raw)) as archive:
            infos = archive.infolist()
            if len(infos) > 3000 or sum(i.file_size for i in infos) > 40 * 1024 * 1024:
                raise ValueError('DOCX 압축 항목 크기 제한 초과')
            names = {i.filename for i in infos}
            if '[Content_Types].xml' not in names or 'word/document.xml' not in names:
                raise ValueError('DOCX 필수 문서 항목이 없습니다.')
            for i in infos:
                if i.filename.startswith('/') or '..' in Path(i.filename).parts or '\\' in i.filename:
                    raise ValueError('DOCX 내부 경로가 안전하지 않습니다.')
            return f'DOCX 구조 항목 {len(infos)}개 (압축 해제·본문 실행 없음)'
    except (zipfile.BadZipFile, EOFError) as exc:
        raise ValueError('DOCX 압축 구조가 유효하지 않습니다.') from exc


_INSPECTORS = {
    'image_png': _inspect_png, 'image_jpeg': _inspect_jpeg,
    'video_mp4': _inspect_mp4, 'video_webm': _inspect_webm,
    'document_text': _inspect_text, 'document_pdf': _inspect_pdf,
    'document_docx': _inspect_docx,
}


def inspect_local(path: str | Path, adapter_key: str) -> dict:
    """Inspect an explicitly chosen local file, never mutate or execute it."""
    adapter = next((a for a in ADAPTERS if a.key == adapter_key), None)
    if adapter is None:
        raise ValueError('등록되지 않은 내장 어댑터입니다.')
    p = Path(path).expanduser()
    if p.is_symlink() or not p.is_file():
        raise ValueError('일반 로컬 파일만 허용합니다. 심볼릭 링크는 거부합니다.')
    if p.suffix.lower() not in adapter.extensions:
        raise ValueError('파일 확장자가 선택한 어댑터와 일치하지 않습니다.')
    before = p.stat()
    if not (1 <= before.st_size <= MAX_BYTES):
        raise ValueError('파일은 1바이트~20MiB만 지원합니다.')
    flags = os.O_RDONLY | getattr(os, 'O_BINARY', 0) | getattr(os, 'O_NOFOLLOW', 0)
    fd = os.open(p, flags)
    try:
        opened = os.fstat(fd)
        if not stat.S_ISREG(opened.st_mode) or opened.st_ino != before.st_ino:
            raise ValueError('일반 파일이 아니거나 파일이 교체되었습니다.')
        with os.fdopen(fd, 'rb') as stream:
            fd = -1
            raw = stream.read(MAX_BYTES + 1)
    finally:
        if fd != -1:
            os.close(fd)
    after = p.stat()
    if (len(raw) != before.st_size or len(raw) > MAX_BYTES or
            before.st_size != after.st_size or before.st_mtime_ns != after.st_mtime_ns or
            before.st_ino != after.st_ino):
        raise ValueError('읽는 동안 파일이 변경되었거나 크기 제한을 초과했습니다.')
    details = _INSPECTORS[adapter.key](raw)
    return {'adapter_key': adapter.key, 'category': adapter.category,
            'filename': p.name, 'byte_size': len(raw),
            'sha256': hashlib.sha256(raw).hexdigest(), 'details': details,
            'operation': adapter.operation, 'external_execution': False}


def initialize(con: sqlite3.Connection) -> None:
    con.execute('''CREATE TABLE IF NOT EXISTS media_adapter_inspections (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        adapter_key TEXT NOT NULL CHECK(length(adapter_key) BETWEEN 3 AND 64),
        category TEXT NOT NULL CHECK(category IN ('image','video','document')),
        filename TEXT NOT NULL CHECK(length(filename) BETWEEN 1 AND 255),
        byte_size INTEGER NOT NULL CHECK(byte_size BETWEEN 1 AND 20971520),
        sha256 TEXT NOT NULL CHECK(length(sha256)=64),
        details TEXT NOT NULL CHECK(length(details) BETWEEN 1 AND 500),
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    )''')
    for event in ('UPDATE', 'DELETE'):
        con.execute(f'''CREATE TRIGGER IF NOT EXISTS media_adapter_inspections_no_{event.lower()}
            BEFORE {event} ON media_adapter_inspections BEGIN
            SELECT RAISE(ABORT,'media inspection audit is immutable'); END''')


def record(con: sqlite3.Connection, result: dict) -> int:
    cursor = con.execute('''INSERT INTO media_adapter_inspections
        (adapter_key,category,filename,byte_size,sha256,details) VALUES (?,?,?,?,?,?)''',
        tuple(result[k] for k in ('adapter_key','category','filename','byte_size','sha256','details')))
    return int(cursor.lastrowid)


def history(con: sqlite3.Connection, limit: int = 50) -> list[dict]:
    if type(limit) is not int or not 1 <= limit <= 200:
        raise ValueError('조회 제한은 1~200입니다.')
    con.row_factory = sqlite3.Row
    return [dict(row) for row in con.execute('SELECT * FROM media_adapter_inspections ORDER BY id DESC LIMIT ?', (limit,))]
