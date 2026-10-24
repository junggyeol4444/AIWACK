"""기존 누적 원본 병합의 SHA 증거와 미추적 ZIP 전수 검증 회귀."""
import hashlib
import zipfile

import pytest

from validation.stage_three_way_merge import stage_merge
from validation.export_historical_version_evidence import export_historical_versions
from validation import verify_historical_against_archives as archive_audit


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def roots(tmp_path, *, main_bytes=b'original', test_bytes=b'updated'):
    main = tmp_path / 'main'
    test = tmp_path / 'test'
    main.mkdir()
    test.mkdir()
    (main / 'core.py').write_bytes(main_bytes)
    (test / 'core.py').write_bytes(test_bytes)
    audit = {
        'coverage_confirmed': True,
        'identical': [{'path': 'core.py', 'original_versions': [
            {'sha256': sha(b'original')}]}],
        'changed': [], 'missing': [], 'version_conflicts': [],
    }
    return audit, main, test, tmp_path / 'staged'


def test_staging_reports_exact_merged_sha_without_changing_sources(tmp_path):
    audit, main, test, destination = roots(tmp_path)
    before_main = (main / 'core.py').read_bytes()
    before_test = (test / 'core.py').read_bytes()
    report = stage_merge(audit, main, test, destination)
    assert report['merged_path_hashes'] == {'core.py': sha(b'updated')}
    assert report['held_review_evidence'] == []
    assert (destination / 'core.py').read_bytes() == before_test
    assert (main / 'core.py').read_bytes() == before_main
    assert (test / 'core.py').read_bytes() == before_test
    assert not report['github_main_updated']


def test_unmergeable_divergence_records_both_source_hashes(tmp_path):
    audit, main, test, destination = roots(
        tmp_path, main_bytes=b'main-change', test_bytes=b'test-change')
    report = stage_merge(audit, main, test, destination)
    assert report['merged_path_hashes'] == {}
    assert report['held_for_manual_review'] == ['core.py']
    evidence = report['held_review_evidence']
    assert len(evidence) == 1
    assert evidence[0]['reason'] == 'historical_baseline_unavailable'
    assert evidence[0]['main_sha256'] == sha(b'main-change')
    assert evidence[0]['test_sha256'] == sha(b'test-change')
    assert evidence[0]['historical_sha256'] == [sha(b'original')]
    assert (destination / 'core.py').read_bytes() == b'main-change'


def _history_evidence(tmp_path):
    archive = tmp_path / 'history.zip'
    with zipfile.ZipFile(archive, 'w') as output:
        output.writestr('docs/verified.md', b'yes')
        output.writestr('docs/untracked.md', b'untracked')
    audit = {
        'coverage_confirmed': True,
        'distinct_original_paths': 1,
        'identical': [{'path': 'docs/verified.md', 'original_versions': [
            {'sha256': sha(b'yes')}]}],
        'changed': [], 'missing': [], 'version_conflicts': [],
    }
    destination = tmp_path / 'evidence'
    export_historical_versions(audit, [archive], destination)
    return archive, destination


def test_untracked_archive_entry_has_verified_hash_and_byte_count(tmp_path):
    archive, destination = _history_evidence(tmp_path)
    original_sha = sha(archive.read_bytes())
    report = archive_audit.verify_against_archives(destination)
    assert report['unmatched_archive_entries_total'] == 1
    assert report['unmatched_archive_entries_verified'] == 1
    assert report['unmatched_archive_bytes_verified'] == len(b'untracked')
    assert report['unmatched_archive_entries_sample'][0]['sha256'] == sha(b'untracked')
    assert report['full_1099_originals_verified'] is False
    assert sha(archive.read_bytes()) == original_sha


def test_untracked_archive_entry_obeys_decompression_limit(tmp_path, monkeypatch):
    _, destination = _history_evidence(tmp_path)
    monkeypatch.setattr(archive_audit, '_MAX_ENTRY_BYTES', 4)
    with pytest.raises(ValueError, match='미추적 원본 ZIP 항목 크기 제한 초과'):
        archive_audit.verify_against_archives(destination)
