"""Desktop storage checks; full Tk GUI exercised by scripts/desktop_gui_smoke.py."""
from pathlib import Path
import csv
import os
import subprocess
import sys

import pytest
from desktop.storage import LocalStore, user_data_dir


def test_offline_storage_save_reopen_and_health(tmp_path):
    location = tmp_path / "appdata" / "aiwack.sqlite3"
    db = LocalStore(location)
    db.save_note("first note")
    db.save_note("second note")
    assert LocalStore(location).read_note() == "second note"
    assert LocalStore(location).health()["status"] == "ok"


def test_user_data_directory_can_be_overridden(tmp_path, monkeypatch):
    monkeypatch.setenv("AIWACK_DATA_DIR", str(tmp_path / "subdir"))
    assert user_data_dir() == (tmp_path / "subdir").resolve()
    assert LocalStore().path.parent == (tmp_path / "subdir").resolve()


@pytest.mark.parametrize("note", ["", "   ", "a" * 121])
def test_validation_rejects_bad_note(tmp_path, note):
    with pytest.raises(ValueError):
        LocalStore(tmp_path / "file.sqlite3").save_note(note)


def test_data_saved_across_separate_python_processes(tmp_path):
    db = tmp_path / "persist.sqlite3"
    env = os.environ.copy()
    env["AIWACK_DATA_DIR"] = str(tmp_path)
    result = subprocess.run([sys.executable, "-m", "desktop.entry", "--self-test"], env=env, timeout=15)
    assert result.returncode == 0
    writer = 'from desktop.storage import LocalStore; import sys; LocalStore(sys.argv[1]).save_note("process-one")'
    reader = 'from desktop.storage import LocalStore; import sys; print(LocalStore(sys.argv[1]).read_note())'
    subprocess.run([sys.executable, "-c", writer, str(db)], check=True, timeout=15)
    r = subprocess.run([sys.executable, "-c", reader, str(db)], capture_output=True, text=True, check=True, timeout=15)
    assert r.stdout.strip() == "process-one"
