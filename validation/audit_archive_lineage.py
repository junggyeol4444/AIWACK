"""과거 여러 회차 원본 ZIP과 현재 누적 소스를 바이트 단위로 대조한다.

기존 복원 도구의 ZIP 경로·CRC·Windows 충돌 검사를 그대로 재사용한다.
읽기 전용: 서로 다른 회차의 동일 경로는 버전 충돌로 남기고 합성·덮어쓰지 않는다.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import stat
import zipfile

if __package__:
    from validation.restore_original_source_history import _validated_members
    from validation.windows_path_policy import collision_key
else:
    from restore_original_source_history import _validated_members
    from windows_path_policy import collision_key


def _sha_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def audit_archives(archives: list[Path], repository: Path, *, expected_paths: int | None = None) -> dict:
    """모든 ZIP을 읽고 원본별 버전·중복·누락을 반환한다. 파일 쓰기는 없다."""
    root = Path(repository).resolve(strict=True)
    if not root.is_dir() or not archives:
        raise ValueError('원본 저장소 폴더와 최소 한 개의 ZIP이 필요합니다.')
    if expected_paths is not None and (type(expected_paths) is not int or expected_paths < 1):
        raise ValueError('예상 원본 파일 수는 양의 정수여야 합니다.')
    source: dict[str, list[dict]] = {}
    aliases: dict[str, str] = {}
    for archive_path in archives:
        archive_path = Path(archive_path)
        with zipfile.ZipFile(archive_path) as archive:
            members = _validated_members(archive)
            for member in members:
                path = member.filename
                folded = collision_key(path)
                if folded in aliases and aliases[folded] != path:
                    raise ValueError('회차 간 Windows 경로 충돌: '+aliases[folded]+' / '+path)
                aliases[folded] = path
                digest = hashlib.sha256()
                with archive.open(member) as stream:
                    size = 0
                    for chunk in iter(lambda: stream.read(1024 * 1024), b''):
                        size += len(chunk)
                        if size > member.file_size:
                            raise ValueError('ZIP 파일 크기 불일치: '+path)
                        digest.update(chunk)
                if size != member.file_size:
                    raise ValueError('ZIP 파일 크기 불일치: '+path)
                source.setdefault(path, []).append({
                    'archive': str(archive_path), 'sha256': digest.hexdigest(), 'bytes': size})
    result = {'archives': [str(Path(p)) for p in archives], 'root': str(root),
              'expected_paths': expected_paths, 'distinct_original_paths': len(source),
              'identical': [], 'missing': [], 'changed': [], 'version_conflicts': [],
              'unsafe': [], 'repeated_identical': []}
    for name, versions in sorted(source.items()):
        unique = sorted({v['sha256'] for v in versions})
        record = {'path': name, 'original_versions': versions}
        if len(unique) > 1:
            result['version_conflicts'].append({**record, 'distinct_sha256': unique})
        elif len(versions) > 1:
            result['repeated_identical'].append(record)
        candidate = root.joinpath(*PurePosixPath(name).parts)
        if any(p.is_symlink() for p in (candidate, *candidate.parents) if p != root):
            result['unsafe'].append({**record, 'reason': 'symlink'})
            continue
        if not candidate.exists():
            result['missing'].append(record)
            continue
        if not candidate.is_file() or not stat.S_ISREG(candidate.stat().st_mode):
            result['unsafe'].append({**record, 'reason': 'not_regular_file'})
            continue
        current = _sha_file(candidate)
        matched = [v['archive'] for v in versions if v['sha256'] == current]
        row = {**record, 'current_sha256': current, 'matched_archives': matched}
        result['identical' if matched else 'changed'].append(row)
    result['coverage_confirmed'] = (expected_paths is None or len(source) == expected_paths)
    result['requires_manual_merge_review'] = bool(
        result['missing'] or result['changed'] or result['unsafe']
        or result['version_conflicts'] or not result['coverage_confirmed'])
    return result


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description='AIWACK 여러 회차 원본 ZIP 무손실 전수 대조')
    parser.add_argument('repository', type=Path)
    parser.add_argument('archives', nargs='+', type=Path)
    parser.add_argument('--expected-paths', type=int)
    parser.add_argument('--report', type=Path)
    args = parser.parse_args(argv)
    try:
        result = audit_archives(args.archives, args.repository, expected_paths=args.expected_paths)
    except (ValueError, OSError, zipfile.BadZipFile) as error:
        print(json.dumps({'error': str(error), 'verified': False}, ensure_ascii=False))
        return 3
    output = json.dumps(result, ensure_ascii=False, indent=2)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(output+'\n', encoding='utf-8')
    print(output)
    return 2 if result['requires_manual_merge_review'] else 0


if __name__ == '__main__':
    raise SystemExit(main())
