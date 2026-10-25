"""AIWACK 원본 ZIP 1099개 전수 대조기 안전 계약.

이 파일의 임시 ZIP은 검사기 계약용이며 과거 원본 전체의 통과 증빙이 아니다.
"""
import stat
import zipfile

import pytest

from validation.audit_cumulative_archives import audit_archives, _read_archive


def _zip(path, entries):
    with zipfile.ZipFile(path, "w") as z:
        for name,data in entries:
            z.writestr(name,data)
    return path


def test_archive_comparison_preserves_changed_missing_and_added(tmp_path):
    old=_zip(tmp_path/"old.zip",[
        ("same.txt",b"same"),("changed.txt",b"old"),("missing.txt",b"lost")])
    current=_zip(tmp_path/"current.zip",[
        ("same.txt",b"same"),("changed.txt",b"new"),("added.txt",b"extra")])
    history=_zip(tmp_path/"history.zip",[("same.txt",b"same"),("history.txt",b"old")])
    report=audit_archives(old,current,history=history)
    assert report["original_files"]==3
    assert report["identical_files"]==1
    assert [r["path"] for r in report["modified_files"]]==["changed.txt"]
    assert [r["path"] for r in report["missing_files"]]==["missing.txt"]
    assert [r["path"] for r in report["added_files"]]==["added.txt"]
    assert report["history"]["missing_files"]==["history.txt"]
    assert report["original_fully_preserved_byte_identical"] is False
    assert report["archive_members_extracted"] is False
    assert report["remote_github_branch_verified"] is False


def test_identical_original_archive_is_reported_without_extraction(tmp_path):
    old=_zip(tmp_path/"original.zip",[("docs/기획.md","기획".encode())])
    current=_zip(tmp_path/"cumulative.zip",[("docs/기획.md","기획".encode())])
    report=audit_archives(old,current)
    assert report["original_fully_preserved_byte_identical"] is True
    assert report["identical_files"]==1


@pytest.mark.parametrize("bad",[
    "../escape.txt","/absolute.txt","dir/../../escape.txt",
    "CON.txt","folder/NUL","folder/name?.txt","folder/trailing. ",
    "folder\\escape.txt",
])
def test_unsafe_windows_paths_are_rejected(tmp_path,bad):
    path=_zip(tmp_path/"unsafe.zip",[(bad,b"x")])
    with pytest.raises(ValueError,match="안전하지"):
        _read_archive(path)


def test_windows_case_collision_is_rejected(tmp_path):
    path=_zip(tmp_path/"collision.zip",[("A.txt",b"1"),("a.TXT",b"2")])
    with pytest.raises(ValueError,match="경로 충돌"):
        _read_archive(path)


def test_unix_symlink_member_is_rejected(tmp_path):
    path=tmp_path/"symlink.zip"
    info=zipfile.ZipInfo("link")
    info.create_system=3
    info.external_attr=(stat.S_IFLNK | 0o777)<<16
    with zipfile.ZipFile(path,"w") as z:
        z.writestr(info,b"target")
    with pytest.raises(ValueError,match="심볼릭 링크"):
        _read_archive(path)


def test_suspicious_compression_ratio_is_rejected(tmp_path):
    path=tmp_path/"bomb.zip"
    with zipfile.ZipFile(path,"w",compression=zipfile.ZIP_DEFLATED) as z:
        z.writestr("repeated.bin",b"0"*200000)
    with pytest.raises(ValueError,match="압축 비율"):
        _read_archive(path)
