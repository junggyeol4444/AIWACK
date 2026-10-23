"""기존 AIWACK main·테스트·과거 ZIP 3-way 원본 보존 병합 검토.

읽기 전용으로 SHA256 차이와 Windows 경로 충돌을 검출한다. 실제 병합·원본
복원·권한 우회·자동 main 반영은 수행하지 않는다. 개발 결과물의 손실을
막기 위한 기존 누적 프로젝트 검증 구성요소이다.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import stat

try:
    from validation.windows_path_policy import collision_key
except ImportError:
    from windows_path_policy import collision_key


def _snapshot(root: Path) -> tuple[dict[str, str], list[dict]]:
    root = Path(root).resolve(strict=True)
    if not root.is_dir():
        raise ValueError('비교 대상은 기존 소스 폴더여야 합니다.')
    hashes: dict[str, str] = {}
    unsafe: list[dict] = []
    aliases: dict[str, str] = {}
    for item in sorted(root.rglob('*')):
        rel = item.relative_to(root).as_posix()
        if rel == '.git' or rel.startswith('.git/'):
            continue
        key = collision_key(rel)
        previous = aliases.setdefault(key, rel)
        if previous != rel:
            unsafe.append({'path': rel, 'reason': 'windows_alias', 'other': previous})
        if item.is_symlink():
            unsafe.append({'path': rel, 'reason': 'symlink'})
            continue
        if item.is_dir():
            continue
        if not item.is_file() or not stat.S_ISREG(item.stat().st_mode):
            unsafe.append({'path': rel, 'reason': 'not_regular_file'})
            continue
        digest = hashlib.sha256()
        with item.open('rb') as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b''):
                digest.update(chunk)
        hashes[rel] = digest.hexdigest()
    return hashes, unsafe


def review_three_way(audit: dict, main_root: Path, test_root: Path) -> dict:
    """원본 이력별 SHA와 두 브랜치의 SHA를 분류하고 무단 병합을 차단한다."""
    if not isinstance(audit, dict) or not isinstance(audit.get('coverage_confirmed'), bool):
        raise ValueError('기존 원본 전수 감사 결과가 필요합니다.')
    historical: dict[str, set[str]] = {}
    for section in ('identical', 'changed', 'missing'):
        for row in audit.get(section, []):
            name = row['path']
            if name in historical:
                raise ValueError('원본 감사 경로 중복: '+name)
            hashes = {v['sha256'] for v in row['original_versions']}
            if not hashes or any(len(h) != 64 or any(c not in '0123456789abcdef' for c in h)
                                 for h in hashes):
                raise ValueError('원본 감사 SHA256 손상: '+name)
            historical[name] = hashes
    main, main_unsafe = _snapshot(main_root)
    test, test_unsafe = _snapshot(test_root)
    rows = []
    counts: dict[str, int] = {}
    for name in sorted(set(main) | set(test) | set(historical)):
        a, b, original = main.get(name), test.get(name), historical.get(name, set())
        if a == b and a is not None:
            status = 'same_in_both'
        elif a is None and b is None:
            status = 'missing_in_both'
        elif a is None:
            status = 'test_only'
        elif b is None:
            status = 'main_only'
        elif a in original and b not in original:
            status = 'test_changed_from_original'
        elif b in original and a not in original:
            status = 'main_changed_from_original'
        else:
            status = 'divergent_change'
        counts[status] = counts.get(status, 0) + 1
        if status != 'same_in_both' or (original and a not in original):
            rows.append({'path': name, 'classification': status,
                         'main_sha256': a, 'test_sha256': b,
                         'historical_sha256': sorted(original),
                         'historical_match_main': a in original if a else False,
                         'historical_match_test': b in original if b else False})
    return {
        'main_root': str(Path(main_root).resolve()),
        'test_root': str(Path(test_root).resolve()),
        'historical_paths': len(historical),
        'main_paths': len(main), 'test_paths': len(test),
        'classifications': counts, 'review_items': rows,
        'unsafe': [{'tree': 'main', **r} for r in main_unsafe]
                  + [{'tree': 'test', **r} for r in test_unsafe],
        'historical_version_conflicts': len(audit.get('version_conflicts', [])),
        'historical_coverage_confirmed': audit['coverage_confirmed'],
        'ready_for_main': bool(audit['coverage_confirmed']
                               and not audit.get('requires_manual_merge_review')
                               and not rows and not main_unsafe and not test_unsafe),
        'automatic_merge_performed': False,
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description='기존 AIWACK 원본 보존형 3-way 비교')
    parser.add_argument('archive_audit', type=Path)
    parser.add_argument('main_source', type=Path)
    parser.add_argument('test_source', type=Path)
    parser.add_argument('--report', type=Path)
    args = parser.parse_args(argv)
    try:
        audit = json.loads(args.archive_audit.read_text(encoding='utf-8'))
        result = review_three_way(audit, args.main_source, args.test_source)
    except (ValueError, OSError, KeyError, TypeError) as error:
        print(json.dumps({'verified': False, 'error': str(error)}, ensure_ascii=False))
        return 3
    body = json.dumps(result, ensure_ascii=False, indent=2) + '\n'
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(body, encoding='utf-8')
    print(body)
    return 0 if result['ready_for_main'] else 2


if __name__ == '__main__':
    raise SystemExit(main())
