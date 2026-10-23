"""누적 원본 ZIP SHA256·무덮어쓰기·CRC 선검증 회귀 (실 Windows 시험 아님)."""
import stat
import zipfile
import pytest
from validation.restore_original_source_history import reconcile


def _zip(path, entries):
    with zipfile.ZipFile(path, 'w') as archive:
        for name, content in entries:
            archive.writestr(name, content)
    return path


def test_read_only_does_not_restore(tmp_path):
    root=tmp_path/'repo';root.mkdir()
    archive=_zip(tmp_path/'original.zip',[('docs/original.md',b'original')])
    report=reconcile(archive,root)
    assert report['missing'][0]['path']=='docs/original.md'
    assert not (root/'docs').exists()


def test_restore_exact_bytes_and_idempotent(tmp_path):
    root=tmp_path/'repo';root.mkdir()
    content='원문\r\n보존'.encode('utf8')
    archive=_zip(tmp_path/'original.zip',[('docs/original.md',content)])
    assert len(reconcile(archive,root,restore_missing=True)['restored'])==1
    assert (root/'docs/original.md').read_bytes()==content
    assert len(reconcile(archive,root,restore_missing=True)['identical'])==1


def test_changed_file_is_never_overwritten(tmp_path):
    root=tmp_path/'repo';(root/'docs').mkdir(parents=True)
    (root/'docs/original.md').write_bytes(b'newer')
    archive=_zip(tmp_path/'original.zip',[('docs/original.md',b'older')])
    report=reconcile(archive,root,restore_missing=True)
    assert len(report['conflicts'])==1 and not report['complete']
    assert (root/'docs/original.md').read_bytes()==b'newer'


@pytest.mark.parametrize('path',['../escape','/absolute','docs\\evil','C:/drive',
                                 'docs/CON.txt','docs/trailing. ','docs/../../escape',
                                 'docs//alias.txt','docs/./alias.txt','docs/has?.txt',
                                 'docs/a<b>.md','docs/pipe|name','docs/illegal*.md'])
def test_windows_unsafe_archive_paths_blocked(tmp_path,path):
    root=tmp_path/'repo';root.mkdir()
    archive=_zip(tmp_path/'original.zip',[(path,b'bad')])
    with pytest.raises(ValueError):
        reconcile(archive,root,restore_missing=True)
    assert not list(root.iterdir())


def test_unicode_nfc_collision_rejected_before_writes(tmp_path):
    root=tmp_path/'repo';root.mkdir()
    archive=_zip(tmp_path/'original.zip',[('docs/é.md',b'a'),('docs/e\u0301.md',b'b')])
    with pytest.raises(ValueError,match='중복'):
        reconcile(archive,root,restore_missing=True)
    assert not list(root.iterdir())


def test_zip_symlink_rejected(tmp_path):
    root=tmp_path/'repo';root.mkdir()
    archive=tmp_path/'original.zip'
    with zipfile.ZipFile(archive,'w') as z:
        item=zipfile.ZipInfo('docs/link')
        item.create_system=3
        item.external_attr=(stat.S_IFLNK|0o777)<<16
        z.writestr(item,'../escape')
    with pytest.raises(ValueError,match='링크'):
        reconcile(archive,root,restore_missing=True)


def test_later_corrupt_crc_prevents_any_restore(tmp_path):
    root=tmp_path/'repo';root.mkdir()
    archive=_zip(tmp_path/'original.zip',[('docs/1-good.md',b'original'),
                                          ('docs/2-broken.md',b'corrupt-me')])
    raw=archive.read_bytes()
    offset=raw.find(b'corrupt-me')
    assert offset>0
    archive.write_bytes(raw[:offset]+b'X'+raw[offset+1:])
    with pytest.raises((ValueError,zipfile.BadZipFile)):
        reconcile(archive,root,restore_missing=True)
    assert not (root/'docs').exists()
