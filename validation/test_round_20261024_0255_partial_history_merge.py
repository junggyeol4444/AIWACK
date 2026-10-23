"""과거 다중버전 충돌을 보류하면서 독립 소스만 스테이징하는 실제 병합 회귀."""
import hashlib
import pytest
from validation.stage_three_way_merge import stage_merge
from validation.three_way_merge_review import review_three_way

def sha(value):
    return hashlib.sha256(value).hexdigest()

def fixture(tmp_path):
    main, test = tmp_path/'main', tmp_path/'test'
    main.mkdir(); test.mkdir()
    (main/'core.py').write_bytes(b'base')
    (test/'core.py').write_bytes(b'candidate')
    (main/'history.py').write_bytes(b'old')
    (test/'history.py').write_bytes(b'other')
    audit = {'coverage_confirmed': True,
             'identical': [{'path': 'core.py', 'original_versions': [{'sha256': sha(b'base')}]},
                           {'path': 'history.py', 'original_versions': [
                               {'sha256': sha(b'old')}, {'sha256': sha(b'other')}]}],
             'changed': [], 'missing': [],
             'version_conflicts': [{'path': 'history.py',
                                    'distinct_sha256': sorted([sha(b'old'), sha(b'other')])}]}
    return audit, main, test, tmp_path/'staging'

def test_independent_change_staged_conflicted_history_held(tmp_path):
    audit, main, test, dest = fixture(tmp_path)
    result = stage_merge(audit, main, test, dest)
    assert result['merged_paths'] == ['core.py']
    assert result['historical_conflict_paths_held'] == ['history.py']
    assert result['held_for_manual_review'] == ['history.py']
    assert (dest/'core.py').read_bytes() == b'candidate'
    assert (dest/'history.py').read_bytes() == b'old'
    assert (main/'history.py').read_bytes() == b'old'

def test_history_same_in_both_still_reviewed(tmp_path):
    audit, main, test, dest = fixture(tmp_path)
    (test/'history.py').write_bytes(b'old')
    review = review_three_way(audit, main, test)
    assert review['historical_conflict_paths'] == ['history.py']
    assert any(x['path']=='history.py' and x['historical_conflict'] for x in review['review_items'])
    assert not review['ready_for_main']
    result = stage_merge(audit, main, test, dest)
    assert result['held_for_manual_review'] == ['history.py']

def test_missing_conflict_provenance_fails_closed(tmp_path):
    audit, main, test, dest = fixture(tmp_path)
    audit['version_conflicts'] = []
    with pytest.raises(ValueError, match='다중버전'):
        stage_merge(audit, main, test, dest)
    assert not dest.exists()

def test_conflict_sha_mismatch_fails_closed(tmp_path):
    audit, main, test, dest = fixture(tmp_path)
    audit['version_conflicts'][0]['distinct_sha256'] = [sha(b'forged')]
    with pytest.raises(ValueError, match='SHA'):
        stage_merge(audit, main, test, dest)
    assert not dest.exists()

def test_git_metadata_not_copied(tmp_path):
    audit, main, test, dest = fixture(tmp_path)
    (main/'.git').mkdir()
    (main/'.git'/'config').write_text('private')
    stage_merge(audit, main, test, dest)
    assert not (dest/'.git').exists()

def test_symlinked_destination_inside_source_rejected(tmp_path):
    audit, main, test, dest = fixture(tmp_path)
    link = tmp_path/'alias'
    try:
        link.symlink_to(main, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip('symlink unavailable')
    with pytest.raises(ValueError, match='원본'):
        stage_merge(audit, main, test, link/'output')
    assert not (main/'output').exists()
