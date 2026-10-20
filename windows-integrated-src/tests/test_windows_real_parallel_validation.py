"""Regression for the Windows real-GGUF validator's DB lifetime and overlap proof."""
from __future__ import annotations

from pathlib import Path
import sqlite3
import pytest

import sys
# The validator lives at repository root; desktop must stay the native app.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from validation.windows_real_parallel_company_e2e import (
    verify_sqlite_integrity, actual_overlap_seconds,
)


def test_integrity_check_closes_database_before_file_cleanup(tmp_path):
    db = tmp_path / 'company.sqlite3'
    con = sqlite3.connect(db)
    try:
        con.execute('CREATE TABLE test_data (id INTEGER PRIMARY KEY)')
        con.execute('INSERT INTO test_data VALUES (1)')
        con.commit()
    finally:
        con.close()
    verify_sqlite_integrity(db)
    db.unlink()
    assert not db.exists()


def test_integrity_check_refuses_invalid_foreign_key_and_closes_connection(tmp_path):
    db = tmp_path / 'invalid_foreign_key.sqlite3'
    con = sqlite3.connect(db)
    try:
        con.execute('PRAGMA foreign_keys = OFF')
        con.execute('CREATE TABLE parent (id INTEGER PRIMARY KEY)')
        con.execute('CREATE TABLE child (parent_id INTEGER REFERENCES parent(id))')
        con.execute('INSERT INTO child VALUES (99)')
        con.commit()
    finally:
        con.close()
    with pytest.raises(AssertionError, match='foreign-key'):
        verify_sqlite_integrity(db)
    db.unlink()
    assert not db.exists()


def test_inference_overlap_requires_actual_intersection():
    assert actual_overlap_seconds([(1.0, 3.0), (2.0, 4.0)]) == 1.0
    assert actual_overlap_seconds([(1.0, 2.0), (2.0, 3.0)]) == 0.0
    assert actual_overlap_seconds([(1.0, 2.0), (3.0, 4.0)]) < 0


@pytest.mark.parametrize('invalid', [[], [(1.0, 2.0)], [(2.0, 1.0), (1.0, 3.0)]])
def test_inference_overlap_refuses_bad_or_missing_measurements(invalid):
    with pytest.raises(AssertionError):
        actual_overlap_seconds(invalid)
