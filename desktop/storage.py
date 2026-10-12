"""Durable offline SQLite data and the single local owner identity.

The password-derived key authenticates a session. It does NOT encrypt the DB.
No remote authentication, external accounts, or financial operations exist yet.
"""
from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
import hashlib
import hmac
import os
from pathlib import Path
import re
import sqlite3
import time

APP_DIR_NAME = "AIWACK"
CHECKPOINT_KEY = "local_manual_test"
HASH_ITERATIONS = 310_000
MAX_FAILURES = 5
LOCK_SECONDS = 60
OWNER_PERMISSIONS = frozenset({"notes:read", "notes:write", "company:manage", "agents:manage", "expenses:approve"})


class AuthenticationError(PermissionError):
    """Authentication failed, owner account locked, or action unauthorized."""


def user_data_dir() -> Path:
    """Return a persistent writable directory, never PyInstaller's temp folder."""
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
    """Single-owner authentication controls notes stored in the local file."""

    def __init__(self, path: Path | None = None):
        self.path = Path(path) if path is not None else user_data_dir() / "aiwack.sqlite3"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._logged_in = False
        self._init_schema()

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        # A context-managed sqlite3 connection only commits: always close on Windows.
        connection = sqlite3.connect(self.path, timeout=10)
        try:
            connection.execute("PRAGMA busy_timeout = 10000")
            with connection:
                yield connection
        finally:
            connection.close()

    def _init_schema(self) -> None:
        with self._connect() as con:
            # Preserve local data from the previous EXE version.
            con.execute("""
                CREATE TABLE IF NOT EXISTS system_metadata (
                    id INTEGER PRIMARY KEY,
                    key VARCHAR(120) NOT NULL UNIQUE,
                    value VARCHAR(1000) NOT NULL,
                    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
            """)
            con.execute("""
                CREATE TABLE IF NOT EXISTS owner_accounts (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    username TEXT NOT NULL,
                    password_salt BLOB NOT NULL,
                    password_hash BLOB NOT NULL,
                    iterations INTEGER NOT NULL,
                    failed_attempts INTEGER NOT NULL DEFAULT 0,
                    locked_until INTEGER NOT NULL DEFAULT 0,
                    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
            """)

    def has_owner(self) -> bool:
        with self._connect() as con:
            return con.execute("SELECT 1 FROM owner_accounts WHERE id = 1").fetchone() is not None

    @property
    def is_authenticated(self) -> bool:
        return self._logged_in

    def setup_owner(self, username: str, password: str) -> None:
        """First-run setup; a second owner cannot overwrite credentials."""
        username = username.strip()
        if not re.fullmatch(r"[A-Za-z0-9_.-]{3,32}", username):
            raise ValueError("관리자 ID는 영문·숫자·._-로 3~32자여야 합니다.")
        if not isinstance(password, str) or not (12 <= len(password) <= 1024) or password.isspace():
            raise ValueError("비밀번호는 12~1024자로 설정하세요.")
        salt = os.urandom(16)
        digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, HASH_ITERATIONS)
        try:
            with self._connect() as con:
                con.execute(
                    "INSERT INTO owner_accounts (id, username, password_salt, password_hash, iterations) "
                    "VALUES (1, ?, ?, ?, ?)",
                    (username, salt, digest, HASH_ITERATIONS),
                )
        except sqlite3.IntegrityError as exc:
            raise AuthenticationError("관리자 계정은 이미 생성되어 있습니다.") from exc
        self._logged_in = True

    def login(self, username: str, password: str) -> None:
        """Authenticate once per process; throttle repeated failures across restarts."""
        self._logged_in = False
        if not isinstance(username, str) or not isinstance(password, str):
            raise AuthenticationError("계정 또는 비밀번호가 올바르지 않습니다.")
        error = None
        with self._connect() as con:
            row = con.execute(
                "SELECT username, password_salt, password_hash, iterations, failed_attempts, locked_until "
                "FROM owner_accounts WHERE id = 1"
            ).fetchone()
            if row is None:
                error = "관리자 계정을 먼저 설정해야 합니다."
            elif row[5] > int(time.time()):
                error = "로그인 시도가 너무 많습니다. 1분 후 다시 시도하세요."
            else:
                is_valid = hmac.compare_digest(str(row[0]), username) and hmac.compare_digest(
                    hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), row[1], int(row[3])), row[2]
                )
                if is_valid:
                    con.execute("UPDATE owner_accounts SET failed_attempts=0, locked_until=0 WHERE id=1")
                else:
                    attempts = row[4] + 1
                    con.execute("UPDATE owner_accounts SET failed_attempts=?, locked_until=? WHERE id=1",
                                (attempts, int(time.time()) + LOCK_SECONDS if attempts >= MAX_FAILURES else 0))
                    error = "계정 또는 비밀번호가 올바르지 않습니다."
        if error:
            raise AuthenticationError(error)
        self._logged_in = True

    def logout(self) -> None:
        self._logged_in = False

    def require_permission(self, permission: str) -> None:
        if not self._logged_in or permission not in OWNER_PERMISSIONS:
            raise AuthenticationError("관리자 로그인이 필요한 작업입니다.")

    def role(self) -> str | None:
        return "owner" if self._logged_in else None

    def save_note(self, value: str) -> None:
        self.require_permission("notes:write")
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
        self.require_permission("notes:read")
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
