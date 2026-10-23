"""AIWACK 누적 원본 누락 파일의 안전한 복원·병합 회귀."""
import hashlib

from validation.stage_three_way_merge import stage_merge


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def _case(tmp_path, main_files=None, test_files=None, old_files=None):
    roots = [tmp_path / name for name in ('main', 'test', 'historical')]
    for root, files in zip(roots, (main_files or {}, test_files or {}, old_files or {})):
        root.mkdir()
        for name, raw in files.items():
            target = root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(raw)
    audit = {
        'coverage_confirmed': True,
        'identical': [{'path': name, 'original_versions': [{'sha256': _sha(raw)}]}
                      for name, raw in (old_files or {}).items()],
        'changed': [], 'missing': [], 'version_conflicts': [],
    }
    return audit, *roots


def test_missing_in_both_recovers_only_verified_historical_bytes(tmp_path):
    old = b'original source\n'
    audit, main, test, history = _case(tmp_path, old_files={'legacy.py': old})
    result = stage_merge(audit, main, test, tmp_path / 'out', history)
    assert (tmp_path / 'out' / 'legacy.py').read_bytes() == old
    assert result['restored_historical_paths'] == ['legacy.py']
    assert result['restored_historical_evidence']['legacy.py']['sha256'] == _sha(old)
    assert result['held_for_manual_review'] == []
    assert not (main / 'legacy.py').exists()
    assert not (test / 'legacy.py').exists()


def test_test_only_unchanged_historical_file_can_be_restored(tmp_path):
    old = b'kept history\n'
    audit, main, test, history = _case(
        tmp_path, test_files={'legacy.py': old}, old_files={'legacy.py': old})
    result = stage_merge(audit, main, test, tmp_path / 'out', history)
    assert result['restored_historical_paths'] == ['legacy.py']
    assert (tmp_path / 'out' / 'legacy.py').read_bytes() == old


def test_test_only_changed_from_historical_is_held(tmp_path):
    old = b'original\n'
    changed = b'test modification\n'
    audit, main, test, history = _case(
        tmp_path, test_files={'legacy.py': changed}, old_files={'legacy.py': old})
    result = stage_merge(audit, main, test, tmp_path / 'out', history)
    assert result['restored_historical_paths'] == []
    assert result['held_for_manual_review'] == ['legacy.py']
    assert not (tmp_path / 'out' / 'legacy.py').exists()


def test_historical_sha_mismatch_is_held_without_writing(tmp_path):
    old = b'original\n'
    audit, main, test, history = _case(tmp_path, old_files={'legacy.py': old})
    (history / 'legacy.py').write_bytes(b'tampered\n')
    result = stage_merge(audit, main, test, tmp_path / 'out', history)
    assert result['held_for_manual_review'] == ['legacy.py']
    assert result['restored_historical_paths'] == []
    assert not (tmp_path / 'out' / 'legacy.py').exists()


def test_missing_without_historical_root_stays_held(tmp_path):
    audit, main, test, history = _case(
        tmp_path, old_files={'legacy.py': b'original\n'})
    result = stage_merge(audit, main, test, tmp_path / 'out')
    assert result['held_for_manual_review'] == ['legacy.py']
    assert result['restored_historical_paths'] == []


def test_multiversion_historical_conflict_never_auto_restored(tmp_path):
    old = b'first version\n'
    audit, main, test, history = _case(tmp_path, old_files={'legacy.py': old})
    audit['identical'][0]['original_versions'].append({'sha256': _sha(b'second version\n')})
    audit['version_conflicts'] = [{'path': 'legacy.py'}]
    result = stage_merge(audit, main, test, tmp_path / 'out', history)
    assert result['held_for_manual_review'] == ['legacy.py']
    assert result['historical_conflict_paths_held'] == ['legacy.py']
    assert result['restored_historical_paths'] == []


def test_new_test_only_file_remains_eligible_with_historical_root(tmp_path):
    audit, main, test, history = _case(
        tmp_path, test_files={'new.py': b'new source\n'},
        old_files={'legacy.py': b'original\n'})
    result = stage_merge(audit, main, test, tmp_path / 'out', history)
    assert 'new.py' in result['merged_paths']
    assert (tmp_path / 'out' / 'new.py').read_bytes() == b'new source\n'
    assert 'legacy.py' in result['restored_historical_paths']
