"""원본 역사 문서 복원 시 원문·기존 소스·Windows 경로를 보호한다."""
import hashlib
import json
from pathlib import Path
import zipfile

import pytest

from validation.restore_original_history_manifest import restore_manifest_history


def archive(tmp_path, files, *, manifest_override=None):
    path = tmp_path / 'history.zip'
    manifest = {'files': [{'path': name, 'bytes': len(data),
                           'sha256': hashlib.sha256(data).hexdigest()}
                          for name, data in files.items()]}
    if manifest_override:
        manifest_override(manifest)
    with zipfile.ZipFile(path, 'w') as out:
        for name, data in files.items():
            out.writestr(name, data)
        out.writestr('PRESERVATION_MANIFEST.json', json.dumps(manifest))
    return path


def test_dry_run_never_creates(tmp_path):
    root = tmp_path / 'repo'; root.mkdir()
    source = archive(tmp_path, {'docs/원본.md': b'original'})
    result = restore_manifest_history(source, root)
    assert result['missing'] == ['docs/원본.md']
    assert result['restored'] == []
    assert not (root / 'docs').exists()


def test_apply_restores_only_missing_bytes(tmp_path):
    root = tmp_path / 'repo'; root.mkdir()
    source = archive(tmp_path, {'docs/원본.md': b'original', 'docs/새문서.md': b'new'})
    (root / 'docs').mkdir(); (root / 'docs/원본.md').write_bytes(b'changed')
    result = restore_manifest_history(source, root, apply=True)
    assert result['existing_conflict'] == ['docs/원본.md']
    assert result['restored'] == ['docs/새문서.md']
    assert (root / 'docs/원본.md').read_bytes() == b'changed'
    assert (root / 'docs/새문서.md').read_bytes() == b'new'


def test_identical_is_not_rewritten(tmp_path):
    root = tmp_path / 'repo'; root.mkdir()
    source = archive(tmp_path, {'docs/a.md': b'same'})
    (root / 'docs').mkdir(); target = root / 'docs/a.md'; target.write_bytes(b'same')
    result = restore_manifest_history(source, root, apply=True)
    assert result['existing_identical'] == ['docs/a.md']
    assert not result['restored']


def test_corrupt_manifest_blocks_all_writes(tmp_path):
    root = tmp_path / 'repo'; root.mkdir()
    source = archive(tmp_path, {'docs/a.md': b'good', 'docs/b.md': b'good'},
                     manifest_override=lambda m: m['files'][1].update(sha256='0'*64))
    with pytest.raises(ValueError, match='SHA256'):
        restore_manifest_history(source, root, apply=True)
    assert not (root / 'docs').exists()


def test_windows_case_collision_blocks_all_writes(tmp_path):
    root = tmp_path / 'repo'; root.mkdir()
    source = archive(tmp_path, {'docs/A.md': b'one', 'docs/a.md': b'two'})
    with pytest.raises(ValueError, match='Windows'):
        restore_manifest_history(source, root, apply=True)
    assert not (root / 'docs').exists()


def test_parent_symlink_blocks(tmp_path):
    root = tmp_path / 'repo'; root.mkdir()
    outside = tmp_path / 'outside'; outside.mkdir()
    (root / 'docs').symlink_to(outside, target_is_directory=True)
    source = archive(tmp_path, {'docs/a.md': b'data'})
    with pytest.raises(ValueError, match='심볼릭'):
        restore_manifest_history(source, root, apply=True)
    assert not (outside / 'a.md').exists()


def test_manifest_missing_member_blocks(tmp_path):
    root = tmp_path / 'repo'; root.mkdir()
    source = archive(tmp_path, {'docs/a.md': b'data'})
    with zipfile.ZipFile(source, 'a') as out:
        out.writestr('docs/extra.md', b'extra')
    with pytest.raises(ValueError, match='목록'):
        restore_manifest_history(source, root, apply=True)


def test_duplicate_windows_alias_in_existing_tree(tmp_path):
    root = tmp_path / 'repo'; root.mkdir()
    (root / 'DOCS').mkdir(); (root / 'docs').mkdir()
    source = archive(tmp_path, {'docs/new.md': b'data'})
    with pytest.raises(ValueError, match='Windows'):
        restore_manifest_history(source, root, apply=True)
