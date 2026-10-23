"""여러 회차 원본 ZIP SHA 전수 대조 회귀. 실제 Windows EXE 검증 아님."""
import zipfile
import pytest
from validation.audit_archive_lineage import audit_archives


def _zip(path, entries):
    with zipfile.ZipFile(path, 'w') as archive:
        for name, data in entries:
            archive.writestr(name, data)
    return path


def test_multi_archive_exact_preservation(tmp_path):
    repo = tmp_path / 'repo'; (repo/'docs').mkdir(parents=True)
    (repo/'docs'/'기록.md').write_bytes(b'original')
    first = _zip(tmp_path/'first.zip', [('docs/기록.md', b'original')])
    second = _zip(tmp_path/'second.zip', [('docs/기록.md', b'original')])
    result = audit_archives([first, second], repo, expected_paths=1)
    assert result['coverage_confirmed'] and not result['requires_manual_merge_review']
    assert len(result['identical']) == len(result['repeated_identical']) == 1


def test_changed_versions_stay_visible_without_overwrite(tmp_path):
    repo = tmp_path / 'repo'; (repo/'docs').mkdir(parents=True)
    original = repo/'docs'/'기록.md'; original.write_bytes(b'new')
    first = _zip(tmp_path/'first.zip', [('docs/기록.md', b'old')])
    second = _zip(tmp_path/'second.zip', [('docs/기록.md', b'new')])
    result = audit_archives([first, second], repo, expected_paths=1)
    assert len(result['version_conflicts']) == 1
    assert len(result['identical']) == 1 and result['identical'][0]['matched_archives'] == [str(second)]
    assert result['requires_manual_merge_review']
    assert original.read_bytes() == b'new'


def test_missing_and_expected_count_not_reported_as_complete(tmp_path):
    repo = tmp_path/'repo'; repo.mkdir()
    archive = _zip(tmp_path/'old.zip', [('docs/missing.md', b'old')])
    result = audit_archives([archive], repo, expected_paths=1099)
    assert not result['coverage_confirmed'] and len(result['missing']) == 1
    assert not (repo/'docs').exists()


def test_windows_collision_across_archives_rejected(tmp_path):
    repo = tmp_path/'repo'; repo.mkdir()
    first = _zip(tmp_path/'a.zip', [('docs/Name.md', b'a')])
    second = _zip(tmp_path/'b.zip', [('docs/name.md', b'b')])
    with pytest.raises(ValueError, match='Windows 경로 충돌'):
        audit_archives([first, second], repo)


def test_corrupted_archive_rejected(tmp_path):
    repo = tmp_path/'repo'; repo.mkdir()
    archive = _zip(tmp_path/'a.zip', [('docs/a.md', b'CORRUPT_PAYLOAD')])
    raw = archive.read_bytes(); pos = raw.find(b'CORRUPT_PAYLOAD')
    assert pos > 0
    archive.write_bytes(raw[:pos]+b'X'+raw[pos+1:])
    with pytest.raises(zipfile.BadZipFile):
        audit_archives([archive], repo)


def test_symlink_target_rejected(tmp_path):
    repo = tmp_path/'repo'; repo.mkdir()
    outside = tmp_path/'outside'; outside.mkdir()
    try:
        (repo/'docs').symlink_to(outside, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip('링크 생성 불가')
    archive = _zip(tmp_path/'a.zip', [('docs/item.md', b'no')])
    result = audit_archives([archive], repo)
    assert len(result['unsafe']) == 1 and not (outside/'item.md').exists()
