"""원본 보존형 다중 ZIP 대조 검사(모의 파일만 사용; 전체 개발 이후 실행)."""
from __future__ import annotations

import hashlib
import io
import zipfile

import pytest

from validation.audit_nested_original_source_archive import audit_archive, DEFAULT_PREFIX


def _zip(entries: dict[str, bytes]) -> bytes:
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, value in entries.items():
            archive.writestr(name, value)
    return out.getvalue()


def _archive(tmp_path, files):
    inner = _zip({DEFAULT_PREFIX + name: data for name, data in files.items()})
    nested = _zip({"handoff/source_snapshot.zip": inner})
    outer = tmp_path / "source_bundle.zip"
    outer.write_bytes(_zip({"original/old_handoff.zip": nested}))
    return outer


def test_nested_snapshot_exact_match_and_git_blob_preservation(tmp_path):
    content = b"import math\n"
    zip_file = _archive(tmp_path, {"desktop/example.py": content})
    checkout = tmp_path / "existing_sources"
    (checkout / "desktop").mkdir(parents=True)
    (checkout / "desktop" / "example.py").write_bytes(content)
    result = audit_archive(zip_file, checkout, expected_count=1)
    assert result["all_originals_match"] is True
    assert result["summary"] == {"match": 1, "missing": 0,
                                  "different": 0, "unsafe_path": 0}
    blob = b"blob " + str(len(content)).encode("ascii") + b"\x00" + content
    assert result["files"][0]["original_git_blob_sha1"] == hashlib.sha1(blob).hexdigest()
    assert result["files"][0]["original_sha256"] == hashlib.sha256(content).hexdigest()


def test_missing_and_changed_originals_are_not_modified(tmp_path):
    zip_file = _archive(tmp_path, {
        "desktop/absent.py": b"original a",
        "desktop/existing.py": b"original b",
    })
    checkout = tmp_path / "existing_sources"
    (checkout / "desktop").mkdir(parents=True)
    target = checkout / "desktop" / "existing.py"
    target.write_bytes(b"new code must be preserved")
    result = audit_archive(zip_file, checkout, expected_count=2)
    assert result["summary"]["missing"] == 1
    assert result["summary"]["different"] == 1
    assert result["all_originals_match"] is False
    assert not (checkout / "desktop" / "absent.py").exists()
    assert target.read_bytes() == b"new code must be preserved"


def test_expected_count_prevents_false_complete_report(tmp_path):
    zip_file = _archive(tmp_path, {"desktop/a.py": b"pass\n"})
    checkout = tmp_path / "sources"
    (checkout / "desktop").mkdir(parents=True)
    (checkout / "desktop" / "a.py").write_bytes(b"pass\n")
    status = audit_archive(zip_file, checkout, expected_count=1099)
    assert status["expected_count_matches"] is False
    assert status["all_originals_match"] is False


def test_ambiguous_windows_case_paths_fail_before_source_overwrite(tmp_path):
    zip_file = _archive(tmp_path, {"desktop/Config.py": b"a", "desktop/config.py": b"b"})
    checkout = tmp_path / "sources"
    checkout.mkdir()
    with pytest.raises(ValueError, match="대소문자"):
        audit_archive(zip_file, checkout)


def test_path_traversal_in_nested_source_is_rejected(tmp_path):
    zip_file = _archive(tmp_path, {"desktop/../../foreign.py": b"x"})
    checkout = tmp_path / "sources"
    checkout.mkdir()
    with pytest.raises(ValueError, match="비정상"):
        audit_archive(zip_file, checkout)


def test_multiple_archives_exact_unique_originals(tmp_path):
    from validation.audit_nested_original_source_archive import audit_archive_collection
    first = _archive(tmp_path, {"desktop/a.py": b"a"})
    second = tmp_path / "second.zip"
    second.write_bytes(_zip({DEFAULT_PREFIX + "desktop/b.py": b"b"}))
    checkout = tmp_path / "sources"
    (checkout / "desktop").mkdir(parents=True)
    (checkout / "desktop" / "a.py").write_bytes(b"a")
    (checkout / "desktop" / "b.py").write_bytes(b"b")
    result = audit_archive_collection([first, second], checkout, expected_count=2)
    assert result["all_originals_match"] is True
    assert result["unique_original_paths"] == 2
    assert result["summary"]["match"] == 2
    assert result["duplicate_original_paths"] == []


