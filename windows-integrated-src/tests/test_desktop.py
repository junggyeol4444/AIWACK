"""Real SQLite owner tests, no mocked authentication or in-memory DB."""
import os
from pathlib import Path
import sqlite3
import subprocess
import sys

import pytest
from desktop.storage import AuthenticationError, LocalStore, user_data_dir, MAX_FAILURES, LOCK_SECONDS

TEST_USER = "my_owner"
TEST_PASSWORD = "a-secure-passphrase-2026"


def owner(db: LocalStore) -> LocalStore:
    db.setup_owner(TEST_USER, TEST_PASSWORD)
    return db


def test_first_launch_requires_owner_and_rejects_unapproved_access(tmp_path):
    db = LocalStore(tmp_path / "appdata" / "aiwack.sqlite3")
    assert not db.has_owner()
    assert not db.is_authenticated
    assert db.role() is None
    with pytest.raises(AuthenticationError):
        db.read_note()
    with pytest.raises(AuthenticationError):
        db.save_note("unapproved")
    with pytest.raises(AuthenticationError):
        db.require_permission("expenses:approve")
    owner(db)
    assert db.has_owner()
    assert db.role() == "owner"
    db.require_permission("company:manage")
    db.require_permission("agents:manage")
    db.require_permission("expenses:approve")
    with pytest.raises(AuthenticationError):
        db.require_permission("imaginary:unknown")


def test_reopen_requires_login_wrong_password_rejected_and_data_preserved(tmp_path):
    path = tmp_path / "reopen.sqlite3"
    db = owner(LocalStore(path))
    db.save_note("first note")
    db.save_note("second note")
    db.logout()
    with pytest.raises(AuthenticationError):
        db.save_note("cannot-change")
    reopened = LocalStore(path)
    assert reopened.has_owner()
    with pytest.raises(AuthenticationError):
        reopened.read_note()
    with pytest.raises(AuthenticationError):
        reopened.login(TEST_USER, "wrong_password")
    with pytest.raises(AuthenticationError):
        reopened.login("wrong_user", TEST_PASSWORD)
    reopened.login(TEST_USER, TEST_PASSWORD)
    assert reopened.read_note() == "second note"
    assert reopened.health()["status"] == "ok"
    reopened.logout()
    assert reopened.role() is None
    with pytest.raises(AuthenticationError):
        reopened.read_note()


def test_no_second_owner_can_be_created(tmp_path):
    db = owner(LocalStore(tmp_path / "local.sqlite3"))
    with pytest.raises(AuthenticationError):
        db.setup_owner("new_admin", "another-long-password-2026")
    db.logout()
    db.login(TEST_USER, TEST_PASSWORD)


@pytest.mark.parametrize("username,password", [
    ("ab", TEST_PASSWORD),
    ("bad space", TEST_PASSWORD),
    ("good_admin", "short"),
    ("good_admin", " " * 14),
    ("good_admin", "z" * 1025),
])
def test_bad_credentials_not_saved(tmp_path, username, password):
    db = LocalStore(tmp_path / "local.sqlite3")
    with pytest.raises(ValueError):
        db.setup_owner(username, password)
    assert not db.has_owner()


@pytest.mark.parametrize("note", ["", "   ", "a" * 121])
def test_validation_rejects_bad_note_when_logged_in(tmp_path, note):
    db = owner(LocalStore(tmp_path / "file.sqlite3"))
    with pytest.raises(ValueError):
        db.save_note(note)


def test_password_salted_and_not_stored_as_plaintext(tmp_path):
    path = tmp_path / "db.sqlite3"
    db = owner(LocalStore(path))
    con = sqlite3.connect(path)
    try:
        salt, digest, iterations = con.execute("SELECT password_salt,password_hash,iterations FROM owner_accounts").fetchone()
    finally:
        con.close()
    assert len(salt) >= 16
    assert len(digest) == 32
    assert TEST_PASSWORD.encode() not in path.read_bytes()
    assert iterations >= 300_000
    assert db.role() == "owner"


def test_failed_login_lockout_persists_across_instances(tmp_path, monkeypatch):
    path = tmp_path / "lock.sqlite3"
    db = owner(LocalStore(path))
    db.logout()
    monkeypatch.setattr("desktop.storage.time.time", lambda: 200000)
    for _ in range(MAX_FAILURES):
        with pytest.raises(AuthenticationError):
            db.login(TEST_USER, "bad-password")
    with pytest.raises(AuthenticationError, match="1분"):
        LocalStore(path).login(TEST_USER, TEST_PASSWORD)
    monkeypatch.setattr("desktop.storage.time.time", lambda: 200000 + LOCK_SECONDS + 1)
    LocalStore(path).login(TEST_USER, TEST_PASSWORD)


def test_existing_note_and_table_not_deleted_on_owner_setup(tmp_path):
    path = tmp_path / "legacy.sqlite3"
    with sqlite3.connect(path) as con:
        con.execute("CREATE TABLE system_metadata (id INTEGER PRIMARY KEY, key VARCHAR(120) NOT NULL UNIQUE, value VARCHAR(1000) NOT NULL, created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP)")
        con.execute("INSERT INTO system_metadata(key,value) VALUES ('local_manual_test','old-user-note')")
    db = LocalStore(path)
    owner(db)
    assert db.read_note() == "old-user-note"


def test_user_data_directory_can_be_overridden(tmp_path, monkeypatch):
    monkeypatch.setenv("AIWACK_DATA_DIR", str(tmp_path / "subdir"))
    assert user_data_dir() == (tmp_path / "subdir").resolve()
    assert LocalStore().path.parent == (tmp_path / "subdir").resolve()


def test_data_saved_across_separate_python_processes(tmp_path):
    db = tmp_path / "persist.sqlite3"
    env = os.environ.copy()
    env["AIWACK_DATA_DIR"] = str(tmp_path)
    result = subprocess.run([sys.executable, "-m", "desktop.entry", "--self-test"], env=env, timeout=20)
    assert result.returncode == 0
    writer = 'from desktop.storage import LocalStore; import sys; s=LocalStore(sys.argv[1]); s.setup_owner("my_owner","a-secure-passphrase-2026"); s.save_note("process-one")'
    reader = 'from desktop.storage import LocalStore; import sys; s=LocalStore(sys.argv[1]); s.login("my_owner","a-secure-passphrase-2026"); print(s.read_note())'
    subprocess.run([sys.executable, "-c", writer, str(db)], check=True, timeout=20)
    r = subprocess.run([sys.executable, "-c", reader, str(db)], capture_output=True, text=True, check=True, timeout=20)
    assert r.stdout.strip() == "process-one"
