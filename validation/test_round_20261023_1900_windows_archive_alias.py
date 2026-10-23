"""Windows 10/11 alias safety for original ZIPs; fixture tests only."""
import zipfile
import pytest

from validation.audit_archive_lineage import audit_archives
from validation.restore_original_source_history import reconcile


def _zip(path, rows):
    with zipfile.ZipFile(path, 'w') as archive:
        for name, body in rows:
            archive.writestr(name, body)
    return path


def test_restore_refuses_case_alias_before_writing(tmp_path):
    root = tmp_path / 'repo'
    (root / 'docs').mkdir(parents=True)
    (root / 'docs' / 'Report.md').write_bytes(b'old')
    archive = _zip(tmp_path / 'old.zip', [
        ('docs/report.md', b'new'), ('docs/extra.md', b'extra')])
    with pytest.raises(ValueError, match='Windows 경로 충돌'):
        reconcile(archive, root, restore_missing=True)
    assert (root / 'docs' / 'Report.md').read_bytes() == b'old'
    assert not (root / 'docs' / 'report.md').exists()
    assert not (root / 'docs' / 'extra.md').exists()


def test_restore_refuses_parent_directory_alias(tmp_path):
    root = tmp_path / 'repo'
    (root / 'Docs').mkdir(parents=True)
    archive = _zip(tmp_path / 'old.zip', [('docs/new.md', b'new')])
    with pytest.raises(ValueError, match='Windows 경로 충돌'):
        reconcile(archive, root, restore_missing=True)
    assert not (root / 'docs').exists()


def test_archive_audit_reports_alias_as_unsafe(tmp_path):
    root = tmp_path / 'repo'
    (root / 'docs').mkdir(parents=True)
    (root / 'docs' / 'Report.md').write_bytes(b'old')
    archive = _zip(tmp_path / 'old.zip', [('docs/report.md', b'old')])
    report = audit_archives([archive], root, expected_paths=1)
    assert report['requires_manual_merge_review']
    assert not report['identical']
    assert any(row['reason'] == 'repository_windows_alias'
               for row in report['unsafe'])
