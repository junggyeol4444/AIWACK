"""Export Windows E2E-verified AIWACK source snapshot to a directly browsable tree.

Source is the integrated ZIP artifact produced by GitHub Actions run 39184374421
(windows-2025 success). This tool refuses other bytes or an existing target.
The resulting tree omits generated test logs, bytecode and databases, not app code.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
from pathlib import Path, PurePosixPath
import zipfile

EXPECTED_SHA256 = "07f154c47aa0f7d747824a3a4763e1d12c1fbf475d647df0e2da6e3471709f2a"
PREFIX = "AIWACK-Stage54/"
EXPECTED_FILES = 851
REQUIRED = {
    "desktop/entry.py", "desktop/app.py", "desktop/storage.py",
    "desktop/company_operations.py", "desktop/company_office_gui.py",
    "desktop/company_model_connect_ui.py",
    "docs/original_project_spec.txt", "pyproject.toml", "README.md",
    "tests/test_company_approved_autocycle.py",
}
REJECT_SUFFIXES = (".pyc", ".pyo", ".log", ".pid", ".exit", ".sqlite3", ".db")


def export(snapshot: Path, destination: Path) -> dict:
    actual = hashlib.sha256(snapshot.read_bytes()).hexdigest()
    if actual != EXPECTED_SHA256:
        raise ValueError(f"Integrated source digest differs: {actual}")
    if destination.exists() and any(destination.iterdir()):
        raise FileExistsError(f"Refusing to overwrite existing source: {destination}")
    staging = []
    manifest = []
    with zipfile.ZipFile(snapshot) as source:
        if source.testzip() is not None:
            raise ValueError("Integrated source ZIP CRC failure")
        for info in source.infolist():
            if info.is_dir():
                continue
            raw = info.filename
            if not raw.startswith(PREFIX):
                raise ValueError(f"Unexpected archive path: {raw}")
            relative = raw[len(PREFIX):]
            parts = PurePosixPath(relative).parts
            if not parts or any(part in (".", "..", ".git", "__pycache__", ".pytest_cache") for part in parts):
                continue
            if relative in (".env", "dev_company.sqlite3") or relative.lower().endswith(REJECT_SUFFIXES):
                continue
            if info.external_attr >> 16 & 0o170000 == 0o120000:
                raise ValueError(f"Archive symlink refused: {relative}")
            data = source.read(info)
            if relative.endswith(".py"):
                ast.parse(data.decode("utf-8-sig"), filename=relative)
            staging.append((relative, data))
            manifest.append({
                "path": relative,
                "bytes": len(data),
                "sha256": hashlib.sha256(data).hexdigest(),
            })
    present = {p for p, _ in staging}
    if len(staging) != EXPECTED_FILES or not REQUIRED.issubset(present):
        raise ValueError(f"Unexpected source layout: {len(staging)} files; missing {sorted(REQUIRED - present)}")
    destination.mkdir(parents=True, exist_ok=True)
    for relative, data in staging:
        target = destination.joinpath(*PurePosixPath(relative).parts)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    receipt = {
        "source": "GitHub Actions 39184374421 Windows 2025 integrated source artifact",
        "source_commit": "9eb950adb30da7e694e0b698bbcd2bf849c15c53",
        "archive_sha256": actual,
        "files": len(manifest),
        "contents": sorted(manifest, key=lambda x: x["path"]),
        "note": "Server 2022/2025 scoped GUI tests passed; not Windows 11 or all T01-T20 acceptance.",
    }
    (destination / "VERIFIED_SOURCE_MANIFEST.json").write_text(
        json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return receipt


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("snapshot", type=Path)
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    print(json.dumps({
        k: v for k, v in export(args.snapshot, args.destination).items()
        if k != "contents"
    }, ensure_ascii=False))
