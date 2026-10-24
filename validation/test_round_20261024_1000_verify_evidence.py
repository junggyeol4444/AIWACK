"""원본 보존 증빙의 누락·변조·임의 추가를 탐지한다."""
import hashlib
import json
import zipfile

import pytest
from validation.export_historical_version_evidence import export_historical_versions
from validation.verify_historical_version_evidence import verify_evidence


def _evidence(tmp_path):
    source = tmp_path / 'source.zip'
    data = b'preserved-original'
    with zipfile.ZipFile(source, 'w') as archive:
        archive.writestr('history.txt', data)
    digest = hashlib.sha256(data).hexdigest()
    audit = {'coverage_confirmed': True, 'distinct_original_paths': 1,
             'identical': [{'path': 'history.txt', 'original_versions': [{'sha256': digest}]}],
             'changed': [], 'missing': [], 'version_conflicts': []}
    folder = tmp_path / 'evidence'
    export_historical_versions(audit, [source], folder)
    return folder, folder / 'versions' / '00001' / (digest + '.bin')


def test_evidence_self_consistency(tmp_path):
    folder, _ = _evidence(tmp_path)
    result = verify_evidence(folder)
    assert result['verified_versions'] == 1
    assert result['independent_archive_comparison'] is False


def test_tampered_bytes_rejected(tmp_path):
    folder, blob = _evidence(tmp_path)
    blob.write_bytes(b'forged')
    with pytest.raises(ValueError, match='SHA 변조'):
        verify_evidence(folder)


def test_missing_version_rejected(tmp_path):
    folder, blob = _evidence(tmp_path)
    blob.unlink()
    with pytest.raises(ValueError, match='누락'):
        verify_evidence(folder)


def test_unlisted_file_rejected(tmp_path):
    folder, _ = _evidence(tmp_path)
    (folder / 'unlisted.txt').write_text('unexpected')
    with pytest.raises(ValueError, match='미등록'):
        verify_evidence(folder)


def test_forged_completion_flag_rejected(tmp_path):
    folder, _ = _evidence(tmp_path)
    manifest = folder / 'manifest.json'
    data = json.loads(manifest.read_text())
    data['all_versions_recovered'] = False
    manifest.write_text(json.dumps(data))
    with pytest.raises(ValueError, match='완료 표시'):
        verify_evidence(folder)


def test_symlinked_version_rejected(tmp_path):
    folder, blob = _evidence(tmp_path)
    replacement = tmp_path / 'replacement.bin'
    replacement.write_bytes(blob.read_bytes())
    blob.unlink()
    try:
        blob.symlink_to(replacement)
    except OSError:
        pytest.skip('심볼릭 링크 사용 불가')
    with pytest.raises(ValueError, match='링크'):
        verify_evidence(folder)
