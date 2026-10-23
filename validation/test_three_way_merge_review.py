"""실제 브랜치 병합을 하지 않는 기존 AIWACK SHA 기반 분류 회귀."""
import hashlib
import pytest
from validation.three_way_merge_review import review_three_way


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _audit(name='desktop/core.py', raw=b'old'):
    return {'coverage_confirmed': True, 'requires_manual_merge_review': False,
            'version_conflicts': [], 'identical': [{
                'path': name, 'original_versions': [{'sha256': _sha(raw)}]}],
            'changed': [], 'missing': []}


def _trees(tmp_path, main=b'old', test=b'old'):
    left, right = tmp_path/'main', tmp_path/'test'
    for root, data in ((left, main), (right, test)):
        (root/'desktop').mkdir(parents=True)
        (root/'desktop'/'core.py').write_bytes(data)
    return left, right


def test_identical_original_both_branches_ready(tmp_path):
    a, b = _trees(tmp_path)
    result = review_three_way(_audit(), a, b)
    assert result['ready_for_main'] and not result['review_items']
    assert not result['automatic_merge_performed']


def test_test_only_change_preserved_for_review(tmp_path):
    a, b = _trees(tmp_path, b'old', b'new')
    result = review_three_way(_audit(), a, b)
    row = result['review_items'][0]
    assert row['classification'] == 'test_changed_from_original'
    assert row['main_sha256'] == _sha(b'old')
    assert row['test_sha256'] == _sha(b'new')
    assert not result['ready_for_main']
    assert (b/'desktop'/'core.py').read_bytes() == b'new'


def test_main_only_change_never_overwritten(tmp_path):
    a, b = _trees(tmp_path, b'main-change', b'old')
    result = review_three_way(_audit(), a, b)
    assert result['review_items'][0]['classification'] == 'main_changed_from_original'
    assert (a/'desktop'/'core.py').read_bytes() == b'main-change'


def test_divergent_changes_flagged(tmp_path):
    a, b = _trees(tmp_path, b'main-change', b'test-change')
    result = review_three_way(_audit(), a, b)
    assert result['review_items'][0]['classification'] == 'divergent_change'
    assert not result['ready_for_main']


def test_windows_alias_collision_blocks(tmp_path):
    a, b = _trees(tmp_path)
    (b/'desktop'/'CORE.py').write_bytes(b'alias')
    result = review_three_way(_audit(), a, b)
    assert result['unsafe'] and not result['ready_for_main']


def test_symlink_blocks_without_following(tmp_path):
    a, b = _trees(tmp_path)
    target = tmp_path/'external'; target.write_bytes(b'outside')
    try:
        (b/'link.py').symlink_to(target)
    except (OSError, NotImplementedError):
        pytest.skip('symlink unavailable')
    result = review_three_way(_audit(), a, b)
    assert any(x['reason'] == 'symlink' for x in result['unsafe'])
    assert target.read_bytes() == b'outside'


def test_unverified_historical_coverage_blocks(tmp_path):
    a, b = _trees(tmp_path)
    audit = _audit(); audit['coverage_confirmed'] = False
    assert not review_three_way(audit, a, b)['ready_for_main']


def test_missing_historical_path_blocks(tmp_path):
    a, b = _trees(tmp_path)
    audit = _audit('desktop/missing.py')
    result = review_three_way(audit, a, b)
    assert result['review_items'][0]['classification'] == 'missing_in_both'
    assert not result['ready_for_main']


def test_invalid_sha_refused(tmp_path):
    a, b = _trees(tmp_path)
    audit = _audit(); audit['identical'][0]['original_versions'][0]['sha256'] = 'broken'
    with pytest.raises(ValueError, match='SHA256'):
        review_three_way(audit, a, b)
