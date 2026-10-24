"""과거 원본 파일과 GitHub 전체 tree SHA 대조 신규 회귀 (실GGUF 검증 아님)."""
import hashlib
import json
import zipfile

import pytest

from validation.compare_zip_archives_github_tree import compare_zip_archives_to_github, main


def _blob(data):
    return hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest()


def _archive(tmp_path, name, entries):
    file = tmp_path / name
    with zipfile.ZipFile(file, 'w') as bundle:
        for path, content in entries.items():
            bundle.writestr(path, content)
    return file


def _entry(path, data=b'', kind='blob', mode='100644'):
    return {'path': path, 'type': kind, 'mode': mode, 'sha': _blob(data)}


def _tree(*items):
    return {'truncated': False, 'tree': list(items)}


def test_exact_archive_bytes_and_added_remote_path(tmp_path):
    source = _archive(tmp_path, 'a.zip', {'docs/one.md': b'one'})
    before = source.read_bytes()
    tree = _tree(_entry('docs', kind='tree', mode='040000'),
                 _entry('docs/one.md', b'one'), _entry('docs/new.md', b'new'))
    report = compare_zip_archives_to_github([source], tree, expected_paths=1)
    assert report['full_expected_paths_compared'] is True
    assert report['status_counts']['unchanged'] == 1
    assert report['remote_only_paths'] == ['docs', 'docs/new.md']
    assert report['manual_review_required'] is False
    assert source.read_bytes() == before


def test_missing_with_parent_directory_is_recoverable_without_overwriting(tmp_path):
    source = _archive(tmp_path, 'a.zip', {'docs/missing.md': b'data'})
    report = compare_zip_archives_to_github(
        [source], _tree(_entry('docs', kind='tree', mode='040000')), 1)
    assert report['status_counts']['missing'] == 1
    assert report['status_counts']['remote_type_conflict'] == 0
    assert report['manual_review_required'] is True


def test_changed_remote_and_historical_multiversion_are_separate(tmp_path):
    archive1 = _archive(tmp_path, 'first.zip', {'model.py': b'old', 'app.py': b'one'})
    archive2 = _archive(tmp_path, 'second.zip', {'model.py': b'new'})
    report = compare_zip_archives_to_github(
        [archive1, archive2],
        _tree(_entry('model.py', b'old'), _entry('app.py', b'local')), 2)
    assert report['status_counts']['historical_conflict'] == 1
    assert report['status_counts']['changed'] == 1
    assert report['all_development_merged'] is False


def test_exact_duplicate_versions_across_archives_are_not_false_conflicts(tmp_path):
    a = _archive(tmp_path, 'a.zip', {'same.md': b'one'})
    b = _archive(tmp_path, 'b.zip', {'same.md': b'one'})
    report = compare_zip_archives_to_github([a, b], _tree(_entry('same.md', b'one')), 1)
    assert report['status_counts']['unchanged'] == 1
    assert report['status_counts']['historical_conflict'] == 0


def test_remote_file_blocks_missing_archive_directory_path(tmp_path):
    source = _archive(tmp_path, 'a.zip', {'docs/history.md': b'h'})
    report = compare_zip_archives_to_github([source], _tree(_entry('docs', b'file')), 1)
    assert report['status_counts']['remote_type_conflict'] == 1


def test_truncated_github_tree_is_not_full_comparison(tmp_path):
    a = _archive(tmp_path, 'a.zip', {'original.md': b'a'})
    with pytest.raises(ValueError, match='truncated'):
        compare_zip_archives_to_github([a], {'truncated': True, 'tree': []})


def test_missing_original_entries_cannot_claim_1099_complete(tmp_path):
    a = _archive(tmp_path, 'a.zip', {'one.md': b'one'})
    with pytest.raises(ValueError, match='불일치'):
        compare_zip_archives_to_github([a], _tree(), 1099)


def test_source_zip_windows_traversal_is_refused(tmp_path):
    a = _archive(tmp_path, 'a.zip', {'../escape.md': b'unsafe'})
    with pytest.raises(ValueError, match='안전하지 않은'):
        compare_zip_archives_to_github([a], _tree())


def test_source_zip_overlapping_windows_case_aliases_refused(tmp_path):
    a = _archive(tmp_path, 'a.zip', {'App.py': b'a'})
    b = _archive(tmp_path, 'b.zip', {'app.py': b'b'})
    with pytest.raises(ValueError, match='Windows 경로 충돌'):
        compare_zip_archives_to_github([a,b], _tree())


def test_remote_symlink_is_not_same_even_if_blob_sha_matches(tmp_path):
    a = _archive(tmp_path, 'a.zip', {'link.md': b'target'})
    report = compare_zip_archives_to_github(
        [a], _tree(_entry('link.md', b'target', 'blob', '120000')), 1)
    assert report['status_counts']['remote_type_conflict'] == 1


def test_cli_report_does_not_overwrite(tmp_path, capsys):
    source = _archive(tmp_path, 'a.zip', {'app.py': b'one'})
    tree_file = tmp_path / 'tree.json'
    tree_file.write_text(json.dumps(_tree(_entry('app.py', b'one'))))
    report_file = tmp_path / 'result.json'
    cmd = [str(tree_file), str(source), '--expected-paths', '1', '--output', str(report_file)]
    assert main(cmd) == 0
    assert json.loads(report_file.read_text())['status_counts']['unchanged'] == 1
    assert main(cmd) == 3
    assert '덮어쓸 수 없습니다' in capsys.readouterr().out


def test_empty_original_zip_must_not_pass_as_fully_verified(tmp_path):
    source = _archive(tmp_path, 'empty.zip', {})
    with pytest.raises(ValueError, match='대조할 파일'):
        compare_zip_archives_to_github([source], _tree())
