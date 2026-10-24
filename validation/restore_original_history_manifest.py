"""21회차 원본 ZIP의 매니페스트를 검증해 누락 파일만 바이트 그대로 복원한다.

기존 파일은 동일/충돌 여부만 검사하며 수정·삭제하지 않는다. 이 도구는
원본 복원 도구이지 GitHub main 병합·실 GGUF 검증의 대체물이 아니다.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import stat
import zipfile

try:
    from validation.restore_original_source_history import _validated_members
    from validation.windows_path_policy import collision_key
except ImportError:
    from restore_original_source_history import _validated_members
    from windows_path_policy import collision_key


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _safe_destination(root: Path, name: str) -> Path:
    parts = PurePosixPath(name).parts
    if (not parts or name.startswith('/') or '\\' in name
            or any(p in ('', '.', '..') for p in parts)):
        raise ValueError('원본 ZIP 경로가 안전하지 않습니다: ' + name)
    dest = root.joinpath(*parts)
    for parent in (dest, *dest.parents):
        if parent == root:
            break
        if parent.is_symlink():
            raise ValueError('기존 경로의 심볼릭 링크가 감지됐습니다: ' + name)
    if not dest.resolve(strict=False).is_relative_to(root):
        raise ValueError('원본 복원 대상이 저장소를 벗어납니다: ' + name)
    return dest


def restore_manifest_history(archive_path: Path, repository: Path, *, apply=False) -> dict:
    """전체 ZIP을 검증한 뒤에만 없는 파일을 생성한다. 기존 파일은 변경하지 않는다."""
    root = Path(repository).resolve(strict=True)
    if not root.is_dir():
        raise ValueError('대상 저장소 폴더가 존재하지 않습니다.')
    records = {}
    with zipfile.ZipFile(archive_path) as archive:
        members = {item.filename: item for item in _validated_members(archive)}
        if 'PRESERVATION_MANIFEST.json' not in members:
            raise ValueError('원본 보존 매니페스트가 없습니다.')
        manifest_bytes = archive.read(members['PRESERVATION_MANIFEST.json'])
        manifest = json.loads(manifest_bytes)
        rows = manifest.get('files')
        if not isinstance(rows, list) or not rows:
            raise ValueError('원본 보존 파일 목록이 비어 있습니다.')
        if set(members) != {'PRESERVATION_MANIFEST.json'} | {r.get('path') for r in rows if isinstance(r, dict)}:
            raise ValueError('원본 매니페스트와 ZIP 파일 목록이 다릅니다.')
        keys = {}
        for row in rows:
            if not isinstance(row, dict):
                raise ValueError('원본 매니페스트 항목 형식 오류')
            name, size, expected = row.get('path'), row.get('bytes'), row.get('sha256')
            if (not isinstance(name, str) or name == 'PRESERVATION_MANIFEST.json'
                    or type(size) is not int or size < 0 or not isinstance(expected, str)
                    or len(expected) != 64 or any(c not in '0123456789abcdef' for c in expected)):
                raise ValueError('원본 매니페스트 항목 무결성 오류')
            dest = _safe_destination(root, name)
            key = collision_key(name)
            if key in keys:
                raise ValueError('Windows 원본 파일명 충돌: ' + name)
            keys[key] = name
            data = archive.read(members[name])
            if len(data) != size or _digest(data) != expected:
                raise ValueError('원본 바이트 또는 SHA256 불일치: ' + name)
            records[name] = (dest, expected, data)

    existing_aliases = {}
    for path in root.rglob('*'):
        rel = path.relative_to(root).as_posix()
        if rel == '.git' or rel.startswith('.git/'):
            continue
        key = collision_key(rel)
        previous = existing_aliases.setdefault(key, rel)
        if previous != rel:
            raise ValueError('저장소 Windows 경로 충돌: ' + rel)
    for name in records:
        parts = PurePosixPath(name).parts
        for index in range(1, len(parts) + 1):
            prefix = '/'.join(parts[:index])
            alias = existing_aliases.get(collision_key(prefix))
            if alias is not None and alias != prefix:
                raise ValueError('복원 경로의 Windows 별칭 충돌: ' + prefix)

    result = {'archive': str(archive_path), 'manifest_sha256': _digest(manifest_bytes),
              'expected_files': len(records), 'apply_requested': bool(apply),
              'existing_identical': [], 'existing_conflict': [], 'missing': [],
              'restored': [], 'automatic_overwrite': False}
    for name, (dest, expected, _) in records.items():
        if dest.exists():
            if not dest.is_file() or not stat.S_ISREG(dest.stat().st_mode):
                result['existing_conflict'].append(name)
            elif _digest(dest.read_bytes()) == expected:
                result['existing_identical'].append(name)
            else:
                result['existing_conflict'].append(name)
        else:
            result['missing'].append(name)

    if apply:
        for name in result['missing']:
            dest, expected, data = records[name]
            _safe_destination(root, name)
            dest.parent.mkdir(parents=True, exist_ok=True)
            flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
            if hasattr(os, 'O_BINARY'):
                flags |= os.O_BINARY
            fd = os.open(dest, flags, 0o644)
            try:
                with os.fdopen(fd, 'wb') as stream:
                    stream.write(data)
                    stream.flush()
                    os.fsync(stream.fileno())
                if _digest(dest.read_bytes()) != expected:
                    raise ValueError('복원 직후 원본 SHA256 불일치: ' + name)
            except BaseException:
                dest.unlink(missing_ok=True)
                raise
            result['restored'].append(name)
    result['manual_review_required'] = bool(result['existing_conflict'])
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description='AIWACK 원본 역사 문서 무덮어쓰기 복원')
    parser.add_argument('archive', type=Path)
    parser.add_argument('repository', type=Path)
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--report', type=Path)
    args = parser.parse_args(argv)
    try:
        result = restore_manifest_history(args.archive, args.repository, apply=args.apply)
    except (ValueError, OSError, KeyError, TypeError, zipfile.BadZipFile) as error:
        print(json.dumps({'verified': False, 'error': str(error)}, ensure_ascii=False))
        return 3
    payload = json.dumps(result, ensure_ascii=False, indent=2) + '\n'
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(payload, encoding='utf-8')
    print(payload)
    return 2 if result['manual_review_required'] else 0


if __name__ == '__main__':
    raise SystemExit(main())
