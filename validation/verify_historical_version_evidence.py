"""AIWACK 역사 원본 버전 증빙의 독립 바이트 재검사(읽기 전용).

이 검사는 보존된 증빙 폴더 자체의 완전성만 확인한다. 원본 ZIP과
독립적으로 동일하다는 주장은 별도 원본 ZIP SHA 재검사가 필요하다.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

try:
    from validation.windows_path_policy import collision_key, unsafe_part
except ImportError:
    from windows_path_policy import collision_key, unsafe_part


def _sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def verify_evidence(root: Path) -> dict:
    """증빙의 모든 버전을 누락·추가·변조 없이 재확인한다. 원본을 수정하지 않는다."""
    root = Path(root).absolute()
    if not root.is_dir() or root.is_symlink():
        raise ValueError('증빙 폴더는 실제 디렉터리여야 합니다.')
    manifest_file = root / 'manifest.json'
    if manifest_file.is_symlink() or not manifest_file.is_file():
        raise ValueError('증빙 매니페스트가 없거나 링크입니다.')
    manifest = json.loads(manifest_file.read_text(encoding='utf-8'))
    if (not isinstance(manifest, dict)
            or manifest.get('format') != 'aiwack-historical-versions-v1'
            or manifest.get('audit_complete') is not True
            or manifest.get('automatic_version_selection') is not False):
        raise ValueError('증빙 매니페스트 계약이 유효하지 않습니다.')
    rows = manifest.get('paths')
    if not isinstance(rows, list) or not rows:
        raise ValueError('역사 원본 경로 목록이 비어 있습니다.')
    seen_paths, seen_aliases, expected_files = set(), set(), {'manifest.json'}
    verified_versions = 0
    missing_versions = 0
    for index, row in enumerate(rows, 1):
        if not isinstance(row, dict) or not isinstance(row.get('path'), str):
            raise ValueError('역사 경로 형식 오류')
        name = row['path']
        if (not name or name.startswith('/') or '\\' in name
                or any(unsafe_part(part) for part in name.split('/'))):
            raise ValueError('역사 원본 위험 경로: ' + name)
        alias = collision_key(name)
        if name in seen_paths or alias in seen_aliases:
            raise ValueError('역사 원본 경로 중복·Windows 충돌: ' + name)
        seen_paths.add(name); seen_aliases.add(alias)
        expected = row.get('expected_sha256')
        found = row.get('found_sha256')
        missing = row.get('missing_sha256')
        versions = row.get('versions')
        if not all(isinstance(x, list) for x in (expected, found, missing, versions)):
            raise ValueError('역사 버전 목록 형식 오류: ' + name)
        if (not expected or len(set(expected)) != len(expected)
                or any(not isinstance(s, str) or len(s) != 64
                       or any(c not in '0123456789abcdef' for c in s) for s in expected)
                or set(found) | set(missing) != set(expected)
                or set(found) & set(missing)
                or len(found) != len(set(found))
                or len(versions) != len(found)):
            raise ValueError('역사 버전 SHA 목록 불일치: ' + name)
        if bool(row.get('historical_conflict')) != (len(expected) > 1):
            raise ValueError('역사 버전 충돌 증빙 불일치: ' + name)
        if {version.get('sha256') for version in versions if isinstance(version, dict)} != set(found):
            raise ValueError('역사 증빙 버전 누락·중복: ' + name)
        for version in versions:
            if not isinstance(version, dict):
                raise ValueError('역사 버전 항목 형식 오류')
            digest = version.get('sha256')
            relative = version.get('evidence_path')
            if digest not in found or relative != f'versions/{index:05d}/{digest}.bin':
                raise ValueError('역사 증빙 경로/SHA 불일치: ' + name)
            file = root / relative
            if (file.is_symlink() or not file.is_file()
                    or any(parent.is_symlink() for parent in file.parents if parent != root)):
                raise ValueError('역사 증빙 파일 누락·링크: ' + relative)
            if _sha(file) != digest:
                raise ValueError('역사 증빙 파일 SHA 변조: ' + relative)
            expected_files.add(relative)
            verified_versions += 1
        missing_versions += len(missing)
    # 증빙 폴더의 예상하지 못한 파일을 조용히 무시하지 않는다.
    for file in root.rglob('*'):
        relative = file.relative_to(root).as_posix()
        if file.is_symlink():
            raise ValueError('증빙 폴더에 링크가 있습니다: ' + relative)
        if file.is_file() and relative not in expected_files:
            raise ValueError('증빙 폴더에 미등록 파일이 있습니다: ' + relative)
    if manifest.get('all_versions_recovered') is not (missing_versions == 0):
        raise ValueError('역사 증빙 완료 표시 불일치')
    return {'verified': True, 'historical_paths': len(rows),
            'verified_versions': verified_versions,
            'missing_versions': missing_versions,
            'self_consistent': True, 'independent_archive_comparison': False,
            'github_main_updated': False}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description='AIWACK 역사 버전 증빙 재검사')
    parser.add_argument('evidence', type=Path)
    args = parser.parse_args(argv)
    try:
        result = verify_evidence(args.evidence)
    except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError) as error:
        print(json.dumps({'verified': False, 'error': str(error)}, ensure_ascii=False))
        return 3
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result['missing_versions'] == 0 else 2


if __name__ == '__main__':
    raise SystemExit(main())
