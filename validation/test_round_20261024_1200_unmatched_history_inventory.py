"""원본 ZIP에서 아직 증빙되지 않은 항목을 삭제 없이 표시한다."""
import hashlib
import zipfile

from validation.export_historical_version_evidence import export_historical_versions
from validation.verify_historical_against_archives import verify_against_archives


def test_unmatched_archive_entry_is_visible_without_false_full_success(tmp_path):
    archive = tmp_path / 'history.zip'
    with zipfile.ZipFile(archive, 'w') as out:
        out.writestr('docs/verified.md', 'verified')
        out.writestr('docs/untracked.md', 'untracked')
    audit = {'coverage_confirmed': True, 'distinct_original_paths': 1,
             'identical': [{'path': 'docs/verified.md',
                            'original_versions': [{'sha256': hashlib.sha256(b'verified').hexdigest()}]}],
             'changed': [], 'missing': [], 'version_conflicts': []}
    destination = tmp_path / 'evidence'
    export_historical_versions(audit, [archive], destination)
    result = verify_against_archives(destination)
    assert result['verified'] is True
    assert result['unmatched_archive_entries_total'] == 1
    assert result['unmatched_archive_entries_sample'] == [{
        'archive': str(archive), 'zip_entry': 'docs/untracked.md',
        'bytes': 9, 'zip_crc32': result['unmatched_archive_entries_sample'][0]['zip_crc32']}]
    assert result['unmatched_archive_entries_sample_truncated'] is False
    assert result['full_1099_originals_verified'] is False


def test_unmatched_archive_sample_limit_reports_total(tmp_path):
    archive = tmp_path / 'many.zip'
    with zipfile.ZipFile(archive, 'w') as out:
        out.writestr('docs/verified.md', 'verified')
        for number in range(105):
            out.writestr(f'docs/untracked_{number:03}.md', 'x')
    audit = {'coverage_confirmed': True, 'distinct_original_paths': 1,
             'identical': [{'path': 'docs/verified.md',
                            'original_versions': [{'sha256': hashlib.sha256(b'verified').hexdigest()}]}],
             'changed': [], 'missing': [], 'version_conflicts': []}
    destination = tmp_path / 'evidence'
    export_historical_versions(audit, [archive], destination)
    result = verify_against_archives(destination)
    assert result['unmatched_archive_entries_total'] == 105
    assert len(result['unmatched_archive_entries_sample']) == 100
    assert result['unmatched_archive_entries_sample_truncated'] is True
