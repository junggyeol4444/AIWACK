import hashlib
import json
import zipfile

import pytest

from validation.plan_github_history_restore import audit_github_history_restore, main


def blob(data):
    return hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest()


def archive(tmp_path, entries):
    path = tmp_path / 'history.zip'
    with zipfile.ZipFile(path, 'w') as z:
        for name, content in entries.items():
            z.writestr(name, content)
    return path


def tree(*entries):
    return {'truncated': False, 'tree': list(entries)}


def entry(name, data, kind='blob', mode='100644'):
    return {'path': name, 'type': kind, 'mode': mode, 'sha': blob(data)}


def test_missing_and_exact_original_bytes(tmp_path):
    path = archive(tmp_path, {'docs/one.md': b'original', 'docs/two.md': b'two'})
    before = path.read_bytes()
    result = audit_github_history_restore(path, tree(entry('docs/one.md', b'original')))
    assert result['total'] == 2
    assert [r['path'] for r in result['identical']] == ['docs/one.md']
    assert [r['path'] for r in result['missing']] == ['docs/two.md']
    assert result['restorable_paths'][0]['git_blob_sha1'] == blob(b'two')
    assert result['original_preserved'] and path.read_bytes() == before


def test_changed_remote_is_never_overwritten(tmp_path):
    path = archive(tmp_path, {'docs/one.md': b'old'})
    result = audit_github_history_restore(path, tree(entry('docs/one.md', b'new')))
    assert len(result['conflicts']) == 1
    assert not result['safe_to_restore_without_overwrite']
    assert result['restorable_paths'] == []


def test_symlink_remote_conflict(tmp_path):
    path = archive(tmp_path, {'docs/one.md': b'old'})
    result = audit_github_history_restore(path, tree(entry('docs/one.md', b'old', 'blob', '120000')))
    assert len(result['conflicts']) == 1


def test_truncated_tree_refused(tmp_path):
    path = archive(tmp_path, {'docs/one.md': b'old'})
    with pytest.raises(ValueError, match='truncated'):
        audit_github_history_restore(path, {'truncated': True, 'tree': []})


def test_windows_alias_collision_refused(tmp_path):
    path = archive(tmp_path, {'docs/one.md': b'old'})
    with pytest.raises(ValueError, match='Windows 경로 충돌'):
        audit_github_history_restore(path, tree(entry('docs/One.md', b'new')))


def test_duplicate_tree_path_refused(tmp_path):
    path = archive(tmp_path, {'docs/one.md': b'old'})
    with pytest.raises(ValueError, match='중복 경로'):
        audit_github_history_restore(path, tree(entry('docs/one.md', b'old'), entry('docs/one.md', b'old')))


def test_git_file_parent_conflict(tmp_path):
    path = archive(tmp_path, {'docs/one.md': b'old'})
    result = audit_github_history_restore(path, tree(entry('docs', b'file')))
    assert len(result['conflicts']) == 1
    assert result['restorable_paths'] == []


def test_cli_exit_status_and_read_only(tmp_path, capsys):
    path = archive(tmp_path, {'docs/one.md': b'old'})
    source = tmp_path / 'tree.json'
    source.write_text(json.dumps(tree()), encoding='utf-8')
    assert main([str(path), str(source)]) == 2
    assert json.loads(capsys.readouterr().out)['missing'][0]['path'] == 'docs/one.md'
