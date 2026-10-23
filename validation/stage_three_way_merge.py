"""기존 AIWACK 소스의 충돌 없는 변경만 별도 폴더에 실제 병합한다.

main, 테스트, 과거 원본 폴더를 절대 수정하지 않는다. 역사 충돌·위험 경로가
있으면 중단한다. 변경된 main 원본에 대한 덮어쓰기는 수행하지 않는다.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import tempfile

try:
    from validation.merge_disjoint_text_changes import merge_disjoint_text
except ImportError:
    from merge_disjoint_text_changes import merge_disjoint_text

try:
    from validation.three_way_merge_review import review_three_way, _snapshot
except ImportError:
    from three_way_merge_review import review_three_way, _snapshot


def stage_merge(audit: dict, main_root: Path, test_root: Path, destination: Path,
                historical_root: Path | None = None) -> dict:
    main_root = Path(main_root).resolve(strict=True)
    test_root = Path(test_root).resolve(strict=True)
    destination = Path(destination).absolute()
    if historical_root is not None:
        historical_root = Path(historical_root).resolve(strict=True)
        if not historical_root.is_dir():
            raise ValueError('과거 원본은 실제 폴더여야 합니다.')
    if destination.exists():
        raise FileExistsError('기존 병합 산출물을 덮어쓸 수 없습니다.')
    if main_root == test_root or main_root in destination.parents or test_root in destination.parents:
        raise ValueError('원본 또는 테스트 폴더 내부에 병합 산출물을 만들 수 없습니다.')
    result = review_three_way(audit, main_root, test_root)
    if (result['unsafe'] or not result['historical_coverage_confirmed']
            or result['historical_version_conflicts']
            or audit.get('unsafe') or audit.get('baseline_paths_unseen')
            or audit.get('baseline_paths_sha_mismatch')):
        raise ValueError('역사 원본/Windows 경로 충돌 또는 감사 미완료로 병합 차단')
    original_paths = {
        item['path'] for group in ('identical', 'changed', 'missing')
        for item in audit.get(group, [])}
    eligible = []
    held = []
    merged_divergent = {}
    for item in result['review_items']:
        path, status = item['path'], item['classification']
        if status == 'test_changed_from_original' or (
                status == 'test_only' and path not in original_paths):
            eligible.append(item)
        elif status == 'divergent_change' and historical_root is not None:
            historical = item['historical_sha256']
            # 여러 과거 버전은 기준점이 불명확하여 자동 병합하지 않는다.
            if len(historical) != 1:
                held.append(item)
                continue
            base_file = historical_root / path
            if not base_file.is_file() or base_file.is_symlink():
                held.append(item)
                continue
            base = base_file.read_bytes()
            if hashlib.sha256(base).hexdigest() != historical[0]:
                held.append(item)
                continue
            merged = merge_disjoint_text(base, (main_root / path).read_bytes(),
                                         (test_root / path).read_bytes())
            if merged is None:
                held.append(item)
            else:
                eligible.append(item)
                merged_divergent[path] = merged
        else:
            held.append(item)
    destination.parent.mkdir(parents=True, exist_ok=True)
    scratch = Path(tempfile.mkdtemp(prefix='.aiwack-merge-', dir=destination.parent))
    try:
        for source in sorted(main_root.rglob('*')):
            if source.is_dir() or '.git' in source.relative_to(main_root).parts:
                continue
            rel = source.relative_to(main_root)
            target = scratch / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
        for item in eligible:
            source = test_root / item['path']
            target = scratch / item['path']
            if hashlib.sha256(source.read_bytes()).hexdigest() != item['test_sha256']:
                raise ValueError('테스트 소스가 감사 후 변경됐습니다: ' + item['path'])
            main_source = main_root / item['path']
            if item['path'] in merged_divergent and (
                    not main_source.is_file() or
                    hashlib.sha256(main_source.read_bytes()).hexdigest() != item['main_sha256']):
                raise ValueError('main 소스가 감사 후 변경됐습니다: ' + item['path'])
            if target.exists() and item['classification'] not in (
                    'test_changed_from_original', 'divergent_change'):
                raise ValueError('신규 경로가 기존 원본과 충돌합니다: ' + item['path'])
            target.parent.mkdir(parents=True, exist_ok=True)
            if item['path'] in merged_divergent:
                target.write_bytes(merged_divergent[item['path']]['content'])
            else:
                shutil.copyfile(source, target)
        staged, unsafe = _snapshot(scratch)
        if unsafe:
            raise ValueError('병합 산출물 Windows 경로 충돌: ' + str(unsafe[:2]))
        for item in eligible:
            expected = (merged_divergent[item['path']]['sha256']
                        if item['path'] in merged_divergent else item['test_sha256'])
            if staged.get(item['path']) != expected:
                raise ValueError('병합 산출물 SHA 불일치: ' + item['path'])
        main_hashes, _ = _snapshot(main_root)
        merged_names = {item['path'] for item in eligible}
        for path, sha in main_hashes.items():
            if path not in merged_names and staged.get(path) != sha:
                raise ValueError('기존 main 원본 손실 또는 변조: ' + path)
        scratch.rename(destination)
    finally:
        if scratch.exists():
            shutil.rmtree(scratch)
    return {'staging_path': str(destination), 'staged_paths': len(staged),
            'merged_paths': [item['path'] for item in eligible],
            'merged_divergent_evidence': {
                path: {k: v for k, v in data.items() if k != 'content'}
                for path, data in merged_divergent.items()},
            'held_for_manual_review': [item['path'] for item in held],
            'main_original_preserved': True, 'test_original_preserved': True,
            'github_main_updated': False}


def main(argv=None):
    parser = argparse.ArgumentParser(description='AIWACK 충돌 없는 변경 원본 보존 병합')
    parser.add_argument('audit', type=Path)
    parser.add_argument('main', type=Path)
    parser.add_argument('test', type=Path)
    parser.add_argument('staging', type=Path)
    parser.add_argument('--historical-root', type=Path)
    args = parser.parse_args(argv)
    try:
        result = stage_merge(json.loads(args.audit.read_text(encoding='utf-8')),
                             args.main, args.test, args.staging, args.historical_root)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(json.dumps({'merged': False, 'error': str(exc)}, ensure_ascii=False))
        return 3
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if not result['held_for_manual_review'] else 2


if __name__ == '__main__':
    raise SystemExit(main())
