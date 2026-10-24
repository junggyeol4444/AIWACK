"""기존 원본 보존형 실제 스테이징 병합 회귀."""
import hashlib
import pytest
from validation.stage_three_way_merge import stage_merge


def _sha(data): return hashlib.sha256(data).hexdigest()


def _setup(tmp_path, base=b'old', current=b'old', candidate=b'new'):
    main, test = tmp_path/'main', tmp_path/'test'
    main.mkdir(); test.mkdir()
    (main/'core.py').write_bytes(current)
    (test/'core.py').write_bytes(candidate)
    audit = {'coverage_confirmed': True, 'identical': [
        {'path':'core.py','original_versions':[{'sha256':_sha(base)}]}],
        'changed':[], 'missing':[], 'version_conflicts':[]}
    return audit, main, test, tmp_path/'staging'


def test_actual_merge_test_change_only(tmp_path):
    audit, main, test, staging = _setup(tmp_path)
    result = stage_merge(audit, main, test, staging)
    assert (staging/'core.py').read_bytes() == b'new'
    assert (main/'core.py').read_bytes() == b'old'
    assert result['merged_paths'] == ['core.py']
    assert not result['held_for_manual_review']
    assert not result['github_main_updated']


def test_main_divergent_change_is_preserved_and_held(tmp_path):
    audit, main, test, staging = _setup(tmp_path, current=b'local', candidate=b'new')
    result = stage_merge(audit, main, test, staging)
    assert (staging/'core.py').read_bytes() == b'local'
    assert result['held_for_manual_review'] == ['core.py']


def test_new_file_from_test_is_merged_without_deleting_main(tmp_path):
    audit, main, test, staging = _setup(tmp_path)
    (test/'new.py').write_bytes(b'new file')
    (main/'untouched.txt').write_bytes(b'original')
    result = stage_merge(audit, main, test, staging)
    assert sorted(result['merged_paths']) == ['core.py','new.py']
    assert (staging/'new.py').read_bytes() == b'new file'
    assert (staging/'untouched.txt').read_bytes() == b'original'


def test_conflicted_history_blocks_any_output(tmp_path):
    audit, main, test, staging = _setup(tmp_path)
    audit['version_conflicts'] = [{'path':'core.py'}]
    with pytest.raises(ValueError, match='충돌'):
        stage_merge(audit, main, test, staging)
    assert not staging.exists()


def test_never_overwrite_existing_staging(tmp_path):
    audit, main, test, staging = _setup(tmp_path)
    staging.mkdir(); (staging/'saved.txt').write_text('keep')
    with pytest.raises(FileExistsError): stage_merge(audit, main, test, staging)
    assert (staging/'saved.txt').read_text() == 'keep'


def test_historical_deletion_not_silently_restored(tmp_path):
    audit, main, test, staging = _setup(tmp_path)
    (main/'core.py').unlink()
    result = stage_merge(audit, main, test, staging)
    assert not (staging/'core.py').exists()
    assert result['held_for_manual_review'] == ['core.py']


def test_symlink_in_test_blocks(tmp_path):
    audit, main, test, staging = _setup(tmp_path)
    outside = tmp_path/'outside.txt'; outside.write_text('keep')
    try: (test/'bad.txt').symlink_to(outside)
    except OSError: pytest.skip('symlink unavailable')
    with pytest.raises(ValueError, match='충돌'):
        stage_merge(audit, main, test, staging)
    assert not staging.exists()
