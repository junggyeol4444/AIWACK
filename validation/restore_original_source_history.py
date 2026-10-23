"""AIWACK 누적 원본 ZIP 무손실 비교·누락 복원 도구.

기본 모드는 읽기 전용이다. --restore-missing도 없는 파일만 복원하며,
이미 존재하는 코드·인수인계는 어떤 경우에도 덮어쓰지 않는다.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import stat
import sys
import zipfile
if __package__:
    from validation.windows_path_policy import collision_key, unsafe_part
else:  # Windows direct script invocation
    from windows_path_policy import collision_key, unsafe_part

MAX_MEMBER_BYTES = 16 * 1024 * 1024
MAX_ARCHIVE_BYTES = 256 * 1024 * 1024
MAX_MEMBERS = 10000
WINDOWS_RESERVED = {'CON', 'PRN', 'AUX', 'NUL'} | {
    f'{prefix}{number}' for prefix in ('COM', 'LPT') for number in range(1, 10)
}


def _validated_members(archive: zipfile.ZipFile) -> list[zipfile.ZipInfo]:
    entries = []
    seen = set()
    total = 0
    for entry in archive.infolist():
        if entry.is_dir():
            continue
        name = entry.filename
        parts = PurePosixPath(name).parts
        if (not name or name.startswith(('/', '\\')) or '\\' in name
                or ':' in name or '\x00' in name or name != PurePosixPath(name).as_posix()
                or any(ord(c) < 32 for c in name)
                or any(unsafe_part(part) for part in parts)
                or any(part in ('', '.', '..') or part.endswith((' ', '.'))
                       or part.split('.')[0].upper() in WINDOWS_RESERVED for part in parts)
                or not parts or PurePosixPath(name).is_absolute()):
            raise ValueError(f'안전하지 않은 ZIP 파일 경로: {name!r}')
        mode = (entry.external_attr >> 16) & 0o170000
        if mode not in (0, stat.S_IFREG):
            raise ValueError(f'ZIP 링크·특수 파일 복원 금지: {name!r}')
        if entry.flag_bits & 1:
            raise ValueError(f'암호화된 ZIP 항목 복원 금지: {name!r}')
        if entry.file_size > MAX_MEMBER_BYTES:
            raise ValueError(f'ZIP 단일 파일 크기 초과: {name!r}')
        total += entry.file_size
        if total > MAX_ARCHIVE_BYTES or len(entries) >= MAX_MEMBERS:
            raise ValueError('ZIP 전체 크기 또는 항목 수 초과')
        folded = collision_key(name)
        if folded in seen:
            raise ValueError(f'Windows 파일명 중복/대소문자 충돌: {name!r}')
        seen.add(folded)
        entries.append(entry)
    return sorted(entries, key=lambda item: item.filename)


def _hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def reconcile(archive_path: Path, repository_root: Path, *, restore_missing: bool = False) -> dict:
    """원본 파일별 SHA256 검사, 선택적 누락 복원. 변경된 파일은 충돌로 보고."""
    root = Path(repository_root).resolve(strict=True)
    if not root.is_dir():
        raise ValueError('원본 소스 폴더가 없습니다.')
    result = {'archive': str(archive_path), 'root': str(root),
              'mode': 'restore_missing' if restore_missing else 'read_only',
              'identical': [], 'missing': [], 'restored': [], 'conflicts': []}
    with zipfile.ZipFile(archive_path) as archive:
        members = _validated_members(archive)
        # Validate all decompressed bytes/CRC before writing any original file.
        for entry in members:
            with archive.open(entry) as source:
                count = 0
                for chunk in iter(lambda: source.read(1024 * 1024), b''):
                    count += len(chunk)
                    if count > entry.file_size or count > MAX_MEMBER_BYTES:
                        raise ValueError('ZIP 원본 크기·CRC 검증 실패: ' + entry.filename)
                if count != entry.file_size:
                    raise ValueError('ZIP 원본 크기 검증 실패: ' + entry.filename)
        # Validate ALL destination paths before the first write. A later
        # symlink must not leave an earlier historical file half-restored.
        for entry in members:
            candidate = root.joinpath(*PurePosixPath(entry.filename).parts)
            for ancestor in (candidate, *candidate.parents):
                if ancestor == root:
                    break
                if ancestor.is_symlink():
                    raise ValueError(f'링크 경로를 통한 원본 복원 금지: {entry.filename}')
            if not candidate.resolve(strict=False).is_relative_to(root):
                raise ValueError(f'저장소 바깥 경로 복원 금지: {entry.filename}')
        for entry in members:
            path = root.joinpath(*PurePosixPath(entry.filename).parts)
            for ancestor in (path, *path.parents):
                if ancestor == root:
                    break
                if ancestor.is_symlink():
                    raise ValueError(f'링크 경로를 통한 원본 복원 금지: {entry.filename}')
            if not path.resolve(strict=False).is_relative_to(root):
                raise ValueError(f'저장소 바깥 경로 복원 금지: {entry.filename}')
            with archive.open(entry) as stream:
                content = stream.read(MAX_MEMBER_BYTES + 1)
            if len(content) != entry.file_size:
                raise ValueError(f'ZIP 원본 파일 크기 불일치: {entry.filename}')
            item = {'path': entry.filename, 'sha256': _hash(content), 'bytes': len(content)}
            if path.exists():
                if not path.is_file():
                    result['conflicts'].append({**item, 'reason': 'not_regular_file'})
                    continue
                digest = hashlib.sha256()
                with path.open('rb') as stream:
                    for chunk in iter(lambda: stream.read(1024 * 1024), b''):
                        digest.update(chunk)
                if digest.hexdigest() == item['sha256']:
                    result['identical'].append(item)
                else:
                    result['conflicts'].append({**item, 'existing_sha256': digest.hexdigest(),
                                                'reason': 'different_content_no_overwrite'})
                continue
            if not restore_missing:
                result['missing'].append(item)
                continue
            path.parent.mkdir(parents=True, exist_ok=True)
            try:
                with path.open('xb') as output:
                    output.write(content)
                    output.flush()
                    os.fsync(output.fileno())
                if _hash(path.read_bytes()) != item['sha256']:
                    raise OSError('복원된 원본 SHA256 검증 실패')
            except FileExistsError:
                result['conflicts'].append({**item, 'reason': 'concurrent_create'})
                continue
            except Exception:
                if path.exists() and path.is_file():
                    path.unlink()
                raise
            result['restored'].append(item)
    result['total'] = sum(len(result[key]) for key in
                          ('identical', 'missing', 'restored', 'conflicts'))
    result['complete'] = not result['missing'] and not result['conflicts']
    return result


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description='AIWACK 원본 ZIP 무손실 대조/누락 복원')
    parser.add_argument('archive', type=Path)
    parser.add_argument('repository', type=Path)
    parser.add_argument('--restore-missing', action='store_true', help='없는 파일만 복원, 덮어쓰기 금지')
    parser.add_argument('--report', type=Path, help='JSON 검사 결과 저장 경로')
    args = parser.parse_args(argv)
    try:
        report = reconcile(args.archive, args.repository, restore_missing=args.restore_missing)
    except (ValueError, OSError, zipfile.BadZipFile) as exc:
        print(json.dumps({'complete': False, 'error': str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 3
    output = json.dumps(report, ensure_ascii=False, indent=2)
    print(output)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(output + '\n', encoding='utf-8')
    return 0 if report['complete'] else 2


if __name__ == '__main__':
    raise SystemExit(main())
