"""Stage 12: real persisted owner-controlled department operations."""
from pathlib import Path
import sqlite3
import subprocess
import sys

import pytest

from desktop.storage import AuthenticationError, LocalStore

OWNER = "owner_demo"
PASSWORD = "this-is-a-long-password-2026"


def new_store(path):
    store = LocalStore(path)
    store.setup_owner(OWNER, PASSWORD)
    return store


def test_department_create_edit_delete_reopen(tmp_path):
    path = tmp_path / "app.sqlite3"
    store = new_store(path)
    first = store.add_department("  시장조사부  ", "실제 시장 조사")
    second = store.add_department("개발부", "제품 개발")
    assert store.list_departments() == [
        {"id": first, "name": "시장조사부", "description": "실제 시장 조사"},
        {"id": second, "name": "개발부", "description": "제품 개발"},
    ]
    store.update_department(first, "시장·데이터분석부", "시장·경쟁 분석")
    store.logout()
    with pytest.raises(AuthenticationError):
        store.list_departments()
    restarted = LocalStore(path)
    with pytest.raises(AuthenticationError):
        restarted.update_department(first, "bad")
    restarted.login(OWNER, PASSWORD)
    assert restarted.list_departments()[0]["name"] == "시장·데이터분석부"
    restarted.delete_department(second)
    assert len(restarted.list_departments()) == 1
    assert restarted.list_departments()[0]["id"] == first


def test_no_permission_before_login_or_after_logout(tmp_path):
    store = LocalStore(tmp_path / "data.sqlite3")
    for operation in (lambda:store.list_departments(),
                      lambda:store.add_department("secret"),
                      lambda:store.update_department(1, "new"),
                      lambda:store.delete_department(1)):
        with pytest.raises(AuthenticationError):
            operation()
    store.setup_owner(OWNER, PASSWORD)
    store.add_department("연구")
    store.logout()
    with pytest.raises(AuthenticationError):
        store.add_department("조작 시도")


def test_duplicate_names_and_casefolding(tmp_path):
    store = new_store(tmp_path / "company.sqlite3")
    first = store.add_department("Research", "original")
    other = store.add_department("Content")
    for name in ("research", " RESEARCH "):
        with pytest.raises(ValueError, match="이미 존재"):
            store.add_department(name)
    with pytest.raises(ValueError, match="이미 존재"):
        store.update_department(other, "research")
    store.update_department(first, "RESEARCH", "same department, new spelling")
    assert len(store.list_departments()) == 2
    store.add_department("Straße")
    with pytest.raises(ValueError, match="이미 존재"):
        store.add_department("STRASSE")


@pytest.mark.parametrize("name, description", [
    ("", ""), ("  ", "text"), ("A" * 81, ""), ("valid", "X" * 501), (None, "invalid"),
])
def test_invalid_department_rejected_without_write(tmp_path, name, description):
    store = new_store(tmp_path / "company.sqlite3")
    with pytest.raises(ValueError):
        store.add_department(name, description)
    assert store.list_departments() == []


def test_invalid_ids_and_failed_updates_are_atomic(tmp_path):
    store = new_store(tmp_path / "company.sqlite3")
    identifier = store.add_department("원본", "설명")
    for bad_id in (-1, 0, True, "1", None):
        with pytest.raises(ValueError):
            store.delete_department(bad_id)
    with pytest.raises(ValueError):
        store.update_department(999, "없음")
    with pytest.raises(ValueError):
        store.delete_department(999)
    with pytest.raises(ValueError):
        store.update_department(identifier, " ", "변경되면 안 됨")
    assert store.list_departments() == [{"id": identifier, "name": "원본", "description": "설명"}]


def test_existing_notes_and_goals_survive_schema_upgrade(tmp_path):
    path = tmp_path / "before.sqlite3"
    store = new_store(path)
    store.save_note("important legacy note")
    store.save_company("오래된 회사", "옛 소개", "옛 목표")
    goal_id = store.add_goal("2026 목표")
    store.add_department("사업개발")
    store._init_schema()
    store.logout()
    reopened = LocalStore(path)
    reopened.login(OWNER, PASSWORD)
    assert reopened.read_note() == "important legacy note"
    assert reopened.read_company()["name"] == "오래된 회사"
    assert reopened.list_goals()[0]["id"] == goal_id
    assert reopened.list_departments()[0]["name"] == "사업개발"


def test_sql_injection_text_treated_as_literal(tmp_path):
    store = new_store(tmp_path / "department.sqlite3")
    payload = "finance'); DROP TABLE owner_accounts; --"
    identifier = store.add_department(payload, "safe value")
    assert store.list_departments()[0]["name"] == payload
    store.update_department(identifier, "새 부서", payload)
    with sqlite3.connect(store.path) as con:
        assert con.execute("SELECT COUNT(*) FROM owner_accounts").fetchone()[0] == 1


def test_separate_process_round_trip(tmp_path):
    path = tmp_path / "cross-process.sqlite3"
    script = """from desktop.storage import LocalStore
import sys
s=LocalStore(sys.argv[1]);s.setup_owner('owner_demo','this-is-a-long-password-2026');s.add_department('연구개발','실사 확인')
"""
    subprocess.run([sys.executable, "-c", script, str(path)], check=True, timeout=20)
    store = LocalStore(path)
    store.login(OWNER, PASSWORD)
    assert store.list_departments()[0]["description"] == "실사 확인"
