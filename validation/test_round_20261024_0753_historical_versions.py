"""AIWACK 역사 원본 ZIP 다중버전 개별 증빙 기능 회귀."""
import hashlib
import json
import zipfile

import pytest

from validation.export_historical_version_evidence import export_historical_versions


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def audit(paths):
    rows = [{'path': name, 'original_versions': [{'sha256': sha(v)} for v in values]}
            for name, values in paths.items()]
    return {'coverage_confirmed': True, 'distinct_original_paths': len(rows),
            'identical': rows, 'changed': [], 'missing': [],
            'version_conflicts': [{'path': name, 'distinct_sha256': [sha(v) for v in values]}
                                  for name, values in paths.items() if len(set(values)) > 1]}


def archive(path, entries):
    with zipfile.ZipFile(path, 'w') as z:
        for name, data in entries:
            z.writestr(name, data)
    return path


def test_multiple_versions_preserved_without_selection(tmp_path):
    a, b = b'v1', b'v2'
    first = archive(tmp_path / 'one.zip', [('legacy.py', a)])
    second = archive(tmp_path / 'two.zip', [('legacy.py', b)])
    out = tmp_path / 'proof'
    report = export_historical_versions(audit({'legacy.py': [a, b]}), [first, second], out)
    assert report['all_versions_recovered'] and report['recovered_versions'] == 2
    manifest = json.loads((out / 'manifest.json').read_text())
    assert not manifest['automatic_version_selection']
    assert len(manifest['paths'][0]['versions']) == 2
    assert {(out / v['evidence_path']).read_bytes() for v in manifest['paths'][0]['versions']} == {a, b}


def test_partial_archive_keeps_missing_evidence(tmp_path):
    a, b = b'v1', b'v2'
    zip_path = archive(tmp_path / 'one.zip', [('legacy.py', a)])
    report = export_historical_versions(audit({'legacy.py': [a, b]}), [zip_path], tmp_path / 'out')
    assert not report['all_versions_recovered']
    assert report['missing_versions'] == 1
    manifest = json.loads((tmp_path / 'out' / 'manifest.json').read_text())
    assert manifest['paths'][0]['missing_sha256'] == [sha(b)]


def test_unknown_version_is_never_preserved(tmp_path):
    path = archive(tmp_path / 'one.zip', [('legacy.py', b'unknown')])
    report = export_historical_versions(audit({'legacy.py': [b'known']}), [path], tmp_path / 'out')
    assert report['recovered_versions'] == 0
    assert not (tmp_path / 'out' / 'versions').exists()


def test_original_zip_bytes_remain_identical(tmp_path):
    path = archive(tmp_path / 'one.zip', [('legacy.py', b'v1')])
    before = path.read_bytes()
    export_historical_versions(audit({'legacy.py': [b'v1']}), [path], tmp_path / 'out')
    assert path.read_bytes() == before


def test_existing_output_is_never_overwritten(tmp_path):
    path = archive(tmp_path / 'one.zip', [('legacy.py', b'v1')])
    out = tmp_path / 'out'
    out.mkdir()
    (out / 'keep').write_text('untouched')
    with pytest.raises(FileExistsError):
        export_historical_versions(audit({'legacy.py': [b'v1']}), [path], out)
    assert (out / 'keep').read_text() == 'untouched'


def test_traversal_path_rejected_before_extraction(tmp_path):
    path = archive(tmp_path / 'one.zip', [('../escape.py', b'v1')])
    with pytest.raises(ValueError):
        export_historical_versions(audit({'../escape.py': [b'v1']}), [path], tmp_path / 'out')
    assert not (tmp_path / 'out').exists()


def test_multiversion_audit_conflict_omission_rejected(tmp_path):
    path = archive(tmp_path / 'one.zip', [('legacy.py', b'v1')])
    record = audit({'legacy.py': [b'v1', b'v2']})
    record['version_conflicts'] = []
    with pytest.raises(ValueError):
        export_historical_versions(record, [path], tmp_path / 'out')


def test_duplicate_archive_path_rejected(tmp_path):
    path = archive(tmp_path / 'one.zip', [('legacy.py', b'v1')])
    with pytest.raises(ValueError):
        export_historical_versions(audit({'legacy.py': [b'v1']}), [path, path], tmp_path / 'out')


def test_matching_version_multiple_archives_keeps_provenance(tmp_path):
    a = b'v1'
    first = archive(tmp_path / 'one.zip', [('legacy.py', a)])
    second = archive(tmp_path / 'two.zip', [('legacy.py', a)])
    report = export_historical_versions(audit({'legacy.py': [a]}), [first, second], tmp_path / 'out')
    assert report['recovered_versions'] == 1
    manifest = json.loads((tmp_path / 'out' / 'manifest.json').read_text())
    assert len(manifest['paths'][0]['versions'][0]['sources']) == 2
