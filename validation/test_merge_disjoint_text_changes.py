"""실제 과거 원본 SHA와 비중첩 변경 병합 회귀."""
import hashlib
import pytest
from validation.merge_disjoint_text_changes import merge_disjoint_text
from validation.stage_three_way_merge import stage_merge


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _fixture(tmp_path, base, main, test):
    roots = [tmp_path / name for name in ('old', 'main', 'test')]
    for root, data in zip(roots, (base, main, test)):
        root.mkdir()
        (root / 'core.py').write_bytes(data)
    audit = {'coverage_confirmed': True, 'identical': [
        {'path': 'core.py', 'original_versions': [{'sha256': _sha(base)}]}],
        'changed': [], 'missing': [], 'version_conflicts': []}
    return audit, *roots


def test_disjoint_edits_preserve_both_sides(tmp_path):
    base = b'a\nb\nc\nd\n'
    main = b'A\nb\nc\nd\n'
    test = b'a\nb\nc\nD\n'
    audit, old, left, right = _fixture(tmp_path, base, main, test)
    result = stage_merge(audit, left, right, tmp_path / 'stage', old)
    assert (tmp_path / 'stage' / 'core.py').read_bytes() == b'A\nb\nc\nD\n'
    assert (left / 'core.py').read_bytes() == main
    assert (right / 'core.py').read_bytes() == test
    assert result['merged_divergent_evidence']['core.py']['base_sha256'] == _sha(base)
    assert not result['held_for_manual_review']


def test_overlapping_edits_held_not_overwritten(tmp_path):
    audit, old, left, right = _fixture(tmp_path, b'a\nb\nc\n', b'a\nB\nc\n', b'a\nBB\nc\n')
    result = stage_merge(audit, left, right, tmp_path / 'stage', old)
    assert result['held_for_manual_review'] == ['core.py']
    assert (tmp_path / 'stage' / 'core.py').read_bytes() == b'a\nB\nc\n'


def test_insertion_on_replacement_boundary_held():
    assert merge_disjoint_text(b'a\nb\n', b'A\nb\n', b'X\na\nb\n') is None


def test_binary_data_held():
    assert merge_disjoint_text(b'a\0b', b'A\0b', b'a\0B') is None


def test_mismatched_historical_bytes_never_merged(tmp_path):
    audit, old, left, right = _fixture(tmp_path, b'a\nb\nc\n', b'A\nb\nc\n', b'a\nb\nC\n')
    (old / 'core.py').write_bytes(b'forged')
    result = stage_merge(audit, left, right, tmp_path / 'stage', old)
    assert result['held_for_manual_review'] == ['core.py']


def test_multi_version_history_held(tmp_path):
    audit, old, left, right = _fixture(tmp_path, b'a\nb\nc\n', b'A\nb\nc\n', b'a\nb\nC\n')
    audit['identical'][0]['original_versions'].append({'sha256': _sha(b'other')})
    result = stage_merge(audit, left, right, tmp_path / 'stage', old)
    assert result['held_for_manual_review'] == ['core.py']


def test_unverified_coverage_blocks(tmp_path):
    audit, old, left, right = _fixture(tmp_path, b'a\nb\nc\n', b'A\nb\nc\n', b'a\nb\nC\n')
    audit['coverage_confirmed'] = False
    with pytest.raises(ValueError, match='감사'):
        stage_merge(audit, left, right, tmp_path / 'stage', old)


def test_no_historical_root_retains_conservative_behavior(tmp_path):
    audit, old, left, right = _fixture(tmp_path, b'a\nb\nc\n', b'A\nb\nc\n', b'a\nb\nC\n')
    result = stage_merge(audit, left, right, tmp_path / 'stage')
    assert result['held_for_manual_review'] == ['core.py']


def test_two_insertions_same_location_conflict():
    assert merge_disjoint_text(b'a\nb\n', b'a\nX\nb\n', b'a\nY\nb\n') is None
