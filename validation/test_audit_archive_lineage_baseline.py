"""원본 매니페스트 1099개 경로/해시 확인: 모의 ZIP, 실 Windows GGUF 아님."""
import hashlib
import json
import zipfile
import pytest
from validation.audit_archive_lineage import audit_archives


def _digest(raw):
    return hashlib.sha256(raw).hexdigest()


def _fixture(tmp_path, manifest, archive_rows):
    root = tmp_path / 'repo'
    root.mkdir()
    manifest_path = tmp_path / 'baseline.json'
    manifest_path.write_text(json.dumps({'source_sha256': manifest}), encoding='utf-8')
    archive_path = tmp_path / 'history.zip'
    with zipfile.ZipFile(archive_path, 'w') as out:
        for path, raw in archive_rows:
            out.writestr(path, raw)
            target = root / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(raw)
    return root, manifest_path, archive_path


def test_baseline_exact_archive_sha(tmp_path):
    root, manifest, archive = _fixture(tmp_path, {'docs/a.md': _digest(b'a')},
                                       [('docs/a.md', b'a')])
    result = audit_archives([archive], root, baseline_manifest=manifest)
    assert result['coverage_confirmed'] and result['baseline_exact_provenance']
    assert not result['requires_manual_merge_review']


def test_equal_count_but_wrong_path_is_not_coverage(tmp_path):
    root, manifest, archive = _fixture(tmp_path, {'docs/old.md': _digest(b'a')},
                                       [('docs/new.md', b'a')])
    result = audit_archives([archive], root, baseline_manifest=manifest)
    assert not result['coverage_confirmed']
    assert result['baseline_paths_unseen'][0]['path'] == 'docs/old.md'


def test_equal_path_but_wrong_archive_bytes_is_not_provenance(tmp_path):
    root, manifest, archive = _fixture(tmp_path, {'docs/a.md': _digest(b'old')},
                                       [('docs/a.md', b'new')])
    result = audit_archives([archive], root, baseline_manifest=manifest)
    assert not result['coverage_confirmed']
    assert len(result['baseline_paths_sha_mismatch']) == 1


def test_explicit_expected_count_conflict_rejected(tmp_path):
    root, manifest, archive = _fixture(tmp_path, {'docs/a.md': _digest(b'a')},
                                       [('docs/a.md', b'a')])
    with pytest.raises(ValueError, match='파일 수'):
        audit_archives([archive], root, expected_paths=1099, baseline_manifest=manifest)


def test_manifest_windows_alias_collision_rejected(tmp_path):
    root, manifest, archive = _fixture(tmp_path, {'docs/A.md': _digest(b'a'),
                                                   'docs/a.md': _digest(b'b')},
                                       [('docs/A.md', b'a')])
    with pytest.raises(ValueError, match='충돌'):
        audit_archives([archive], root, baseline_manifest=manifest)
