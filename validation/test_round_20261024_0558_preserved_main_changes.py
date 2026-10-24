"""기존 main 보존 변경은 미병합으로 오분류하지 않는 회귀 검사."""
import hashlib

from validation.merge_preservation_policy import is_preserved_in_main
from validation.stage_three_way_merge import stage_merge


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def _case(tmp_path, main_files, test_files, old_files):
    main = tmp_path / 'main'
    test = tmp_path / 'test'
    main.mkdir()
    test.mkdir()
    for root, files in ((main, main_files), (test, test_files)):
        for name, data in files.items():
            (root / name).write_bytes(data)
    audit = {'coverage_confirmed': True, 'identical': [
        {'path': name, 'original_versions': [{'sha256': _sha(data)}]}
        for name, data in old_files.items()
    ], 'changed': [], 'missing': [], 'version_conflicts': []}
    return audit, main, test


def test_main_only_change_is_preserved_without_false_hold(tmp_path):
    audit, main, test = _case(tmp_path,
        {'core.py': b'old', 'main_feature.py': b'kept'},
        {'core.py': b'old'}, {'core.py': b'old'})
    result = stage_merge(audit, main, test, tmp_path / 'out')
    assert (tmp_path / 'out' / 'main_feature.py').read_bytes() == b'kept'
    assert 'main_feature.py' in result['already_preserved_main_paths']
    assert 'main_feature.py' not in result['held_for_manual_review']


def test_main_changed_from_original_is_preserved(tmp_path):
    audit, main, test = _case(tmp_path, {'core.py': b'main'},
                              {'core.py': b'old'}, {'core.py': b'old'})
    result = stage_merge(audit, main, test, tmp_path / 'out')
    assert (tmp_path / 'out' / 'core.py').read_bytes() == b'main'
    assert result['held_for_manual_review'] == []
    assert result['already_preserved_main_paths'] == ['core.py']


def test_same_change_in_both_needs_no_manual_merge(tmp_path):
    audit, main, test = _case(tmp_path, {'core.py': b'new'},
                              {'core.py': b'new'}, {'core.py': b'old'})
    result = stage_merge(audit, main, test, tmp_path / 'out')
    assert result['already_preserved_main_paths'] == ['core.py']
    assert result['held_for_manual_review'] == []


def test_main_preservation_does_not_hide_missing_historical_file(tmp_path):
    audit, main, test = _case(tmp_path, {}, {}, {'lost.py': b'old'})
    result = stage_merge(audit, main, test, tmp_path / 'out')
    assert result['held_for_manual_review'] == ['lost.py']


def test_historical_multiversion_still_held_when_same_in_both(tmp_path):
    audit, main, test = _case(tmp_path, {'core.py': b'new'},
                              {'core.py': b'new'}, {'core.py': b'old'})
    audit['identical'][0]['original_versions'].append({'sha256': _sha(b'older')})
    audit['version_conflicts'] = [{'path': 'core.py'}]
    result = stage_merge(audit, main, test, tmp_path / 'out')
    assert result['held_for_manual_review'] == ['core.py']
    assert result['already_preserved_main_paths'] == []


def test_preservation_policy_rejects_inconsistent_sha():
    try:
        is_preserved_in_main({'classification': 'same_in_both',
            'main_sha256': 'a', 'test_sha256': 'b', 'historical_sha256': []})
    except ValueError:
        pass
    else:
        raise AssertionError('불일치 감사 거부 누락')
