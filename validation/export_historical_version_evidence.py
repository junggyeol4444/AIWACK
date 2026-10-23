"""AIWACK 1~21회차 원본 ZIP의 역사 버전을 선택 없이 개별 증빙 보존한다.

원본 ZIP 및 기존 main·테스트 코드를 수정하지 않는다. 감사에서 확인된
SHA256과 일치하는 바이트만 새 폴더에 보존하며 다중버전을 자동 병합하지 않는다.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import shutil
import tempfile
import zipfile

try:
    from validation.windows_path_policy import unsafe_part
except ImportError:
    from windows_path_policy import unsafe_part

_MAX_ENTRY_BYTES = 32 * 1024 * 1024
_MAX_TOTAL_BYTES = 512 * 1024 * 1024


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _safe_path(value: str) -> bool:
    if not isinstance(value, str) or not value or '\\' in value:
        return False
    path = PurePosixPath(value)
    return (not path.is_absolute() and str(path) == value
            and all(not unsafe_part(part) for part in path.parts))


def _expected_versions(audit: dict) -> dict[str, set[str]]:
    if not isinstance(audit, dict) or audit.get('coverage_confirmed') is not True:
        raise ValueError('원본 전수 감사 완료 증빙이 필요합니다.')
    expected = {}
    for section in ('identical', 'changed', 'missing'):
        rows = audit.get(section, [])
        if not isinstance(rows, list):
            raise ValueError('원본 감사 목록 형식 오류: ' + section)
        for row in rows:
            if not isinstance(row, dict) or not _safe_path(row.get('path')):
                raise ValueError('원본 감사 경로 형식 오류')
            path = row['path']
            if path in expected:
                raise ValueError('원본 감사 경로 중복: ' + path)
            versions = row.get('original_versions')
            if not isinstance(versions, list) or not versions:
                raise ValueError('원본 버전 정보 누락: ' + path)
            hashes = set()
            for version in versions:
                digest = version.get('sha256') if isinstance(version, dict) else None
                if (not isinstance(digest, str) or len(digest) != 64
                        or any(c not in '0123456789abcdef' for c in digest)):
                    raise ValueError('원본 SHA256 형식 오류: ' + path)
                hashes.add(digest)
            expected[path] = hashes
    if (not expected or audit.get('distinct_original_paths', len(expected)) != len(expected)):
        raise ValueError('원본 감사 파일 개수 불일치')
    conflicts = audit.get('version_conflicts', [])
    if not isinstance(conflicts, list):
        raise ValueError('역사 버전 충돌 감사 형식 오류')
    declared = set()
    for conflict in conflicts:
        path = conflict.get('path') if isinstance(conflict, dict) else None
        if path in declared or path not in expected or len(expected[path]) < 2:
            raise ValueError('역사 버전 충돌 목록 오류')
        hashes = conflict.get('distinct_sha256')
        if hashes is not None and (not isinstance(hashes, list) or set(hashes) != expected[path]):
            raise ValueError('역사 버전 충돌 SHA 불일치')
        declared.add(path)
    if {p for p, versions in expected.items() if len(versions) > 1} != declared:
        raise ValueError('역사 다중버전 충돌 감사 누락')
    return expected


def export_historical_versions(audit: dict, archives: list[Path], destination: Path) -> dict:
    """감사된 원본 ZIP에서 모든 일치 버전을 별도로 보존한다. 원본은 읽기 전용."""
    expected = _expected_versions(audit)
    if not archives:
        raise ValueError('원본 ZIP이 없습니다.')
    paths = [Path(archive).absolute() for archive in archives]
    if len(set(paths)) != len(paths):
        raise ValueError('중복 원본 ZIP 경로')
    for path in paths:
        if path.is_symlink() or not path.is_file() or path.suffix.lower() != '.zip':
            raise ValueError('원본 ZIP은 일반 파일이어야 합니다: ' + str(path))
    destination = Path(destination).absolute()
    if destination.exists():
        raise FileExistsError('기존 증빙 폴더는 덮어쓸 수 없습니다.')
    if any(destination == path or destination in path.parents for path in paths):
        raise ValueError('원본 ZIP 경로를 증빙 폴더로 사용할 수 없습니다.')
    destination.parent.mkdir(parents=True, exist_ok=True)
    scratch = Path(tempfile.mkdtemp(prefix='.aiwack-history-', dir=destination.parent))
    seen = {path: {} for path in expected}
    archives_info = []
    total_bytes = 0
    try:
        for archive in paths:
            original_hash = _sha(archive.read_bytes())
            archive_info = {'archive': str(archive), 'sha256': original_hash,
                            'matched_entries': 0, 'unmatched_entries': 0}
            with zipfile.ZipFile(archive) as bundle:
                for entry in bundle.infolist():
                    if entry.is_dir():
                        continue
                    if entry.filename not in expected:
                        archive_info['unmatched_entries'] += 1
                        continue
                    if entry.file_size > _MAX_ENTRY_BYTES:
                        raise ValueError('원본 ZIP 항목 크기 제한 초과: ' + entry.filename)
                    total_bytes += entry.file_size
                    if total_bytes > _MAX_TOTAL_BYTES:
                        raise ValueError('원본 ZIP 누적 압축 해제 제한 초과')
                    raw = bundle.read(entry)
                    if len(raw) != entry.file_size:
                        raise ValueError('원본 ZIP 파일 크기 불일치')
                    digest = _sha(raw)
                    if digest not in expected[entry.filename]:
                        archive_info['unmatched_entries'] += 1
                        continue
                    archive_info['matched_entries'] += 1
                    record = seen[entry.filename].setdefault(digest, [])
                    record.append({'archive': str(archive), 'zip_entry': entry.filename,
                                   'zip_crc32': f'{entry.CRC:08x}', 'bytes': len(raw)})
                    index = sorted(expected).index(entry.filename) + 1
                    folder = scratch / 'versions' / f'{index:05d}'
                    folder.mkdir(parents=True, exist_ok=True)
                    target = folder / (digest + '.bin')
                    if not target.exists():
                        target.write_bytes(raw)
                    elif _sha(target.read_bytes()) != digest:
                        raise ValueError('보존 산출물 SHA 불일치')
            if _sha(archive.read_bytes()) != original_hash:
                raise ValueError('검토 중 원본 ZIP이 변경됐습니다: ' + str(archive))
            archives_info.append(archive_info)
        rows = []
        for index, path in enumerate(sorted(expected), 1):
            rows.append({'path': path, 'expected_sha256': sorted(expected[path]),
                         'found_sha256': sorted(seen[path]),
                         'missing_sha256': sorted(expected[path] - set(seen[path])),
                         'historical_conflict': len(expected[path]) > 1,
                         'versions': [{'sha256': sha, 'sources': seen[path][sha],
                                       'evidence_path': f'versions/{index:05d}/{sha}.bin'}
                                      for sha in sorted(seen[path])]})
        complete = all(not row['missing_sha256'] for row in rows)
        manifest = {'format': 'aiwack-historical-versions-v1',
                    'audit_complete': True, 'all_versions_recovered': complete,
                    'automatic_version_selection': False, 'github_main_updated': False,
                    'archives': archives_info, 'paths': rows}
        (scratch / 'manifest.json').write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        scratch.rename(destination)
    finally:
        if scratch.exists():
            shutil.rmtree(scratch)
    return {'destination': str(destination), 'historical_paths': len(expected),
            'recovered_paths': sum(bool(row['found_sha256']) for row in rows),
            'recovered_versions': sum(len(row['found_sha256']) for row in rows),
            'missing_versions': sum(len(row['missing_sha256']) for row in rows),
            'all_versions_recovered': complete, 'github_main_updated': False}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description='AIWACK 원본 ZIP 역사 버전 전체 증빙 보존')
    parser.add_argument('audit', type=Path)
    parser.add_argument('destination', type=Path)
    parser.add_argument('archives', nargs='+', type=Path)
    args = parser.parse_args(argv)
    try:
        report = export_historical_versions(
            json.loads(args.audit.read_text(encoding='utf-8')), args.archives, args.destination)
    except (OSError, ValueError, TypeError, KeyError, zipfile.BadZipFile, RuntimeError) as exc:
        print(json.dumps({'exported': False, 'error': str(exc)}, ensure_ascii=False))
        return 3
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report['all_versions_recovered'] else 2


if __name__ == '__main__':
    raise SystemExit(main())
