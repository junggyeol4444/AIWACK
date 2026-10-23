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
    from validation.merge_disjoint_json_changes import merge_disjoint_json
except ImportError:
    from merge_disjoint_json_changes import merge_disjoint_json

try:
    from validation.three_way_merge_review import review_three_way, _snapshot
except ImportError:
    from three_way_merge_review import review_three_way, _snapshot


def stage_merge(audit: dict, main_root: Path, test_root: Path, destination: Path,
                historical_root: Path | None = None) -> dict:
    main_root = Path(main_root).resolve(strict=True)
    test_root = Path(test_root).resolve(strict=True)
    destination = Path(destination).absolute()
    # Resolve parent aliases before creating any staging directory.
    resolved_destination = destination.resolve(strict=False)
    if historical_root is not None:
        historical_root = Path(historical_root).resolve(strict=True)
        if not historical_root.is_dir():
            raise ValueError('과거 원본은 실제 폴더여야 합니다.')
    protected_roots = [main_root, test_root]
    if historical_root is not None:
        protected_roots.append(historical_root)
    if any(resolved_destination == root or root in resolved_destination.parents
           for root in protected_roots):
        raise ValueError('원본·테스트·과거 원본 내부에 병합 산출물을 만들 수 없습니다.')
    if destination.exists():
        raise FileExistsError('기존 병합 산출물을 덮어쓸 수 없습니다.')
    if main_root == test_root:
        raise ValueError('main과 테스트 원본은 서로 다른 폴더여야 합니다.')
    result = review_three_way(audit, main_root, test_root)
    if (result['unsafe'] or not result['historical_coverage_confirmed']
            or audit.get('unsafe') or audit.get('baseline_paths_unseen')
            or audit.get('baseline_paths_sha_mismatch')):
        raise ValueError('원본 전수 감사 또는 Windows 경로 안전검사 충돌·미완료로 병합 차단')
    historical_versions = {
        item['path']: {v['sha256'] for v in item['original_versions']}
        for group in ('identical', 'changed', 'missing')
        for item in audit.get(group, [])}
    original_paths = set(historical_versions)
    conflicts = audit.get('version_conflicts', [])
    if not isinstance(conflicts, list):
        raise ValueError('역사 버전 충돌 감사 형식 오류')
    conflict_paths = set()
    for conflict in conflicts:
        if not isinstance(conflict, dict) or not isinstance(conflict.get('path'), str):
            raise ValueError('역사 버전 충돌 감사 항목 오류')
        path = conflict['path']
        if path in conflict_paths or len(historical_versions.get(path, set())) < 2:
            raise ValueError('역사 버전 충돌 목록과 원본 SHA 이력 불일치: ' + path)
        reported = conflict.get('distinct_sha256')
        if reported is not None and (not isinstance(reported, list)
                                     or set(reported) != historical_versions[path]):
            raise ValueError('역사 버전 충돌 SHA 목록 불일치: ' + path)
        conflict_paths.add(path)
    if any(len(versions) > 1 and path not in conflict_paths
           for path, versions in historical_versions.items()):
        raise ValueError('원본 다중버전 감사 누락')
    eligible = []
    held = []
    merged_divergent = {}
    for item in result['review_items']:
        path, status = item['path'], item['classification']
        if path in conflict_paths:
            held.append(item)
            continue
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
            if merged is None and path.lower().endswith('.json'):
                merged = merge_disjoint_json(base, (main_root / path).read_bytes(),
                                             (test_root / path).read_bytes())
            if merged is None:
                held.append(item)
            else:
                eligible.append(item)
                merged_divergent[path] = merged
        else:
            held.append(item)
    # Same-in-both content does not resolve a multi-version historical baseline.
    held_paths = {item['path'] for item in held} | conflict_paths
    # 검토 시점의 main 바이트를 고정해 복사 중 동시 수정·추가를 차단한다.
    main_before, main_unsafe = _snapshot(main_root)
    if main_unsafe:
        raise ValueError('main 원본 경로 안전검사 실패')
    for item in result['review_items']:
        if main_before.get(item['path']) != item['main_sha256']:
            raise ValueError('main 원본이 검토 이후 변경됐습니다: ' + item['path'])
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
            if hashlib.sha256(target.read_bytes()).hexdigest() != main_before.get(rel.as_posix()):
                raise ValueError('main 원본 복사 중 변경됐습니다: ' + rel.as_posix())
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
        if main_hashes != main_before:
            raise ValueError('main 원본이 병합 도중 변경됐습니다.')
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
            'held_for_manual_review': sorted(held_paths),
            'historical_conflict_paths_held': sorted(conflict_paths),
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
