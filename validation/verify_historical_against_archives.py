"""AIWACK 보존 증빙을 원본 ZIP 바이트와 독립적으로 대조한다.

원본 ZIP·증빙·프로젝트 파일은 읽기만 한다. 누락·변조·위험 ZIP 항목은
성공으로 처리하지 않으며, 전체 1~21회차 전수 검증 여부는 별도로 기록한다.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import stat
import zipfile
from pathlib import Path

try:
    from validation.export_historical_version_evidence import _safe_path, _MAX_ENTRY_BYTES, _MAX_TOTAL_BYTES
    from validation.verify_historical_version_evidence import verify_evidence
    from validation.windows_path_policy import collision_key
except ImportError:
    from export_historical_version_evidence import _safe_path, _MAX_ENTRY_BYTES, _MAX_TOTAL_BYTES
    from verify_historical_version_evidence import verify_evidence
    from windows_path_policy import collision_key


def _hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def verify_against_archives(evidence_root: Path) -> dict:
    """매니페스트의 각 원본 ZIP·항목·SHA·CRC를 실제 ZIP에서 재검사한다."""
    evidence_root = Path(evidence_root).resolve(strict=True)
    local = verify_evidence(evidence_root)
    manifest = json.loads((evidence_root / 'manifest.json').read_text(encoding='utf-8'))
    archives = manifest.get('archives')
    if not isinstance(archives, list) or not archives:
        raise ValueError('원본 ZIP 출처 목록이 없습니다.')
    expected_sources = {}
    for row in manifest['paths']:
        for version in row['versions']:
            for source in version.get('sources', []):
                if not isinstance(source, dict):
                    raise ValueError('원본 출처 형식 오류')
                archive, entry = source.get('archive'), source.get('zip_entry')
                if not isinstance(archive, str) or entry != row['path']:
                    raise ValueError('원본 출처 경로 불일치')
                key = (archive, entry)
                if key in expected_sources:
                    raise ValueError('원본 ZIP 항목 출처 중복')
                expected_sources[key] = (version['sha256'], source.get('zip_crc32'), source.get('bytes'))
    seen_sources = set()
    seen_archives = set()
    checked_entries = 0
    for record in archives:
        if not isinstance(record, dict) or not isinstance(record.get('archive'), str):
            raise ValueError('원본 ZIP 출처 기록 오류')
        name = record['archive']
        if name in seen_archives:
            raise ValueError('원본 ZIP 출처 중복')
        seen_archives.add(name)
        path = Path(name)
        if path.is_symlink() or not path.is_file() or path.suffix.lower() != '.zip':
            raise ValueError('원본 ZIP 파일 누락·링크: ' + name)
        if _hash_file(path) != record.get('sha256'):
            raise ValueError('원본 ZIP 전체 SHA256 불일치: ' + name)
        matched, unmatched, total_bytes = 0, 0, 0
        aliases = set()
        with zipfile.ZipFile(path) as bundle:
            for item in bundle.infolist():
                name_in_zip = item.filename[:-1] if item.is_dir() else item.filename
                if not _safe_path(name_in_zip) or item.flag_bits & 1:
                    raise ValueError('원본 ZIP 위험 경로·암호화: ' + name_in_zip)
                mode = (item.external_attr >> 16) & 0o170000
                if item.is_dir():
                    if mode not in (0, stat.S_IFDIR):
                        raise ValueError('원본 ZIP 특수 디렉터리: ' + name_in_zip)
                    continue
                if mode not in (0, stat.S_IFREG):
                    raise ValueError('원본 ZIP 특수 파일: ' + name_in_zip)
                alias = collision_key(name_in_zip)
                if alias in aliases:
                    raise ValueError('원본 ZIP Windows 경로 충돌: ' + name_in_zip)
                aliases.add(alias)
                key = (record['archive'], name_in_zip)
                if key not in expected_sources:
                    unmatched += 1
                    continue
                if item.file_size > _MAX_ENTRY_BYTES:
                    raise ValueError('원본 ZIP 항목 크기 제한 초과: ' + name_in_zip)
                total_bytes += item.file_size
                if total_bytes > _MAX_TOTAL_BYTES:
                    raise ValueError('원본 ZIP 누적 해제 크기 제한 초과')
                raw = bundle.read(item)
                expected_sha, expected_crc, expected_bytes = expected_sources[key]
                if (len(raw) != expected_bytes or len(raw) != item.file_size
                        or hashlib.sha256(raw).hexdigest() != expected_sha
                        or f'{item.CRC:08x}' != expected_crc):
                    raise ValueError('원본 ZIP 항목 SHA·CRC·크기 불일치: ' + name_in_zip)
                if key in seen_sources:
                    raise ValueError('원본 출처 재사용')
                seen_sources.add(key)
                matched += 1
                checked_entries += 1
        if matched != record.get('matched_entries') or unmatched != record.get('unmatched_entries'):
            raise ValueError('원본 ZIP 항목 수·출처 기록 불일치')
        if _hash_file(path) != record['sha256']:
            raise ValueError('검사 중 원본 ZIP 변경')
    if seen_sources != set(expected_sources):
        raise ValueError('원본 ZIP 출처 누락')
    return {'verified': True, 'archive_files_checked': len(archives),
            'archive_entries_verified': checked_entries,
            'historical_paths': local['historical_paths'],
            'verified_versions': local['verified_versions'],
            'missing_versions': local['missing_versions'],
            'independent_archive_comparison': True,
            'full_1099_originals_verified': False,
            'github_main_updated': False}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description='AIWACK 원본 ZIP 독립 대조')
    parser.add_argument('evidence', type=Path)
    args = parser.parse_args(argv)
    try:
        result = verify_against_archives(args.evidence)
    except (OSError, ValueError, TypeError, KeyError, zipfile.BadZipFile, RuntimeError) as error:
        print(json.dumps({'verified': False, 'error': str(error)}, ensure_ascii=False))
        return 3
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result['missing_versions'] == 0 else 2


if __name__ == '__main__':
    raise SystemExit(main())
