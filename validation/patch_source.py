"""Validation-branch-only fixes to extracted original source snapshot.
The immutable ZIP on main is never overwritten; these changes only touch runner copies.
"""
from __future__ import annotations
from pathlib import Path
import ast
import sys

def apply(root: Path) -> None:
    path = root / "desktop" / "market_evidence.py"
    original = path.read_text(encoding="utf-8")
    prefix = "WHERE {'1=1' if op == 'DELETE' else '''"
    start = original.find(prefix)
    if start < 0:
        if "_AIWACK_VALIDATION_311_IMMUTABLE" in original:
            print("Patch already applied")
            return
        raise RuntimeError("Unexpected source: cannot find 3.11-incompatible market evidence trigger")
    close = "'''};"
    end = original.find(close, start + len(prefix))
    if end < 0:
        raise RuntimeError("Cannot find expected end of source expression")
    sql = original[start + len(prefix):end]
    label = "_AIWACK_VALIDATION_311_IMMUTABLE"
    definition = label + " = " + repr(sql) + "\n"
    if label in original:
        raise RuntimeError("Unexpected existing validation marker")
    oldexpr = original[start:end + len(close)]
    newexpr = "WHERE {'1=1' if op == 'DELETE' else " + label + "};"
    text = original.replace(oldexpr, newexpr, 1)
    anchor = "\n\ndef initialize(con: sqlite3.Connection) -> None:\n"
    if anchor not in text:
        raise RuntimeError("Unexpected initialize anchor")
    text = text.replace(anchor, "\n\n" + definition + anchor, 1)
    ast.parse(text, filename=str(path))
    path.write_text(text, encoding="utf-8")
    print("Applied validation-branch Python 3.11-compatible immutable trigger patch:", path)

if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("usage: patch_source.py EXTRACTED_SOURCE_DIRECTORY")
    apply(Path(sys.argv[1]).resolve())
