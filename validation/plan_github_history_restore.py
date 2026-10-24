"""원본 ZIP과 GitHub Git tree의 실제 Blob SHA를 대조해 복원 대상을 결정한다.

원본 ZIP 및 GitHub 원격을 수정하지 않는다. 충돌은 덮어쓰지 않고 기록한다.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import stat
import zipfile
from pathlib import Path

try:
    from validation.restore_original_source_history import _validated_members
    from validation.windows_path_policy import collision_key, unsafe_part
except ImportError:
    from restore_original_source_history import _validated_members
    from windows_path_policy import collision_key, unsafe_part


def _git_blob_sha(raw: bytes) -> str:
    return hashlib.sha1(b'blob ' + str(len(raw)).encode('ascii') + b'\0' + raw).hexdigest()


def _checked_tree(tree: dict) -> dict[str, dict]:
    if not isinstance(tree, dict) or tree.get('truncated') is not False:
        raise ValueError('GitHub 전체 tree 확인 불가: truncated=false가 필요합니다.')
    entries = tree.get('tree')
    if not isinstance(entries, list):
        raise ValueError('GitHub tree 항목이 없습니다.')
    indexed = {}
    aliases = {}
    for entry in entries:
        if not isinstance(entry, dict):
            raise ValueError('GitHub tree 항목 형식 오류')
        path = entry.get('path')
        if (not isinstance(path, str) or not path or path.startswith('/')
                or '\\' in path or any(unsafe_part(part) for part in path.split('/'))
                or any(not part or part in ('.', '..') for part in path.split('/'))):
            raise ValueError('GitHub tree 위험 경로')
        if path in indexed:
            raise ValueError('GitHub tree 중복 경로: ' + path)
        key = collision_key(path)
        if key in aliases and aliases[key] != path:
            raise ValueError('GitHub tree Windows 경로 충돌: ' + path)
        aliases[key] = path
        indexed[path] = entry
    return indexed


def audit_github_history_restore(archive_path: Path, tree: dict) -> dict:
    """원본 ZIP을 읽어 동일·누락·내용 충돌을 Git Blob SHA1 기준으로 분류한다."""
    archive_path = Path(archive_path)
    if archive_path.is_symlink() or not archive_path.is_file():
        raise ValueError('원본 ZIP 일반 파일이 없습니다.')
    indexed = _checked_tree(tree)
    original_sha = hashlib.sha256(archive_path.read_bytes()).hexdigest()
    result = {'archive_sha256': original_sha, 'total': 0, 'identical': [],
              'missing': [], 'conflicts': [], 'restorable_paths': [],
              'github_main_updated': False, 'original_preserved': False}
    with zipfile.ZipFile(archive_path) as archive:
        members = _validated_members(archive)
        # GitHub tree의 디렉터리도 파일 복원 경로의 충돌 원인이 된다.
        git_aliases = {collision_key(path): path for path in indexed}
        for entry in members:
            path = entry.filename
            existing_alias = git_aliases.get(collision_key(path))
            if existing_alias is not None and existing_alias != path:
                raise ValueError('원본 ZIP과 GitHub Windows 경로 충돌: ' + path)
            with archive.open(entry) as stream:
                raw = stream.read(entry.file_size + 1)
            if len(raw) != entry.file_size:
                raise ValueError('원본 ZIP 압축 해제 크기 불일치: ' + path)
            sha = _git_blob_sha(raw)
            row = {'path': path, 'bytes': len(raw), 'git_blob_sha1': sha,
                   'sha256': hashlib.sha256(raw).hexdigest()}
            remote = indexed.get(path)
            if remote is None:
                # 동일 경로가 GitHub 디렉터리의 부모/자식일 경우 파일 생성 불가.
                if any(other.startswith(path + '/') or path.startswith(other + '/')
                       and indexed[other].get('type') != 'tree' for other in indexed):
                    result['conflicts'].append({**row, 'reason': 'git_path_parent_conflict'})
                else:
                    result['missing'].append(row)
                    result['restorable_paths'].append(row)
            elif (remote.get('type') == 'blob' and remote.get('mode') in ('100644', '100755')
                  and remote.get('sha') == sha):
                result['identical'].append(row)
            else:
                result['conflicts'].append({**row, 'reason': 'different_or_nonfile_remote',
                                            'remote_sha': remote.get('sha'),
                                            'remote_type': remote.get('type')})
        result['total'] = len(members)
    if hashlib.sha256(archive_path.read_bytes()).hexdigest() != original_sha:
        raise ValueError('검사 중 원본 ZIP이 변경됐습니다.')
    result['original_preserved'] = True
    result['safe_to_restore_without_overwrite'] = not result['conflicts']
    return result


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description='AIWACK 역사 원본 GitHub tree 원본 보존형 복원 계획')
    parser.add_argument('archive', type=Path)
    parser.add_argument('git_tree_json', type=Path)
    parser.add_argument('--report', type=Path)
    args = parser.parse_args(argv)
    try:
        tree = json.loads(args.git_tree_json.read_text(encoding='utf-8'))
        report = audit_github_history_restore(args.archive, tree)
    except (ValueError, OSError, TypeError, KeyError, zipfile.BadZipFile) as error:
        print(json.dumps({'verified': False, 'error': str(error)}, ensure_ascii=False))
        return 3
    output = json.dumps(report, ensure_ascii=False, indent=2) + '\n'
    if args.report:
        if args.report.exists():
            raise FileExistsError('기존 감사 보고서는 덮어쓰지 않습니다.')
        args.report.write_text(output, encoding='utf-8')
    print(output)
    return 2 if report['conflicts'] or report['missing'] else 0


if __name__ == '__main__':
    raise SystemExit(main())
