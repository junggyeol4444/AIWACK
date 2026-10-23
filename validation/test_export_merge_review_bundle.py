"""AIWACK 기존 원본을 건드리지 않는 3-way 검토 묶음 회귀."""
import hashlib
import json
import pytest
from validation.export_merge_review_bundle import export_review_bundle


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _fixture(tmp_path):
    roots = [tmp_path / name for name in ('history', 'main', 'test')]
    for root, raw in zip(roots, (b'old\n', b'MAIN\n', b'TEST\n')):
        root.mkdir()
        (root / 'core.py').write_bytes(raw)
    audit = {'coverage_confirmed': True, 'identical': [
        {'path': 'core.py', 'original_versions': [{'sha256': _sha(b'old\n')}]}],
        'changed': [], 'missing': [], 'version_conflicts': []}
    return audit, *roots


def test_export_preserves_three_sources(tmp_path):
    audit, history, main, test = _fixture(tmp_path)
    target = tmp_path / 'review'
    result = export_review_bundle(audit, main, test, target, history)
    assert result['review_cases'] == 1
    assert (target / 'cases/00001/main.bin').read_bytes() == b'MAIN\n'
    assert (target / 'cases/00001/test.bin').read_bytes() == b'TEST\n'
    assert (target / 'cases/00001/historical.bin').read_bytes() == b'old\n'
    manifest = json.loads((target / 'manifest.json').read_text(encoding='utf-8'))
    assert manifest['automatic_merge'] is False
    assert manifest['cases'][0]['main_sha256'] == _sha(b'MAIN\n')
    assert (main / 'core.py').read_bytes() == b'MAIN\n'
    assert (test / 'core.py').read_bytes() == b'TEST\n'


def test_multi_history_kept_unresolved(tmp_path):
    audit, history, main, test = _fixture(tmp_path)
    audit['identical'][0]['original_versions'].append({'sha256': _sha(b'older\n')})
    audit['version_conflicts'] = [{'path': 'core.py'}]
    export_review_bundle(audit, main, test, tmp_path / 'review', history)
    case = tmp_path / 'review/cases/00001'
    assert not (case / 'historical.bin').exists()
    manifest = json.loads((tmp_path / 'review/manifest.json').read_text())
    assert manifest['historical_version_conflicts'] == 1
    assert '다중버전' in manifest['cases'][0]['historical_export']


def test_existing_destination_is_never_overwritten(tmp_path):
    audit, history, main, test = _fixture(tmp_path)
    target = tmp_path / 'review'; target.mkdir()
    (target / 'keep.txt').write_text('원본')
    with pytest.raises(ValueError, match='덮어쓸'):
        export_review_bundle(audit, main, test, target, history)
    assert (target / 'keep.txt').read_text() == '원본'


def test_destination_inside_original_is_blocked(tmp_path):
    audit, history, main, test = _fixture(tmp_path)
    with pytest.raises(ValueError, match='덮어쓸'):
        export_review_bundle(audit, main, test, main / 'review', history)


def test_mismatched_historical_content_not_exported(tmp_path):
    audit, history, main, test = _fixture(tmp_path)
    (history / 'core.py').write_bytes(b'forged\n')
    export_review_bundle(audit, main, test, tmp_path / 'review', history)
    assert not (tmp_path / 'review/cases/00001/historical.bin').exists()


def test_unsafe_test_path_blocks_bundle(tmp_path):
    audit, history, main, test = _fixture(tmp_path)
    (test / 'CON.txt').write_bytes(b'unsafe')
    with pytest.raises(ValueError, match='경로'):
        export_review_bundle(audit, main, test, tmp_path / 'review', history)
    assert not (tmp_path / 'review').exists()


def test_incomplete_audit_blocks_bundle(tmp_path):
    audit, history, main, test = _fixture(tmp_path)
    audit['coverage_confirmed'] = False
    with pytest.raises(ValueError, match='감사'):
        export_review_bundle(audit, main, test, tmp_path / 'review', history)


def test_symlinked_destination_parent_cannot_enter_main(tmp_path):
    audit, history, main, test = _fixture(tmp_path)
    link = tmp_path / 'alias'
    try:
        link.symlink_to(main, target_is_directory=True)
    except OSError:
        pytest.skip('symlink unavailable')
    with pytest.raises(ValueError, match='덮어쓸'):
        export_review_bundle(audit, main, test, link / 'review', history)
    assert not (main / 'review').exists()


def test_changed_main_during_read_blocks_publish(tmp_path, monkeypatch):
    from validation import export_merge_review_bundle as module
    audit, history, main, test = _fixture(tmp_path)
    original = module._verified_read
    def change_after_read(root, relative, expected):
        result = original(root, relative, expected)
        if root == main:
            (main / 'core.py').write_bytes(b'changed again\n')
        return result
    monkeypatch.setattr(module, '_verified_read', change_after_read)
    with pytest.raises(ValueError, match='원본이 변경'):
        export_review_bundle(audit, main, test, tmp_path / 'review', history)
    assert not (tmp_path / 'review').exists()
