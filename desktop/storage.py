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
DESIGNATION_KINDS = frozenset({"rank", "job", "role"})  # Rank / job / responsibility role; NOT RBAC permissions.
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
            connection.execute("PRAGMA foreign_keys = ON")
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

            con.execute("""
                CREATE TABLE IF NOT EXISTS company_profile (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    name TEXT NOT NULL,
                    description TEXT NOT NULL DEFAULT '',
                    mission TEXT NOT NULL DEFAULT '',
                    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
            """)
            con.execute("""
                CREATE TABLE IF NOT EXISTS company_goals (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    detail TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL DEFAULT 'planned',
                    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Stage 12: stable department identifiers; future staff can reference these.
            con.execute("""
                CREATE TABLE IF NOT EXISTS company_departments (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL COLLATE NOCASE UNIQUE,
                    description TEXT NOT NULL DEFAULT '',
                    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Stage 13: job/position taxonomy with stable IDs for future employee assignment.
            # Role labels here do not grant any operating-system or owner privileges.
            con.execute("""
                CREATE TABLE IF NOT EXISTS company_designations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    kind TEXT NOT NULL CHECK(kind IN ('rank', 'job', 'role')),
                    name TEXT NOT NULL COLLATE NOCASE,
                    description TEXT NOT NULL DEFAULT '',
                    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE (kind, name)
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

    @staticmethod
    def _validated_text(value: str, field: str, limit: int, *, required: bool = False) -> str:
        if not isinstance(value, str):
            raise ValueError(f"{field} 항목은 문자열이어야 합니다.")
        cleaned = value.strip()
        if len(cleaned) > limit or (required and not cleaned):
            raise ValueError(f"{field} 항목은 {'1~' if required else '0~'}{limit}자여야 합니다.")
        return cleaned

    def read_company(self) -> dict[str, str]:
        """Return the persisted company profile or safe empty first-run defaults."""
        self.require_permission("company:manage")
        with self._connect() as con:
            row = con.execute("SELECT name, description, mission FROM company_profile WHERE id=1").fetchone()
        return dict(zip(("name", "description", "mission"), row)) if row else {
            "name": "AI Autonomous Company", "description": "", "mission": ""
        }

    def save_company(self, name: str, description: str, mission: str) -> None:
        """Write only after an authenticated owner confirms the changes."""
        self.require_permission("company:manage")
        fields = (
            self._validated_text(name, "회사명", 80, required=True),
            self._validated_text(description, "회사 소개", 500),
            self._validated_text(mission, "운영 방향", 500),
        )
        with self._connect() as con:
            con.execute("""
                INSERT INTO company_profile (id, name, description, mission) VALUES (1, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET name=excluded.name,
                    description=excluded.description, mission=excluded.mission,
                    updated_at=CURRENT_TIMESTAMP
            """, fields)

    def list_goals(self) -> list[dict[str, object]]:
        self.require_permission("company:manage")
        with self._connect() as con:
            rows = con.execute("SELECT id, title, detail, status FROM company_goals ORDER BY id").fetchall()
        return [dict(zip(("id", "title", "detail", "status"), row)) for row in rows]

    def _require_goal_id(self, goal_id: int) -> None:
        if not isinstance(goal_id, int) or isinstance(goal_id, bool) or goal_id < 1:
            raise ValueError("올바른 목표 ID가 필요합니다.")

    def add_goal(self, title: str, detail: str = "") -> int:
        self.require_permission("company:manage")
        validated = (self._validated_text(title, "목표명", 120, required=True),
                     self._validated_text(detail, "목표 설명", 500))
        with self._connect() as con:
            cursor = con.execute("INSERT INTO company_goals (title, detail) VALUES (?, ?)", validated)
            return int(cursor.lastrowid)

    def update_goal(self, goal_id: int, title: str, detail: str, status: str) -> None:
        self.require_permission("company:manage")
        self._require_goal_id(goal_id)
        if status not in {"planned", "active", "done", "paused"}:
            raise ValueError("올바르지 않은 목표 상태입니다.")
        values = (self._validated_text(title, "목표명", 120, required=True),
                  self._validated_text(detail, "목표 설명", 500), status, goal_id)
        with self._connect() as con:
            cursor = con.execute("""
                UPDATE company_goals SET title=?, detail=?, status=?, updated_at=CURRENT_TIMESTAMP
                WHERE id=?
            """, values)
            if cursor.rowcount != 1:
                raise ValueError("선택한 목표를 찾을 수 없습니다.")

    def delete_goal(self, goal_id: int) -> None:
        self.require_permission("company:manage")
        self._require_goal_id(goal_id)
        with self._connect() as con:
            cursor = con.execute("DELETE FROM company_goals WHERE id=?", (goal_id,))
            if cursor.rowcount != 1:
                raise ValueError("선택한 목표를 찾을 수 없습니다.")

    def list_departments(self) -> list[dict[str, object]]:
        """Departments are local company structure, not running AI employees."""
        self.require_permission("company:manage")
        with self._connect() as con:
            rows = con.execute(
                "SELECT id, name, description FROM company_departments ORDER BY id"
            ).fetchall()
        return [dict(zip(("id", "name", "description"), row)) for row in rows]

    @staticmethod
    def _department_id(department_id: int) -> None:
        if isinstance(department_id, bool) or not isinstance(department_id, int) or department_id < 1:
            raise ValueError("올바른 부서 번호를 선택하세요.")

    @staticmethod
    def _validated_department(name: str, description: str) -> tuple[str, str]:
        return (
            LocalStore._validated_text(name, "부서명", 80, required=True),
            LocalStore._validated_text(description, "부서 설명", 500),
        )

    @staticmethod
    def _ensure_unique_department(con: sqlite3.Connection, name: str, except_id: int | None = None) -> None:
        # casefold also handles non-ASCII names that SQLite's NOCASE cannot.
        rows = con.execute("SELECT id, name FROM company_departments").fetchall()
        if any(row[1].casefold() == name.casefold() and row[0] != except_id for row in rows):
            raise ValueError("같은 이름의 부서가 이미 존재합니다.")

    def add_department(self, name: str, description: str = "") -> int:
        self.require_permission("company:manage")
        validated = self._validated_department(name, description)
        with self._connect() as con:
            self._ensure_unique_department(con, validated[0])
            try:
                cursor = con.execute(
                    "INSERT INTO company_departments (name, description) VALUES (?, ?)", validated
                )
            except sqlite3.IntegrityError as exc:
                raise ValueError("같은 이름의 부서가 이미 존재합니다.") from exc
            return int(cursor.lastrowid)

    def update_department(self, department_id: int, name: str, description: str = "") -> None:
        self.require_permission("company:manage")
        self._department_id(department_id)
        validated = self._validated_department(name, description)
        with self._connect() as con:
            self._ensure_unique_department(con, validated[0], except_id=department_id)
            try:
                cursor = con.execute(
                    "UPDATE company_departments SET name=?, description=?, "
                    "updated_at=CURRENT_TIMESTAMP WHERE id=?", (*validated, department_id)
                )
            except sqlite3.IntegrityError as exc:
                raise ValueError("같은 이름의 부서가 이미 존재합니다.") from exc
            if cursor.rowcount != 1:
                raise ValueError("선택한 부서를 찾을 수 없습니다.")

    def delete_department(self, department_id: int) -> None:
        self.require_permission("company:manage")
        self._department_id(department_id)
        with self._connect() as con:
            try:
                cursor = con.execute("DELETE FROM company_departments WHERE id=?", (department_id,))
            except sqlite3.IntegrityError as exc:
                raise ValueError("연결된 직원이나 데이터가 있어 부서를 삭제할 수 없습니다.") from exc
            if cursor.rowcount != 1:
                raise ValueError("선택한 부서를 찾을 수 없습니다.")

    # Stage 13. Catalog metadata only; account/agent permissions remain untouched.
    @staticmethod
    def _validate_designation_kind(kind: str) -> str:
        if not isinstance(kind, str) or kind not in DESIGNATION_KINDS:
            raise ValueError("직급·직무·역할 유형 중 하나를 선택하세요.")
        return kind

    @staticmethod
    def _designation_id(designation_id: int) -> None:
        if isinstance(designation_id, bool) or not isinstance(designation_id, int) or designation_id < 1:
            raise ValueError("올바른 직급·직무·역할 번호가 필요합니다.")

    @staticmethod
    def _unique_designation(con: sqlite3.Connection, kind: str, name: str,
                            except_id: int | None = None) -> None:
        rows = con.execute("SELECT id, name FROM company_designations WHERE kind=?", (kind,)).fetchall()
        if any(existing_name.casefold() == name.casefold() and identifier != except_id
               for identifier, existing_name in rows):
            raise ValueError("같은 유형에 동일한 이름이 이미 존재합니다.")

    def list_designations(self, kind: str | None = None) -> list[dict[str, object]]:
        self.require_permission("company:manage")
        if kind is not None:
            self._validate_designation_kind(kind)
        with self._connect() as con:
            if kind is None:
                rows = con.execute(
                    "SELECT id, kind, name, description FROM company_designations ORDER BY id"
                ).fetchall()
            else:
                rows = con.execute(
                    "SELECT id, kind, name, description FROM company_designations WHERE kind=? ORDER BY id",
                    (kind,),
                ).fetchall()
        return [dict(zip(("id", "kind", "name", "description"), row)) for row in rows]

    def add_designation(self, kind: str, name: str, description: str = "") -> int:
        self.require_permission("company:manage")
        kind = self._validate_designation_kind(kind)
        name = self._validated_text(name, "명칭", 80, required=True)
        description = self._validated_text(description, "설명", 500)
        with self._connect() as con:
            self._unique_designation(con, kind, name)
            try:
                cursor = con.execute(
                    "INSERT INTO company_designations (kind, name, description) VALUES (?, ?, ?)",
                    (kind, name, description),
                )
            except sqlite3.IntegrityError as exc:
                raise ValueError("같은 유형에 동일한 이름이 이미 존재합니다.") from exc
            return int(cursor.lastrowid)

    def update_designation(self, designation_id: int, kind: str, name: str,
                           description: str = "") -> None:
        self.require_permission("company:manage")
        self._designation_id(designation_id)
        kind = self._validate_designation_kind(kind)
        name = self._validated_text(name, "명칭", 80, required=True)
        description = self._validated_text(description, "설명", 500)
        with self._connect() as con:
            self._unique_designation(con, kind, name, except_id=designation_id)
            try:
                cursor = con.execute(
                    "UPDATE company_designations SET kind=?, name=?, description=?, "
                    "updated_at=CURRENT_TIMESTAMP WHERE id=?",
                    (kind, name, description, designation_id),
                )
            except sqlite3.IntegrityError as exc:
                raise ValueError("같은 유형에 동일한 이름이 이미 존재합니다.") from exc
            if cursor.rowcount != 1:
                raise ValueError("선택한 직급·직무·역할을 찾을 수 없습니다.")

    def delete_designation(self, designation_id: int) -> None:
        self.require_permission("company:manage")
        self._designation_id(designation_id)
        with self._connect() as con:
            try:
                cursor = con.execute("DELETE FROM company_designations WHERE id=?", (designation_id,))
            except sqlite3.IntegrityError as exc:
                raise ValueError("사용 중인 직급·직무·역할은 삭제할 수 없습니다.") from exc
            if cursor.rowcount != 1:
                raise ValueError("선택한 직급·직무·역할을 찾을 수 없습니다.")

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
