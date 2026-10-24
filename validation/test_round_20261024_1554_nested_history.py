"""중첩 역사 ZIP 감사의 원본 무변경·중복·변조·버전 보존 회귀."""
import hashlib
import io
from pathlib import Path
import tempfile
import unittest
import zipfile

from validation.audit_nested_original_archives import inventory_nested_zip


def pack(items):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, content in items:
            archive.writestr(name, content)
    return stream.getvalue()


class NestedHistoryAuditTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "history.zip"

    def write(self, data):
        self.path.write_bytes(data)
        return data

    def test_nested_leaf_hash_and_original_unchanged(self):
        child = pack([("docs/report.md", b"first")])
        original = self.write(pack([("source.zip", child), ("notes.txt", b"hello")]))
        result = inventory_nested_zip(self.path)
        self.assertEqual(result["archive_count"], 2)
        self.assertEqual(result["leaf_file_count"], 2)
        self.assertEqual(result["root_sha256"], hashlib.sha256(original).hexdigest())
        self.assertEqual(self.path.read_bytes(), original)
        self.assertFalse(result["original_versions_auto_selected"])

    def test_nested_version_conflict_preserved(self):
        a = pack([("shared.txt", b"old")])
        b = pack([("shared.txt", b"new")])
        self.write(pack([("a.zip", a), ("b.zip", b)]))
        result = inventory_nested_zip(self.path)
        self.assertEqual(result["multi_version_paths"], ["shared.txt"])
        self.assertEqual(len({x["sha256"] for x in result["files"]}), 2)

    def test_same_version_no_false_conflict(self):
        a = pack([("shared.txt", b"same")])
        self.write(pack([("a.zip", a), ("b.zip", a)]))
        self.assertEqual(inventory_nested_zip(self.path)["multi_version_paths"], [])

    def test_path_traversal_rejected(self):
        self.write(pack([("../escape.txt", b"no")]))
        with self.assertRaises(ValueError):
            inventory_nested_zip(self.path)

    def test_windows_case_alias_rejected(self):
        self.write(pack([("A.txt", b"a"), ("a.TXT", b"b")]))
        with self.assertRaises(ValueError):
            inventory_nested_zip(self.path)

    def test_duplicate_exact_path_rejected(self):
        self.write(pack([("x.txt", b"one"), ("x.txt", b"two")]))
        with self.assertRaises(ValueError):
            inventory_nested_zip(self.path)

    def test_bad_nested_zip_rejected(self):
        self.write(pack([("bad.zip", b"not a zip")]))
        with self.assertRaises(ValueError):
            inventory_nested_zip(self.path)

    def test_depth_limit_rejected(self):
        nested = pack([("end.txt", b"ok")])
        for i in range(3):
            nested = pack([(f"layer{i}.zip", nested)])
        self.write(nested)
        with self.assertRaises(ValueError):
            inventory_nested_zip(self.path, max_depth=2)

    def test_invalid_depth_rejected(self):
        self.write(pack([("ok.txt", b"ok")]))
        with self.assertRaises(ValueError):
            inventory_nested_zip(self.path, max_depth=0)

    def test_reserved_windows_filename_rejected(self):
        self.write(pack([("CON.txt", b"bad")]))
        with self.assertRaises(ValueError):
            inventory_nested_zip(self.path)


if __name__ == "__main__":
    unittest.main()
