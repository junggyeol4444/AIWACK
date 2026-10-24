"""실제 ZIP 원본을 이용한 역사 버전 독립 대조 회귀."""
import hashlib
import json
import zipfile
import pytest
from validation.export_historical_version_evidence import export_historical_versions
from validation.verify_historical_against_archives import verify_against_archives


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def _fixture(tmp_path):
    archive = tmp_path / 'original.zip'
    with zipfile.ZipFile(archive, 'w') as out:
        out.writestr('docs/old.md', '원본 내용\n')
        out.writestr('docs/new.md', '신규 내용\n')
        out.writestr('untracked.txt', '별도 기록')
    audit = {'coverage_confirmed': True, 'distinct_original_paths': 2,
             'identical': [{'path': name, 'original_versions': [{'sha256': _sha(value.encode())}]}
                           for name, value in [('docs/old.md', '원본 내용\n'), ('docs/new.md', '신규 내용\n')]],
             'changed': [], 'missing': [], 'version_conflicts': []}
    root = tmp_path / 'evidence'
    export_historical_versions(audit, [archive], root)
    return archive, root


def test_independent_archive_bytes_and_counts(tmp_path):
    archive, root = _fixture(tmp_path)
    result = verify_against_archives(root)
    assert result['archive_files_checked'] == 1
    assert result['archive_entries_verified'] == 2
    assert result['verified_versions'] == 2
    assert result['independent_archive_comparison'] is True
    assert result['full_1099_originals_verified'] is False


def test_original_archive_replaced_is_rejected(tmp_path):
    archive, root = _fixture(tmp_path)
    with zipfile.ZipFile(archive, 'w') as out:
        out.writestr('docs/old.md', '변조')
    with pytest.raises(ValueError, match='SHA256'):
        verify_against_archives(root)


def test_manifest_source_crc_tamper_is_rejected(tmp_path):
    archive, root = _fixture(tmp_path)
    file = root / 'manifest.json'
    data = json.loads(file.read_text())
    data['paths'][0]['versions'][0]['sources'][0]['zip_crc32'] = '00000000'
    file.write_text(json.dumps(data, ensure_ascii=False))
    with pytest.raises(ValueError, match='CRC'):
        verify_against_archives(root)


def test_manifest_source_omission_is_rejected(tmp_path):
    archive, root = _fixture(tmp_path)
    file = root / 'manifest.json'
    data = json.loads(file.read_text())
    data['paths'][0]['versions'][0]['sources'] = []
    file.write_text(json.dumps(data, ensure_ascii=False))
    with pytest.raises(ValueError, match='항목 수'):
        verify_against_archives(root)


def test_evidence_file_tamper_is_rejected(tmp_path):
    archive, root = _fixture(tmp_path)
    data = json.loads((root / 'manifest.json').read_text())
    relative = data['paths'][0]['versions'][0]['evidence_path']
    (root / relative).write_bytes(b'changed')
    with pytest.raises(ValueError, match='SHA'):
        verify_against_archives(root)
