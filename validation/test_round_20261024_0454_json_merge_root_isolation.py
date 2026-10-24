"""기존 AIWACK 누적 병합: JSON 형식 검증 우회·원본 경로 중첩 회귀."""
import hashlib
import json

import pytest

from validation.stage_three_way_merge import stage_merge


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def _prepare(tmp_path, base, main_data, test_data):
    old, main, test = (tmp_path / name for name in ('historical', 'main', 'test'))
    for root, data in ((old, base), (main, main_data), (test, test_data)):
        root.mkdir()
        (root / 'campaign.json').write_bytes(data)
    audit = {
        'coverage_confirmed': True,
        'identical': [{
            'path': 'campaign.json',
            'original_versions': [{'sha256': _sha(base)}],
        }],
        'changed': [], 'missing': [], 'version_conflicts': [],
    }
    return audit, old, main, test


@pytest.mark.parametrize('invalid_main', [
    b'{\n"a": NaN,\n"b": 2\n}\n',
    b'{\n"a": 3,\n"a": 4,\n"b": 2\n}\n',
    b'{\n"a": 3,\n"b": 2,\n}\n',
])
def test_invalid_main_json_cannot_bypass_strict_parser(tmp_path, invalid_main):
    base = b'{\n"a": 1,\n"b": 2\n}\n'
    test = b'{\n"a": 1,\n"b": 4\n}\n'
    audit, old, main, candidate = _prepare(tmp_path, base, invalid_main, test)
    result = stage_merge(audit, main, candidate, tmp_path / 'staged', old)
    assert result['merged_paths'] == []
    assert result['held_for_manual_review'] == ['campaign.json']
    assert (tmp_path / 'staged' / 'campaign.json').read_bytes() == invalid_main
    assert (main / 'campaign.json').read_bytes() == invalid_main
    assert (candidate / 'campaign.json').read_bytes() == test


def test_valid_json_independent_keys_are_merged(tmp_path):
    base = b'{\n"a": 1,\n"b": 2\n}\n'
    main_data = b'{\n"a": 3,\n"b": 2\n}\n'
    test_data = b'{\n"a": 1,\n"b": 4\n}\n'
    audit, old, main, candidate = _prepare(tmp_path, base, main_data, test_data)
    result = stage_merge(audit, main, candidate, tmp_path / 'staged', old)
    assert json.loads((tmp_path / 'staged' / 'campaign.json').read_text()) == {'a': 3, 'b': 4}
    assert result['merged_divergent_evidence']['campaign.json']['merge_kind'] == 'disjoint_json_keys'


def test_test_root_inside_main_is_rejected_before_writing(tmp_path):
    main = tmp_path / 'main'
    main.mkdir()
    test = main / 'test'
    test.mkdir()
    target = tmp_path / 'staged'
    with pytest.raises(ValueError, match='중첩'):
        stage_merge({}, main, test, target)
    assert not target.exists()


def test_historical_root_inside_test_is_rejected_before_writing(tmp_path):
    main = tmp_path / 'main'
    test = tmp_path / 'test'
    main.mkdir()
    test.mkdir()
    historical = test / 'historical'
    historical.mkdir()
    target = tmp_path / 'staged'
    with pytest.raises(ValueError, match='중첩'):
        stage_merge({}, main, test, target, historical)
    assert not target.exists()
