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
