"""User-owned SQLite storage for the offline AIWACK desktop program.

The prototype only stores a local diagnostic note. No customer, owner account,
external AI, financial activity, or autonomous operations are implemented.
"""
from __future__ import annotations

import os
from contextlib import contextmanager
from collections.abc import Iterator
from pathlib import Path
import sqlite3

APP_DIR_NAME = "AIWACK"
CHECKPOINT_KEY = "local_manual_test"


def user_data_dir() -> Path:
    """Return a writable user-level directory, never PyInstaller's temp folder."""
    override = os.getenv("AIWACK_DATA_DIR")
    if override:
        return Path(override).expanduser().resolve()
    if os.name == "nt":
        base = os.getenv("LOCALAPPDATA") or os.getenv("APPDATA")
        if base:
            return Path(base) / APP_DIR_NAME
        return Path.home() / "AppData" / "Local" / APP_DIR_NAME
    base = os.getenv("XDG_DATA_HOME")
    return (Path(base) if base else Path.home() / ".local" / "share") / APP_DIR_NAME


class LocalStore:
    """Short transactions, durable file location and no hidden HTTP endpoint."""

    def __init__(self, path: Path | None = None):
        self.path = Path(path) if path is not None else user_data_dir() / "aiwack.sqlite3"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        # SQLite connection context managers commit but do not close files.
        # Windows requires explicit closure to remove test DBs and reopen files.
        connection = sqlite3.connect(self.path, timeout=10)
        try:
            connection.execute("PRAGMA busy_timeout = 10000")
            with connection:
                yield connection
        finally:
            connection.close()

    def _init_schema(self) -> None:
        # Matches the existing development table for future migration support.
        with self._connect() as con:
            con.execute("""
                CREATE TABLE IF NOT EXISTS system_metadata (
                    id INTEGER PRIMARY KEY,
                    key VARCHAR(120) NOT NULL UNIQUE,
                    value VARCHAR(1000) NOT NULL,
                    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
            """)

    def save_note(self, value: str) -> None:
        note = value.strip()
        if not note or len(note) > 120:
            raise ValueError("메모는 1~120자여야 합니다.")
        with self._connect() as con:
            con.execute(
                "INSERT INTO system_metadata (key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (CHECKPOINT_KEY, note),
            )

    def read_note(self) -> str:
        with self._connect() as con:
            row = con.execute(
                "SELECT value FROM system_metadata WHERE key = ?", (CHECKPOINT_KEY,)
            ).fetchone()
        return row[0] if row else ""

    def health(self) -> dict[str, str]:
        with self._connect() as con:
            result = con.execute("PRAGMA integrity_check").fetchone()[0]
        if result != "ok":
            raise RuntimeError(f"SQLite 파일 무결성 오류: {result}")
        return {"status": "ok", "database": str(self.path), "storage": "SQLite"}
