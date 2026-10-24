"""기존 1~21회차 원본 ZIP과 현재 체크아웃 독립 대조 개발 회귀.

실제 원본 ZIP을 이 테스트에서 재현하지 않는다. 작은 합성 ZIP으로
경로·SHA·다중 역사 버전·원본 무변경 계약만 검사한다.
"""
import hashlib
import json
import zipfile

import pytest

from validation.export_historical_version_evidence import export_historical_versions
from validation.verify_historical_against_archives import (
    compare_checkout_with_archives, main,
)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def fixture(tmp_path, *, versions=(b'old',), extra=False):
    archives = []
    for number, raw in enumerate(versions):
        path = tmp_path / f'original-{number}.zip'
        with zipfile.ZipFile(path, 'w') as bundle:
            bundle.writestr('docs/a.txt', raw)
            if extra and number == 0:
                bundle.writestr('docs/untracked.txt', b'additional')
        archives.append(path)
    hashes = sorted({sha(v) for v in versions})
    audit = {
        'coverage_confirmed': True,
        'distinct_original_paths': 1,
        'identical': [{'path': 'docs/a.txt',
                       'original_versions': [{'sha256': h} for h in hashes]}],
        'changed': [], 'missing': [],
        'version_conflicts': ([{'path': 'docs/a.txt', 'distinct_sha256': hashes}]
                              if len(hashes) > 1 else []),
    }
    evidence = tmp_path / 'evidence'
    export_historical_versions(audit, archives, evidence)
    checkout = tmp_path / 'checkout'
    checkout.mkdir()
    return archives, evidence, checkout


def test_identical_checkout_has_no_review(tmp_path):
    archives, evidence, checkout = fixture(tmp_path)
    (checkout / 'docs').mkdir()
    (checkout / 'docs/a.txt').write_bytes(b'old')
    original = sha(archives[0].read_bytes())
    result = compare_checkout_with_archives(evidence, checkout)
    assert result['status_counts']['unchanged'] == 1
    assert result['historical_paths_compared'] == 1
    assert result['manual_review_required'] is False
    assert result['full_1099_originals_compared'] is False
    assert result['github_main_updated'] is False
    assert sha(archives[0].read_bytes()) == original


def test_changed_checkout_requires_review_without_overwrite(tmp_path):
    _, evidence, checkout = fixture(tmp_path)
    (checkout / 'docs').mkdir()
    path = checkout / 'docs/a.txt'
    path.write_bytes(b'changed')
    result = compare_checkout_with_archives(evidence, checkout)
    assert result['status_counts']['changed'] == 1
    assert result['path_results'][0]['checkout_sha256'] == sha(b'changed')
    assert result['manual_review_required'] is True
    assert path.read_bytes() == b'changed'


def test_missing_checkout_is_not_reported_as_merged(tmp_path):
    _, evidence, checkout = fixture(tmp_path)
    result = compare_checkout_with_archives(evidence, checkout)
    assert result['status_counts']['missing'] == 1
    assert result['manual_review_required'] is True


def test_multiversion_is_never_auto_selected(tmp_path):
    _, evidence, checkout = fixture(tmp_path, versions=(b'old', b'new'))
    (checkout / 'docs').mkdir()
    (checkout / 'docs/a.txt').write_bytes(b'new')
    result = compare_checkout_with_archives(evidence, checkout)
    assert result['status_counts']['historical_conflict_matching'] == 1
    assert result['path_results'][0]['manual_review_required'] is True
    assert result['manual_review_required'] is True


def test_untracked_archive_entry_prevents_false_complete(tmp_path):
    _, evidence, checkout = fixture(tmp_path, extra=True)
    (checkout / 'docs').mkdir()
    (checkout / 'docs/a.txt').write_bytes(b'old')
    result = compare_checkout_with_archives(evidence, checkout)
    assert result['unmatched_archive_entries_total'] == 1
    assert result['manual_review_required'] is True
    assert result['full_1099_originals_compared'] is False


def test_checkout_extra_file_is_reported_but_not_removed(tmp_path):
    _, evidence, checkout = fixture(tmp_path)
    (checkout / 'docs').mkdir()
    (checkout / 'docs/a.txt').write_bytes(b'old')
    (checkout / 'new.txt').write_bytes(b'new')
    result = compare_checkout_with_archives(evidence, checkout)
    assert result['checkout_only_paths'] == ['new.txt']
    assert (checkout / 'new.txt').read_bytes() == b'new'


def test_symlink_in_checkout_rejected(tmp_path):
    _, evidence, checkout = fixture(tmp_path)
    target = tmp_path / 'outside.txt'
    target.write_bytes(b'outside')
    try:
        (checkout / 'linked.txt').symlink_to(target)
    except OSError:
        pytest.skip('symbolic link unavailable')
    with pytest.raises(ValueError, match='안전검사'):
        compare_checkout_with_archives(evidence, checkout)


def test_cli_readonly_comparison_exit_code(tmp_path, capsys):
    _, evidence, checkout = fixture(tmp_path)
    (checkout / 'docs').mkdir()
    (checkout / 'docs/a.txt').write_bytes(b'changed')
    assert main([str(evidence), '--checkout-root', str(checkout)]) == 2
    result = json.loads(capsys.readouterr().out)
    assert result['status_counts']['changed'] == 1
    assert result['github_main_updated'] is False
