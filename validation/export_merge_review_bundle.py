"""AIWACK 원본 보존형 3-way 병합 보류 파일의 검토 묶음을 별도 생성한다.

기존 main·테스트·과거 원본은 읽기 전용. 역사 다중버전은 자동 선택하지 않는다.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import tempfile

try:
    from validation.three_way_merge_review import review_three_way, _snapshot
except ImportError:
    from three_way_merge_review import review_three_way, _snapshot


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _verified_read(root: Path, relative: str, expected: str | None) -> bytes | None:
    if expected is None:
        return None
    target = root / relative
    if not target.is_file() or target.is_symlink() or not target.resolve().is_relative_to(root):
        raise ValueError('원본 경로가 변경됐거나 심볼릭 링크입니다: ' + relative)
    data = target.read_bytes()
    if _sha(data) != expected:
        raise ValueError('원본 SHA256이 검토 이후 변경됐습니다: ' + relative)
    return data


def export_review_bundle(audit: dict, main_root: Path, test_root: Path,
                         destination: Path, historical_root: Path | None = None) -> dict:
    """충돌·보류 원본을 SHA 증빙과 함께 보존한다. 어떤 원본도 수정하지 않는다."""
    main_root = Path(main_root).resolve(strict=True)
    test_root = Path(test_root).resolve(strict=True)
    history = Path(historical_root).resolve(strict=True) if historical_root else None
    destination = Path(destination).absolute()
    roots = [main_root, test_root] + ([history] if history else [])
    resolved_parent = destination.parent.resolve(strict=False)
    if (destination.exists() or any(
            destination == root or root in destination.parents
            or resolved_parent == root or root in resolved_parent.parents for root in roots)):
        raise ValueError('기존 파일 또는 원본 폴더에 검토 묶음을 덮어쓸 수 없습니다.')
    result = review_three_way(audit, main_root, test_root)
    if (result['unsafe'] or not result['historical_coverage_confirmed']
            or audit.get('unsafe') or audit.get('baseline_paths_unseen')
            or audit.get('baseline_paths_sha_mismatch')):
        raise ValueError('원본 전수 감사 또는 Windows 경로 안전검사가 완료되지 않았습니다.')
    history_hashes = {}
    if history:
        history_hashes, history_unsafe = _snapshot(history)
        if history_unsafe:
            raise ValueError('과거 원본 경로 안전검사 실패')
    before_main, _ = _snapshot(main_root)
    before_test, _ = _snapshot(test_root)
    destination.parent.mkdir(parents=True, exist_ok=True)
    scratch = Path(tempfile.mkdtemp(prefix='.aiwack-review-', dir=destination.parent))
    entries = []
    try:
        for index, row in enumerate(result['review_items'], 1):
            relative = row['path']
            case = scratch / 'cases' / f'{index:05d}'
            case.mkdir(parents=True)
            evidence = {'path': relative, 'classification': row['classification'],
                        'historical_sha256': row['historical_sha256'],
                        'main_sha256': row['main_sha256'],
                        'test_sha256': row['test_sha256'], 'files': {}}
            for label, root in [('main', main_root), ('test', test_root)]:
                raw = _verified_read(root, relative, row[label + '_sha256'])
                if raw is not None:
                    (case / (label + '.bin')).write_bytes(raw)
                    evidence['files'][label] = {'sha256': _sha(raw), 'bytes': len(raw)}
            hashes = row['historical_sha256']
            if history and len(hashes) == 1 and history_hashes.get(relative) == hashes[0]:
                raw = _verified_read(history, relative, hashes[0])
                (case / 'historical.bin').write_bytes(raw)
                evidence['files']['historical'] = {'sha256': _sha(raw), 'bytes': len(raw)}
            else:
                evidence['historical_export'] = '다중버전 또는 검증된 단일 원본 부재: 자동 선택 금지'
            entries.append(evidence)
        if _snapshot(main_root)[0] != before_main or _snapshot(test_root)[0] != before_test:
            raise ValueError('검토 묶음 생성 도중 원본이 변경됐습니다.')
        manifest = {'format': 'aiwack-three-way-review-v1', 'automatic_merge': False,
                    'github_main_updated': False, 'historical_version_conflicts':
                    result['historical_version_conflicts'], 'cases': entries}
        (scratch / 'manifest.json').write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        scratch.rename(destination)
    finally:
        if scratch.exists():
            shutil.rmtree(scratch)
    return {'destination': str(destination), 'review_cases': len(entries),
            'historical_version_conflicts': result['historical_version_conflicts'],
            'main_original_preserved': True, 'test_original_preserved': True,
            'github_main_updated': False}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description='AIWACK 충돌 원본 보존 검토 묶음 생성')
    parser.add_argument('audit', type=Path)
    parser.add_argument('main', type=Path)
    parser.add_argument('test', type=Path)
    parser.add_argument('destination', type=Path)
    parser.add_argument('--historical-root', type=Path)
    args = parser.parse_args(argv)
    try:
        result = export_review_bundle(json.loads(args.audit.read_text(encoding='utf-8')),
                                      args.main, args.test, args.destination, args.historical_root)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(json.dumps({'exported': False, 'error': str(exc)}, ensure_ascii=False))
        return 3
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
