"""기존 역사 원본 복원 CLI와 중첩 ZIP 감사 연결 회귀."""
import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
import zipfile

from validation.restore_original_source_history import main


class NestedHistoryCLITests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.archive = self.root / "source.zip"
        with zipfile.ZipFile(self.archive, "w") as stream:
            stream.writestr("old.txt", "원본")
        self.report = self.root / "audit.json"

    def test_nested_audit_creates_valid_json_without_restoring(self):
        before = self.archive.read_bytes()
        capture = io.StringIO()
        with contextlib.redirect_stdout(capture):
            status = main([str(self.archive), str(self.root),
                           "--nested-audit", "--report", str(self.report)])
        self.assertEqual(status, 0)
        self.assertEqual(self.archive.read_bytes(), before)
        self.assertTrue(self.report.read_bytes().endswith(b"\n"))
        report = json.loads(self.report.read_text(encoding="utf-8"))
        self.assertEqual(report["leaf_file_count"], 1)
        self.assertTrue(report["read_only"])
        self.assertFalse(report["original_versions_auto_selected"])

    def test_restore_and_nested_audit_mutually_exclusive(self):
        capture = io.StringIO()
        with contextlib.redirect_stderr(capture):
            status = main([str(self.archive), str(self.root),
                           "--nested-audit", "--restore-missing"])
        self.assertEqual(status, 3)
        self.assertIn("동시 실행", capture.getvalue())

    def test_existing_read_only_mode_unchanged(self):
        capture = io.StringIO()
        with contextlib.redirect_stdout(capture):
            status = main([str(self.archive), str(self.root)])
        self.assertEqual(status, 2)
        report = json.loads(capture.getvalue())
        self.assertEqual(len(report["missing"]), 1)
        self.assertFalse((self.root / "old.txt").exists())


if __name__ == "__main__":
    unittest.main()
