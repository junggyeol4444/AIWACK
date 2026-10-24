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
    unmatched_entries_total = 0
    unmatched_entries_verified = 0
    unmatched_bytes_verified = 0
    unmatched_entries_sample = []
    _MAX_UNMATCHED_SAMPLE = 100
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
                    # 증빙 목록에서 누락된 항목도 실제 압축 해제·CRC·SHA 검사를
                    # 수행한다. 이름·CRC만으로 역사 원본을 확인했다고 하지 않는다.
                    if item.file_size > _MAX_ENTRY_BYTES:
                        raise ValueError('미추적 원본 ZIP 항목 크기 제한 초과: ' + name_in_zip)
                    total_bytes += item.file_size
                    if total_bytes > _MAX_TOTAL_BYTES:
                        raise ValueError('원본 ZIP 누적 해제 크기 제한 초과')
                    digest = hashlib.sha256()
                    read_bytes = 0
                    with bundle.open(item) as stream:
                        for block in iter(lambda: stream.read(1024 * 1024), b''):
                            read_bytes += len(block)
                            if read_bytes > item.file_size:
                                raise ValueError('미추적 원본 ZIP 압축 해제 크기 불일치: ' + name_in_zip)
                            digest.update(block)
                    if read_bytes != item.file_size:
                        raise ValueError('미추적 원본 ZIP 크기 불일치: ' + name_in_zip)
                    unmatched += 1
                    unmatched_entries_total += 1
                    unmatched_entries_verified += 1
                    unmatched_bytes_verified += read_bytes
                    if len(unmatched_entries_sample) < _MAX_UNMATCHED_SAMPLE:
                        unmatched_entries_sample.append({
                            'archive': record['archive'], 'zip_entry': name_in_zip,
                            'bytes': read_bytes, 'zip_crc32': f'{item.CRC:08x}',
                            'sha256': digest.hexdigest()})
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
            'unmatched_archive_entries_total': unmatched_entries_total,
            'unmatched_archive_entries_verified': unmatched_entries_verified,
            'unmatched_archive_bytes_verified': unmatched_bytes_verified,
            'unmatched_archive_entries_sample': unmatched_entries_sample,
            'unmatched_archive_entries_sample_truncated': (
                unmatched_entries_total > len(unmatched_entries_sample)),
            'full_1099_originals_verified': False,
            'github_main_updated': False}



def compare_checkout_with_archives(evidence_root: Path, checkout_root: Path) -> dict:
    """실제 ZIP과 증빙을 먼저 검증한 뒤 기존 소스 트리 1:1 SHA 차이를 읽기 전용으로 기록한다.

    다중 역사 버전은 현재 체크아웃이 어느 한 버전과 일치해도
    자동 채택하지 않는다. '비교 완료'와 '병합 완료'는 별개다.
    """
    try:
        from validation.three_way_merge_review import _snapshot
    except ImportError:
        from three_way_merge_review import _snapshot

    archive_report = verify_against_archives(evidence_root)
    manifest = json.loads((Path(evidence_root) / 'manifest.json').read_text(encoding='utf-8'))
    checkout_root = Path(checkout_root).resolve(strict=True)
    if not checkout_root.is_dir():
        raise ValueError('현재 소스 비교 대상은 폴더여야 합니다.')
    before, unsafe = _snapshot(checkout_root)
    if unsafe:
        raise ValueError('현재 소스 Windows 경로 안전검사 실패: ' + str(unsafe[:2]))
    details = []
    seen = set()
    counts = {'unchanged': 0, 'changed': 0, 'missing': 0,
              'historical_conflict_matching': 0, 'historical_conflict_changed': 0}
    for row in manifest['paths']:
        name = row['path']
        if name in seen:
            raise ValueError('역사 경로 중복: ' + name)
        seen.add(name)
        expected = sorted(row['expected_sha256'])
        actual = before.get(name)
        if len(expected) > 1:
            state = ('historical_conflict_matching' if actual in expected
                     else 'historical_conflict_changed')
        elif actual is None:
            state = 'missing'
        elif actual == expected[0]:
            state = 'unchanged'
        else:
            state = 'changed'
        counts[state] += 1
        details.append({'path': name, 'status': state,
                        'checkout_sha256': actual,
                        'historical_sha256': expected,
                        'manual_review_required': state != 'unchanged'})
    after, unsafe_after = _snapshot(checkout_root)
    if unsafe_after or after != before:
        raise ValueError('비교 중 현재 소스가 변경되었거나 경로 안전검사가 실패했습니다.')
    untracked = sorted(set(before) - seen)
    full = (len(seen) == 1099 and archive_report['missing_versions'] == 0
            and archive_report['unmatched_archive_entries_total'] == 0)
    return {'comparison_completed': True,
            'independent_archive_comparison': True,
            'historical_paths_compared': len(seen),
            'archive_entries_verified': archive_report['archive_entries_verified'],
            'unmatched_archive_entries_total': archive_report['unmatched_archive_entries_total'],
            'missing_historical_versions': archive_report['missing_versions'],
            'full_1099_originals_compared': full,
            'status_counts': counts, 'path_results': details,
            'checkout_only_paths': untracked,
            'manual_review_required': (any(v for k, v in counts.items() if k != 'unchanged')
                                       or archive_report['missing_versions'] != 0
                                       or archive_report['unmatched_archive_entries_total'] != 0),
            'checkout_original_preserved': True, 'github_main_updated': False}



def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description='AIWACK 원본 ZIP 독립 대조')
    parser.add_argument('evidence', type=Path)
    parser.add_argument('--checkout-root', type=Path,
                        help='원본 ZIP과 현재 소스 파일의 SHA256을 읽기 전용 대조')
    args = parser.parse_args(argv)
    try:
        result = (compare_checkout_with_archives(args.evidence, args.checkout_root)
                  if args.checkout_root is not None else verify_against_archives(args.evidence))
    except (OSError, ValueError, TypeError, KeyError, zipfile.BadZipFile, RuntimeError) as error:
        print(json.dumps({'verified': False, 'error': str(error)}, ensure_ascii=False))
        return 3
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if args.checkout_root is not None:
        return 2 if result['manual_review_required'] else 0
    return 0 if result['missing_versions'] == 0 else 2


if __name__ == '__main__':
    raise SystemExit(main())
