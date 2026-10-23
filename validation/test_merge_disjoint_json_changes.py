"""기존 AIWACK 원본 보존형 JSON 의미 병합 회귀."""
import hashlib
import json

from validation.merge_disjoint_json_changes import merge_disjoint_json
from validation.stage_three_way_merge import stage_merge


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _fixture(tmp_path, base, main, test):
    roots = [tmp_path / name for name in ('old', 'main', 'test')]
    for root, data in zip(roots, (base, main, test)):
        root.mkdir()
        (root / 'manifest.json').write_bytes(data)
    audit = {'coverage_confirmed': True, 'identical': [
        {'path': 'manifest.json', 'original_versions': [{'sha256': _sha(base)}]}],
        'changed': [], 'missing': [], 'version_conflicts': []}
    return audit, *roots


def test_independent_nested_keys_merge():
    base = b'{"a":{"x":1,"y":2},"b":0}'
    main = b'{"a":{"x":3,"y":2},"b":0}'
    test = b'{"a":{"x":1,"y":4},"b":0}'
    result = merge_disjoint_json(base, main, test)
    assert json.loads(result['content']) == {'a': {'x': 3, 'y': 4}, 'b': 0}
    assert result['base_sha256'] == _sha(base)


def test_independent_new_keys_merge():
    r = merge_disjoint_json(b'{"a":1}', b'{"a":1,"b":2}', b'{"a":1,"c":3}')
    assert json.loads(r['content']) == {'a': 1, 'b': 2, 'c': 3}


def test_disjoint_deletion_and_edit_merge():
    r = merge_disjoint_json(b'{"a":1,"b":2}', b'{"b":2}', b'{"a":1,"b":4}')
    assert json.loads(r['content']) == {'b': 4}


def test_conflicting_key_values_held():
    assert merge_disjoint_json(b'{"a":1}', b'{"a":2}', b'{"a":3}') is None


def test_conflicting_delete_vs_modify_held():
    assert merge_disjoint_json(b'{"a":1}', b'{}', b'{"a":2}') is None


def test_list_edits_held():
    assert merge_disjoint_json(b'{"a":[1,2]}', b'{"a":[3,2]}', b'{"a":[1,4]}') is None


def test_duplicate_keys_rejected():
    assert merge_disjoint_json(b'{"a":1}', b'{"a":1,"a":2}', b'{"a":2}') is None


def test_nan_rejected():
    assert merge_disjoint_json(b'{"a":0}', b'{"a":NaN}', b'{"a":1}') is None


def test_boolean_vs_integer_not_equal():
    assert merge_disjoint_json(b'{"a":0}', b'{"a":true}', b'{"a":1}') is None


def test_non_json_and_large_input_rejected():
    assert merge_disjoint_json(b'{"a":0}', b'not json', b'{"a":1}') is None
    assert merge_disjoint_json(b'{"a":0}', b'x' * (2*1024*1024+1), b'{"a":1}') is None


def test_stage_merges_same_line_independent_keys(tmp_path):
    base = b'{"a":1,"b":2}\n'
    main = b'{"a":3,"b":2}\n'
    test = b'{"a":1,"b":4}\n'
    audit, old, left, right = _fixture(tmp_path, base, main, test)
    result = stage_merge(audit, left, right, tmp_path/'stage', old)
    assert json.loads((tmp_path/'stage'/'manifest.json').read_bytes()) == {'a':3,'b':4}
    assert result['merged_divergent_evidence']['manifest.json']['merge_kind'] == 'disjoint_json_keys'
    assert (left/'manifest.json').read_bytes() == main
    assert (right/'manifest.json').read_bytes() == test


def test_stage_conflicting_json_keeps_main_and_holds(tmp_path):
    audit, old, left, right = _fixture(tmp_path, b'{"a":1}', b'{"a":2}', b'{"a":3}')
    result = stage_merge(audit, left, right, tmp_path/'stage', old)
    assert (tmp_path/'stage'/'manifest.json').read_bytes() == b'{"a":2}'
    assert result['held_for_manual_review'] == ['manifest.json']
