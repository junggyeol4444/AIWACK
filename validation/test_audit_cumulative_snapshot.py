"""이전 1154+ 누적 원본 무삭제 전수 대조 동작 검증 (실 EXE/실 GGUF 테스트 아님)."""
import hashlib
import json

import pytest

from validation.audit_cumulative_snapshot import audit


def _manifest(tmp_path, rows):
    file = tmp_path / 'manifest.json'
    file.write_text(json.dumps({'source_sha256': rows}), encoding='utf8')
    return file


def _sha(b):
    return hashlib.sha256(b).hexdigest()


def test_detects_exact_bytes_and_additions_without_rewriting(tmp_path):
    root = tmp_path / 'repo'; root.mkdir()
    (root/'original.md').write_bytes(b'\r\nkeep original\r\n')
    (root/'new.md').write_bytes(b'new')
    old = (root/'original.md').read_bytes()
    result = audit(_manifest(tmp_path, {'original.md': _sha(old)}), root)
    assert result['snapshot_fully_identical'] is True
    assert len(result['verified_identical']) == 1
    assert result['new_files'] == ['new.md']
    assert (root/'original.md').read_bytes() == old


def test_old_version_modified_and_missing_must_be_reviewed(tmp_path):
    root = tmp_path / 'repo'; root.mkdir()
    (root/'code.py').write_bytes(b'version 2')
    result = audit(_manifest(tmp_path, {'code.py': _sha(b'version 1'), 'older.md': _sha(b'earlier')}), root)
    assert [v['path'] for v in result['modified']] == ['code.py']
    assert [v['path'] for v in result['missing']] == ['older.md']
    assert result['requires_manual_merge_review'] is True
    assert (root/'code.py').read_bytes() == b'version 2'


@pytest.mark.parametrize('path', ['../outside', '/abs', 'C:/bad', 'dir/../p', 'dir//p',
                                  'dir/./p', 'source\\file'])
def test_rejects_traversal_and_noncanonical_manifest_paths(tmp_path, path):
    root = tmp_path/'repo';root.mkdir()
    with pytest.raises(ValueError):
        audit(_manifest(tmp_path, {path: _sha(b'anything')}), root)


def test_link_not_followed(tmp_path):
    root=tmp_path/'repo';root.mkdir()
    target=tmp_path/'outside';target.write_bytes(b'secret')
    try:
        (root/'linked').symlink_to(target)
    except (OSError, NotImplementedError):
        pytest.skip('플랫폼 링크 미지원')
    result=audit(_manifest(tmp_path, {'linked':_sha(b'secret')}), root)
    assert result['unsafe'] == [{'path':'linked','reason':'symlink'}]
    assert not result['verified_identical']


def test_rejects_casefold_collision(tmp_path):
    root=tmp_path/'repo';root.mkdir()
    with pytest.raises(ValueError, match='대소문자'):
        audit(_manifest(tmp_path, {'Doc.md':_sha(b'a'),'doc.md':_sha(b'b')}), root)
