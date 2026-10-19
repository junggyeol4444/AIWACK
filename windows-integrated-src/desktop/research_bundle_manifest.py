"""Stage54: owner-directed local research bundle manifest writer (offline).

Only creates an import-compatible JSON list next to user-selected files. The
URLs are *unverified claims* supplied by the owner; no network, SQLite write,
file download, or automatic source attribution occurs.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

from desktop.research_captures import (
    DuplicateJSONKeyError, _portable_bundle_filename, _unique_json_members,
    _text, read_local_snapshot, validate_url,
)


def _local_path(value, *, label: str) -> Path:
    if not isinstance(value, (str, os.PathLike)):
        raise ValueError(f'{label}: 절대 경로를 지정해 주세요.')
    raw = os.fspath(value)
    if not isinstance(raw, str) or not raw or '\x00' in raw or raw.startswith(('\\\\', '//')):
        raise ValueError(f'{label}: 네트워크 공유 경로를 사용할 수 없습니다.')
    path = Path(raw)
    if not path.is_absolute():
        raise ValueError(f'{label}: 올바른 절대 경로가 필요합니다.')
    _portable_bundle_filename(path.name)
    if any(p.is_symlink() for p in (path, *path.parents)):
        raise ValueError(f'{label}: 심볼릭 링크 경로는 사용할 수 없습니다.')
    if hasattr(path, 'is_junction') and any(p.is_junction() for p in (path, *path.parents)):
        raise ValueError(f'{label}: Windows 접합점 경로는 사용할 수 없습니다.')
    if os.name == 'nt':
        import ctypes
        from ctypes import wintypes
        if ctypes.windll.kernel32.GetDriveTypeW(wintypes.LPCWSTR(path.anchor)) in (0, 1, 4):
            raise ValueError(f'{label}: 네트워크/확인되지 않은 드라이브는 사용할 수 없습니다.')
    return path


def create_local_bundle_manifest(entries, destination) -> dict:
    """Validate 1-20 explicit file/URL/title triples before creating JSON.

    All chosen files must live next to the new manifest. Uses O_EXCL so an
    existing file (including a competing creation) cannot be overwritten.
    The result can be passed to preview_local_bundle for database read-only
    duplicate checks, then explicitly approved for import in the existing UI.
    """
    if not isinstance(entries, (list, tuple)) or not 1 <= len(entries) <= 20:
        raise ValueError('자료 묶음은 1~20개 파일로 구성해야 합니다.')
    dest = _local_path(destination, label='저장할 JSON 목록')
    if dest.suffix.lower() != '.json':
        raise ValueError('목록 파일은 .json 확장자로 저장해야 합니다.')
    manifest_items = []
    input_hashes = []
    seen = set()
    for entry in entries:
        if not isinstance(entry, (list, tuple)) or len(entry) != 3:
            raise ValueError('파일 경로, 출처 URL, 제목을 각각 입력해야 합니다.')
        file_path, source_url, title = entry
        chosen = _local_path(file_path, label='자료 파일')
        if chosen.parent != dest.parent or chosen.name.casefold() == dest.name.casefold():
            raise ValueError('모든 자료 파일과 JSON 목록은 동일한 로컬 폴더에 있어야 합니다.')
        collision_key = _portable_bundle_filename(chosen.name)
        if collision_key in seen:
            raise ValueError('Windows에서 충돌하는 중복 파일은 묶음에 포함할 수 없습니다.')
        seen.add(collision_key)
        normalized_url = validate_url(source_url)
        clean_title = _text(title, '제목', 200)
        # Verify bytes, UTF-8, content limits and allowed extensions before any write.
        _, _, filename, raw_sha, raw_size = read_local_snapshot(chosen)
        manifest_items.append({'file': filename, 'url': normalized_url, 'title': clean_title})
        input_hashes.append({'file': filename, 'raw_sha256': raw_sha, 'raw_size': raw_size})
    document = {'format': 'aiwack-offline-research-bundle-v1', 'items': manifest_items}
    content = (json.dumps(document, ensure_ascii=False, indent=2) + '\n').encode('utf-8')
    if len(content) > 32_768:
        raise ValueError('JSON 목록이 32KB 제한을 초과합니다.')
    # Previously a change to file A while later files were being collected
    # could produce a valid-looking manifest with stale input fingerprints.
    # Before creating the JSON, check every original file a second time.
    # This is a best-effort read consistency check, NOT an atomic directory
    # snapshot: edits after the final read remain the responsibility of the
    # existing pre-import preview/approval validation.
    for fingerprint in input_hashes:
        try:
            _body, _kind, _name, latest_sha, latest_size = read_local_snapshot(
                dest.parent / fingerprint['file'])
        except (OSError, ValueError) as exc:
            raise ValueError('목록 생성 중 자료 파일을 재확인할 수 없습니다. 다시 검토해 주세요.') from exc
        if (latest_sha != fingerprint['raw_sha256'] or
                latest_size != fingerprint['raw_size']):
            raise ValueError('목록 생성 중 자료 파일이 변경되었습니다. 다시 검토해 주세요.')
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, 'O_BINARY', 0)
    flags |= getattr(os, 'O_NOFOLLOW', 0)
    try:
        fd = os.open(dest, flags, 0o600)
    except OSError as exc:
        raise ValueError('이미 존재하는 파일은 덮어쓰지 않으며, 이 위치에 저장할 수 없습니다.') from exc
    try:
        with os.fdopen(fd, 'wb') as output:
            output.write(content)
            output.flush()
            os.fsync(output.fileno())
    except BaseException:
        dest.unlink(missing_ok=True)
        raise
    return {'manifest_filename': dest.name,
            'manifest_sha256': hashlib.sha256(content).hexdigest(),
            'item_count': len(manifest_items),
            'input_files': input_hashes,
            'network_accessed': False, 'database_modified': False,
            'source_verified': False}


# Independent pre-import local custody checkpoint, not a web authentication.
RECEIPT_FORMAT = 'aiwack-offline-bundle-custody-v1'


def _receipt_digest(data: dict) -> str:
    raw = json.dumps(data, ensure_ascii=False, sort_keys=True,
                     separators=(',', ':')).encode('utf-8')
    return hashlib.sha256(raw).hexdigest()


def create_local_bundle_receipt(manifest_path, destination) -> dict:
    """Freeze the current raw-byte fingerprints without adding SQLite records.

    The owner must select both paths. Output excludes claimed URLs and body text.
    This SHA-256 receipt is *not* a cryptographic signature or web attestation.
    """
    from desktop.research_captures import _read_local_manifest_entries
    manifest_name, manifest_sha, parent, entries = _read_local_manifest_entries(manifest_path)
    dest = _local_path(destination, label='지문 기록 저장')
    if dest.parent != parent or dest.suffix.lower() != '.json' or dest.name.casefold() == manifest_name.casefold():
        raise ValueError('지문 기록 JSON은 자료 목록과 같은 폴더의 새 파일이어야 합니다.')
    filenames = {name.casefold() for name, _, _ in entries}
    if dest.name.casefold() in filenames:
        raise ValueError('기존 자료 파일을 덮어쓸 수 없습니다.')
    fingerprints = []
    for filename, _url, _title in entries:
        _content, _kind, _filename, digest, length = read_local_snapshot(parent / filename)
        fingerprints.append({'file': filename, 'raw_sha256': digest, 'raw_size': length})
    # A bundle is read in sequence, so file A may be replaced while file B is
    # scanned. Refuse to emit a misleading 'consistent' receipt unless the
    # manifest and every source still match the initial read. This is a
    # best-effort pre-write stability guard, not a filesystem-wide snapshot.
    latest_name, latest_sha, latest_parent, latest_entries = _read_local_manifest_entries(manifest_path)
    if (latest_name != manifest_name or latest_sha != manifest_sha or
            latest_parent != parent or latest_entries != entries):
        raise ValueError('기록 생성 중 JSON 목록이 변경되었습니다. 다시 검토해 주세요.')
    for record in fingerprints:
        try:
            _content, _kind, _name, sha, size = read_local_snapshot(parent / record['file'])
        except (OSError, ValueError) as exc:
            raise ValueError('기록 생성 중 자료 파일을 재확인할 수 없습니다. 다시 검토해 주세요.') from exc
        if sha != record['raw_sha256'] or size != record['raw_size']:
            raise ValueError('기록 생성 중 자료 파일이 변경되었습니다. 다시 검토해 주세요.')
    document = {'format': RECEIPT_FORMAT, 'manifest_filename': manifest_name,
                'manifest_sha256': manifest_sha, 'items': fingerprints}
    document['receipt_sha256'] = _receipt_digest(document)
    content = (json.dumps(document, ensure_ascii=False, indent=2) + '\n').encode('utf-8')
    if len(content) > 32_768:
        raise ValueError('지문 기록이 32KB 제한을 초과합니다.')
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, 'O_BINARY', 0)
    flags |= getattr(os, 'O_NOFOLLOW', 0)
    try:
        fd = os.open(dest, flags, 0o600)
    except OSError as exc:
        raise ValueError('기존 파일 덮어쓰기 또는 이 위치에 저장은 허용되지 않습니다.') from exc
    try:
        with os.fdopen(fd, 'wb') as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
    except BaseException:
        dest.unlink(missing_ok=True)
        raise
    return {'receipt_filename': dest.name, 'item_count': len(entries),
            'receipt_sha256': document['receipt_sha256'],
            'network_accessed': False, 'database_modified': False,
            'web_source_verified': False, 'signed': False}


def verify_local_bundle_receipt(receipt_path) -> dict:
    """Read-only comparison against a self-checksummed local custody receipt.

    A missing or changed manifest is reported separately from files. Neither
    this receipt nor a matching SHA-256 authenticates the origin of content.
    """
    from desktop.research_captures import _read_local_manifest_entries
    import stat
    path = _local_path(receipt_path, label='지문 기록 검사')
    if path.suffix.lower() != '.json':
        raise ValueError('JSON 지문 기록 파일이 필요합니다.')
    try:
        fd = os.open(path, os.O_RDONLY | getattr(os, 'O_BINARY', 0) |
                     getattr(os, 'O_NOFOLLOW', 0))
        try:
            before = os.fstat(fd)
            if not stat.S_ISREG(before.st_mode) or not 1 <= before.st_size <= 32_768:
                raise ValueError('지문 기록 크기가 잘못되었습니다.')
            with os.fdopen(fd, 'rb', closefd=False) as handle:
                raw = handle.read(32_769)
            after = os.fstat(fd)
            if len(raw) != before.st_size or (before.st_size, before.st_mtime_ns, before.st_ino) != (
                    after.st_size, after.st_mtime_ns, after.st_ino):
                raise ValueError('읽는 도중 변경된 기록은 사용할 수 없습니다.')
        finally:
            os.close(fd)
    except OSError as exc:
        raise ValueError('지문 기록을 안전하게 읽을 수 없습니다.') from exc
    try:
        doc = json.loads(raw.decode('utf-8', 'strict'),
                         object_pairs_hook=_unique_json_members)
    except DuplicateJSONKeyError as exc:
        raise ValueError('지문 기록에 중복된 키가 있습니다.') from exc
    except (UnicodeError, ValueError) as exc:
        raise ValueError('지문 기록의 UTF-8 JSON이 잘못되었습니다.') from exc
    required = {'format','manifest_filename','manifest_sha256','items','receipt_sha256'}
    if not isinstance(doc, dict) or set(doc) != required or doc['format'] != RECEIPT_FORMAT:
        raise ValueError('지원하지 않는 지문 기록 형식입니다.')
    name = doc['manifest_filename']
    if not isinstance(name, str) or not name.lower().endswith('.json'):
        raise ValueError('지문 기록에 안전하지 않은 목록 파일명이 있습니다.')
    _portable_bundle_filename(name)
    if name.casefold() == path.name.casefold():
        raise ValueError('지문 기록에 안전하지 않은 목록 파일명이 있습니다.')
    if not isinstance(doc['items'], list) or not 1 <= len(doc['items']) <= 20:
        raise ValueError('지문 기록 항목 수가 올바르지 않습니다.')
    for item in doc['items']:
        if (not isinstance(item, dict) or set(item) != {'file','raw_sha256','raw_size'} or
                not isinstance(item['file'], str) or
                not isinstance(item['raw_sha256'], str) or len(item['raw_sha256']) != 64 or
                any(c not in '0123456789abcdef' for c in item['raw_sha256']) or
                type(item['raw_size']) is not int or not 1 <= item['raw_size'] <= 256_000):
            raise ValueError('지문 기록에 잘못된 파일 항목이 있습니다.')
        try:
            _portable_bundle_filename(item['file'])
        except ValueError as exc:
            raise ValueError('지문 기록에 잘못된 파일 항목이 있습니다.') from exc
    for field in ('manifest_sha256', 'receipt_sha256'):
        if not isinstance(doc[field], str) or len(doc[field]) != 64 or any(
                c not in '0123456789abcdef' for c in doc[field]):
            raise ValueError('SHA-256 기록 형식이 올바르지 않습니다.')
    if len({i['file'].casefold() for i in doc['items']}) != len(doc['items']):
        raise ValueError('중복된 지문 기록 항목이 있습니다.')
    import hmac
    if not hmac.compare_digest(_receipt_digest({k:v for k,v in doc.items() if k != 'receipt_sha256'}),
                               doc['receipt_sha256']):
        raise ValueError('지문 기록 자체 체크섬이 일치하지 않습니다.')
    # Check the manifest twice: an editor may replace it after the first
    # read while the source files are being scanned. The double scan below
    # likewise prevents a stale first-file match from becoming a "passed"
    # result when a later file triggers an intervening change.
    def manifest_snapshot():
        try:
            _name, current_sha, _parent, entries = _read_local_manifest_entries(path.parent / name)
        except (ValueError, OSError):
            return None
        return (current_sha, tuple(item[0] for item in entries))

    def source_snapshot(filename):
        try:
            _body, _kind, _filename, current_digest, current_size = read_local_snapshot(path.parent / filename)
        except (ValueError, OSError):
            return None
        return (current_digest, current_size)

    expected_manifest = (doc['manifest_sha256'], tuple(item['file'] for item in doc['items']))
    first_manifest = manifest_snapshot()
    first_sources = [source_snapshot(item['file']) for item in doc['items']]
    last_manifest = manifest_snapshot()
    last_sources = [source_snapshot(item['file']) for item in doc['items']]
    changed_during_check = (first_manifest != last_manifest or
                            any(a != b for a, b in zip(first_sources, last_sources)))
    if first_manifest is None or last_manifest is None:
        manifest_status = 'unavailable'
    elif first_manifest != expected_manifest or last_manifest != expected_manifest:
        manifest_status = 'changed'
    else:
        manifest_status = 'match'
    counts = {'match': 0, 'changed': 0, 'unavailable': 0}
    items = []
    for record, first, last in zip(doc['items'], first_sources, last_sources):
        expected = (record['raw_sha256'], record['raw_size'])
        if first is None or last is None:
            status = 'unavailable'
        elif first == expected and last == expected:
            status = 'match'
        else:
            status = 'changed'
        counts[status] += 1
        items.append({'file': record['file'], 'status': status})
    return {'receipt_filename': path.name, 'item_count': len(items),
            'manifest_status': manifest_status, 'counts': counts, 'items': items,
            'passed': not changed_during_check and manifest_status == 'match' and
                      counts['match'] == len(items),
            'changed_during_check': changed_during_check,
            'receipt_checksum_matches': True,
            'network_accessed': False, 'database_modified': False,
            'web_source_verified': False, 'signed': False}