def test_multiple_archives_conflicting_originals_never_auto_merge(tmp_path):
    from validation.audit_nested_original_source_archive import audit_archive_collection
    first = _archive(tmp_path, {"desktop/a.py": b"old"})
    second = tmp_path / "second.zip"
    second.write_bytes(_zip({DEFAULT_PREFIX + "desktop/a.py": b"new"}))
    checkout = tmp_path / "sources"
    (checkout / "desktop").mkdir(parents=True)
    (checkout / "desktop" / "a.py").write_bytes(b"old")
    result = audit_archive_collection([first, second], checkout, expected_count=1)
    assert result["all_originals_match"] is False
    assert result["unique_original_paths"] == 1
    assert result["duplicate_original_paths"][0]["conflicting_content"] is True
    assert (checkout / "desktop" / "a.py").read_bytes() == b"old"


def test_multiple_archives_identical_duplicates_still_not_1099_unique(tmp_path):
    from validation.audit_nested_original_source_archive import audit_archive_collection
    first = _archive(tmp_path, {"desktop/a.py": b"same"})
    second = tmp_path / "second.zip"
    second.write_bytes(_zip({DEFAULT_PREFIX + "desktop/a.py": b"same"}))
    checkout = tmp_path / "sources"
    (checkout / "desktop").mkdir(parents=True)
    (checkout / "desktop" / "a.py").write_bytes(b"same")
    result = audit_archive_collection([first, second], checkout, expected_count=2)
    assert result["expected_count_matches"] is False
    assert result["duplicate_original_paths"][0]["conflicting_content"] is False
    assert result["all_originals_match"] is False


def test_nested_source_rejects_duplicate_zip_members(tmp_path):
    inner = _zip({DEFAULT_PREFIX + "desktop/a.py": b"a"})
    source = tmp_path / "duplicate.zip"
    import warnings
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        with zipfile.ZipFile(source, "w") as z:
            z.writestr(DEFAULT_PREFIX + "desktop/a.py", b"a")
            z.writestr(DEFAULT_PREFIX + "desktop/a.py", b"b")
    checkout = tmp_path / "sources"
    checkout.mkdir()
    with pytest.raises(ValueError, match="중복"):
        audit_archive(source, checkout)


def test_nested_source_rejects_multiple_snapshot_roots(tmp_path):
    first = _zip({DEFAULT_PREFIX + "desktop/a.py": b"a"})
    second = _zip({DEFAULT_PREFIX + "desktop/b.py": b"b"})
    source = tmp_path / "two_roots.zip"
    source.write_bytes(_zip({"one.zip": first, "two.zip": second}))
    checkout = tmp_path / "sources"
    checkout.mkdir()
    with pytest.raises(ValueError, match="복수"):
        audit_archive(source, checkout)


def test_symlink_parent_cannot_be_audited_as_regular_original(tmp_path):
    import os
    source = _archive(tmp_path, {"desktop/a.py": b"a"})
    checkout = tmp_path / "sources"
    checkout.mkdir()
    real = tmp_path / "actual"
    real.mkdir()
    (real / "a.py").write_bytes(b"a")
    try:
        (checkout / "desktop").symlink_to(real, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("이 테스트 환경에서 심볼릭 링크를 생성할 수 없습니다.")
    # Even an in-tree alias must never be silently treated as a regular file.
    result = audit_archive(source, checkout, expected_count=1)
    assert result["summary"]["unsafe_path"] == 1
    assert result["all_originals_match"] is False


def test_nested_archive_rejects_unix_symlink_member(tmp_path):
    source = tmp_path / "symlink.zip"
    with zipfile.ZipFile(source, "w") as z:
        item = zipfile.ZipInfo(DEFAULT_PREFIX + "desktop/alias.py")
        item.create_system = 3
        item.external_attr = (0o120777 << 16)
        z.writestr(item, b"desktop/actual.py")
    checkout = tmp_path / "sources"
    checkout.mkdir()
    with pytest.raises(ValueError, match="심볼릭 링크"):
        audit_archive(source, checkout)


def test_nested_archive_rejects_duplicate_archive_input(tmp_path):
    from validation.audit_nested_original_source_archive import audit_archive_collection
    source = _archive(tmp_path, {"desktop/a.py": b"a"})
    checkout = tmp_path / "sources"
    checkout.mkdir()
    with pytest.raises(ValueError, match="중복 입력"):
        audit_archive_collection([source, source], checkout)


def test_nested_archive_rejects_invalid_source_prefix(tmp_path):
    source = _archive(tmp_path, {"desktop/a.py": b"a"})
    checkout = tmp_path / "sources"
    checkout.mkdir()
    with pytest.raises(ValueError, match="접두사"):
        audit_archive(source, checkout, prefix="../")
