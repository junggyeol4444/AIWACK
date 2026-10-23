"""이전 누적 SHA256 원본 스냅샷과 현재 EXE 프로젝트 파일을 전수 대조한다.

읽기 전용. 원본/패치/문서를 절대 삭제하거나 덮어쓰지 않으며, 서로 다른
바이트를 합쳐서 동일하다고 주장하지 않는다. 실제 과거 파일이 없는 경우
그 파일이 검증됐다고 주장하지 않는다.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import stat


def _paths(manifest: dict) -> dict[str, str]:
    if not isinstance(manifest, dict) or not isinstance(manifest.get('source_sha256'), dict):
        raise ValueError('원본 source_sha256 맵이 있는 누적 매니페스트가 필요합니다.')
    old = manifest['source_sha256']
    result = {}
    folded = set()
    for raw, digest in old.items():
        if not isinstance(raw, str) or not isinstance(digest, str):
            raise ValueError('원본 경로 또는 SHA256 타입 오류')
        p = PurePosixPath(raw)
        if (not raw or raw != p.as_posix() or p.is_absolute() or '\\' in raw
                or ':' in raw or any(s in ('', '.', '..') or s.endswith((' ', '.')) for s in raw.split('/'))
                or len(digest) != 64 or any(c not in '0123456789abcdef' for c in digest.lower())):
            raise ValueError('매니페스트 원본 경로 또는 SHA256 형식 오류')
        if raw.casefold() in folded:
            raise ValueError('Windows 대소문자 충돌 원본 경로')
        folded.add(raw.casefold())
        result[raw] = digest.lower()
    return result


def audit(manifest_path: Path, root_path: Path) -> dict:
    """바이트 SHA 비교; symlink·비정규 파일 검사 후 모든 변경을 분류한다."""
    root = Path(root_path).resolve(strict=True)
    if not root.is_dir():
        raise ValueError('대조할 원본 저장소 폴더가 아닙니다.')
    manifest_path = Path(manifest_path)
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    original = _paths(manifest)
    result = {'snapshot': str(manifest_path), 'root': str(root),
              'verified_identical': [], 'modified': [], 'missing': [], 'unsafe': [],
              'new_files': [], 'source_paths': len(original)}
    for name, expected in sorted(original.items()):
        candidate = root.joinpath(*PurePosixPath(name).parts)
        if any(parent.is_symlink() for parent in (candidate, *candidate.parents) if parent != root):
            result['unsafe'].append({'path': name, 'reason': 'symlink'})
            continue
        if not candidate.is_file():
            result['missing'].append({'path': name, 'original_sha256': expected})
            continue
        if not stat.S_ISREG(candidate.stat().st_mode):
            result['unsafe'].append({'path': name, 'reason': 'not_regular'})
            continue
        h = hashlib.sha256()
        with candidate.open('rb') as source:
            for chunk in iter(lambda: source.read(1024 * 1024), b''):
                h.update(chunk)
        current = h.hexdigest()
        row = {'path': name, 'original_sha256': expected, 'current_sha256': current}
        result['verified_identical' if current == expected else 'modified'].append(row)
    for candidate in sorted(root.rglob('*')):
        if candidate.is_symlink():
            relative = candidate.relative_to(root).as_posix()
            if relative not in original:
                result['unsafe'].append({'path': relative, 'reason': 'new_symlink'})
            continue
        if candidate.is_file():
            relative = candidate.relative_to(root).as_posix()
            if relative not in original and not relative.startswith(('.git/', '__pycache__/')):
                result['new_files'].append(relative)
    result['snapshot_fully_identical'] = not (result['missing'] or result['modified'] or result['unsafe'])
    # Different versions may be valid cumulative work; 'modified' is not silently failure/preservation proof.
    result['requires_manual_merge_review'] = bool(result['modified'] or result['missing'] or result['unsafe'])
    return result


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description='AIWACK 이전 누적 원본 100% SHA 대조 (읽기 전용)')
    parser.add_argument('manifest', type=Path)
    parser.add_argument('repository', type=Path)
    parser.add_argument('--report', type=Path)
    args = parser.parse_args(argv)
    try:
        result = audit(args.manifest, args.repository)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(json.dumps({'error': str(error), 'verified': False}, ensure_ascii=False))
        return 3
    output = json.dumps(result, ensure_ascii=False, indent=2)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(output + '\n', encoding='utf-8')
    print(output)
    return 2 if result['requires_manual_merge_review'] else 0


if __name__ == '__main__':
    raise SystemExit(main())
