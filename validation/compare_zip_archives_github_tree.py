"""과거 원본 ZIP 여러 회차와 GitHub 완전한 tree의 경로별 바이트 무손실 대조.

이 프로그램은 읽기 전용이다. 결과에 역사 충돌이 남아 있으면 어떤 원본도
임의로 채택하지 않는다. 실제 GitHub tree JSON은 호출자가 제공해야 한다.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import zipfile
from pathlib import Path, PurePosixPath

try:
    from validation.plan_github_history_restore import _checked_tree, _git_blob_sha
    from validation.restore_original_source_history import _validated_members, MAX_MEMBER_BYTES
    from validation.windows_path_policy import collision_key
except ImportError:
    from plan_github_history_restore import _checked_tree, _git_blob_sha
    from restore_original_source_history import _validated_members, MAX_MEMBER_BYTES
    from windows_path_policy import collision_key


def compare_zip_archives_to_github(archive_paths: list[Path], tree: dict,
                                   expected_paths: int | None = None) -> dict:
    """원본 ZIP에서 실제 bytes/CRC를 읽은 뒤 Git Blob SHA와 전수 대조한다."""
    if not archive_paths:
        raise ValueError('원본 ZIP 목록이 비어 있습니다.')
    if expected_paths is not None and (type(expected_paths) is not int or expected_paths < 1):
        raise ValueError('원본 경로 수는 양수여야 합니다.')
    remote = _checked_tree(tree)
    seen_archives: set[str] = set()
    versions: dict[str, dict[str, dict]] = {}
    aliases: dict[str, str] = {}
    fingerprints: list[dict] = []
    for archive_path in archive_paths:
        archive_path = Path(archive_path)
        if archive_path.is_symlink() or not archive_path.is_file():
            raise ValueError('원본 ZIP 누락 또는 링크: ' + str(archive_path))
        if archive_path.suffix.lower() != '.zip':
            raise ValueError('ZIP 파일만 대조합니다.')
        archive_id = str(archive_path.resolve())
        if archive_id in seen_archives:
            raise ValueError('같은 ZIP 반복 지정은 불가합니다.')
        seen_archives.add(archive_id)
        source_sha = hashlib.sha256(archive_path.read_bytes()).hexdigest()
        with zipfile.ZipFile(archive_path) as zip_source:
            entries = _validated_members(zip_source)
            for entry in entries:
                path = entry.filename
                alias = collision_key(path)
                if alias in aliases and aliases[alias] != path:
                    raise ValueError('서로 다른 원본 ZIP 사이 Windows 경로 충돌: ' + path)
                aliases[alias] = path
                digest = hashlib.sha256()
                blob = hashlib.sha1()
                blob.update(b'blob ' + str(entry.file_size).encode('ascii') + b'\0')
                size = 0
                with zip_source.open(entry) as stream:
                    for chunk in iter(lambda: stream.read(1024 * 1024), b''):
                        size += len(chunk)
                        if size > entry.file_size or size > MAX_MEMBER_BYTES:
                            raise ValueError('원본 ZIP 압축 해제 크기 초과: ' + path)
                        digest.update(chunk)
                        blob.update(chunk)
                if size != entry.file_size:
                    raise ValueError('원본 ZIP 압축 해제 크기 불일치: ' + path)
                sha = digest.hexdigest()
                item = {'sha256': sha, 'git_blob_sha1': blob.hexdigest(), 'bytes': size,
                        'archive_sha256': source_sha, 'zip_entry': path}
                version = versions.setdefault(path, {}).setdefault(sha, {
                    'git_blob_sha1': item['git_blob_sha1'], 'bytes': size, 'sources': []})
                version['sources'].append({'archive_sha256': source_sha, 'zip_entry': path})
        if hashlib.sha256(archive_path.read_bytes()).hexdigest() != source_sha:
            raise ValueError('대조 도중 원본 ZIP이 변경되었습니다.')
        fingerprints.append({'archive': str(archive_path), 'sha256': source_sha,
                             'entries': len(entries)})
    if expected_paths is not None and len(versions) != expected_paths:
        raise ValueError(f'독립 원본 고유 경로 수 불일치: {len(versions)} / {expected_paths}')
    groups = {'unchanged': [], 'changed': [], 'missing': [],
              'historical_conflict': [], 'remote_type_conflict': []}
    tracked = set(versions)
    for path in sorted(tracked):
        possibilities = versions[path]
        entry = remote.get(path)
        current_sha = entry.get('sha') if entry else None
        result = {'path': path, 'versions': sorted(possibilities),
                  'remote_git_blob_sha1': current_sha}
        if len(possibilities) != 1:
            state = 'historical_conflict'
        elif entry is None:
            # Git tree에서 파일/폴더가 겹치면 해당 원본을 누락으로 복원할 수 없다.
            if any((other.startswith(path + '/') or path.startswith(other + '/'))
                   and entry_data.get('type') == 'blob'
                   for other, entry_data in remote.items()):
                state = 'remote_type_conflict'
            else:
                state = 'missing'
        elif entry.get('type') != 'blob' or entry.get('mode') not in ('100644', '100755'):
            state = 'remote_type_conflict'
        elif current_sha == next(iter(possibilities.values()))['git_blob_sha1']:
            state = 'unchanged'
        else:
            state = 'changed'
        groups[state].append(result)
    counts = {key: len(items) for key, items in groups.items()}
    unsafe = sum(counts[key] for key in counts if key != 'unchanged')
    return {
        'verified_archives': fingerprints,
        'original_paths_compared': len(tracked),
        'expected_original_paths': expected_paths,
        'full_expected_paths_compared': expected_paths is not None and len(tracked) == expected_paths,
        'complete_github_tree': True,
        'status_counts': counts, 'path_results': [r for state in groups.values() for r in state],
        'remote_only_paths': sorted(set(remote) - tracked),
        'manual_review_required': unsafe != 0,
        'all_paths_unchanged': unsafe == 0,
        'originals_preserved': True, 'github_main_updated': False,
        'all_development_merged': False,
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description='AIWACK 원본 ZIP 여러 개와 GitHub 전체 tree 일대일 대조')
    parser.add_argument('git_tree_json', type=Path, help='GitHub API truncated=false 전체 tree JSON')
    parser.add_argument('archives', nargs='+', type=Path)
    parser.add_argument('--expected-paths', type=int)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args(argv)
    try:
        tree = json.loads(args.git_tree_json.read_text(encoding='utf-8'))
        report = compare_zip_archives_to_github(args.archives, tree, args.expected_paths)
        output = json.dumps(report, ensure_ascii=False, indent=2) + '\n'
        if args.output:
            if args.output.exists() or args.output.is_symlink():
                raise FileExistsError('기존 결과 보고서는 덮어쓸 수 없습니다.')
            args.output.write_text(output, encoding='utf-8')
        print(output)
        return 2 if report['manual_review_required'] else 0
    except (OSError, ValueError, TypeError, KeyError, zipfile.BadZipFile) as exc:
        print(json.dumps({'verified': False, 'error': str(exc)}, ensure_ascii=False))
        return 3


if __name__ == '__main__':
    raise SystemExit(main())
