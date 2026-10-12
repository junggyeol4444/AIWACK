"""Stage 13: owner-only rank, job and responsibility catalog, not RBAC roles."""
import sqlite3
import subprocess
import sys

import pytest

from desktop.storage import AuthenticationError, LocalStore

USER = "owner_test"
PASSWORD = "stage-thirteen-long-password-2026"


def logged_in(path):
    store = LocalStore(path)
    store.setup_owner(USER, PASSWORD)
    return store


def test_crud_three_types_and_reopen(tmp_path):
    path = tmp_path / "app.sqlite3"
    s = logged_in(path)
    rank = s.add_designation("rank", "대표", "회사 직급")
    job = s.add_designation("job", "시장조사", "시장 자료 조사")
    role = s.add_designation("role", "검수", "완료 승인 책임")
    s.update_designation(role, "role", "품질검수", "일의 품질 검증")
    s.logout()
    with pytest.raises(AuthenticationError):
        s.list_designations()
    new = LocalStore(path)
    with pytest.raises(AuthenticationError):
        new.delete_designation(rank)
    new.login(USER, PASSWORD)
    assert [x["id"] for x in new.list_designations()] == [rank, job, role]
    assert [x["name"] for x in new.list_designations()] == ["대표", "시장조사", "품질검수"]
    assert new.list_designations("role")[0]["description"] == "일의 품질 검증"
    new.delete_designation(job)
    assert len(new.list_designations()) == 2


def test_same_name_allowed_for_different_kind(tmp_path):
    s = logged_in(tmp_path / "app.sqlite3")
    for kind in ("rank", "job", "role"):
        s.add_designation(kind, "Coordinator")
    assert len(s.list_designations()) == 3
    assert len(s.list_designations("job")) == 1


def test_duplicate_within_kind_unicode_casefold(tmp_path):
    s = logged_in(tmp_path / "app.sqlite3")
    first = s.add_designation("rank", "Straße")
    second = s.add_designation("rank", "일반")
    with pytest.raises(ValueError, match="이미 존재"):
        s.add_designation("rank", "STRASSE")
    with pytest.raises(ValueError, match="이미 존재"):
        s.update_designation(second, "rank", "STRASSE")
    s.update_designation(first, "rank", "STRASSE")
    assert len(s.list_designations()) == 2
    assert s.list_designations()[0]["name"] == "STRASSE"


@pytest.mark.parametrize("kind,name,description", [
    ("user", "manager", ""), ("admin", "owner", ""), ("role", " ", ""),
    ("rank", "A" * 81, ""), ("job", "valid", "x" * 501),
    (None, "valid", ""), ("role", None, ""), ("rank", "valid", None),
])
def test_invalid_fields_are_rejected_without_insert(tmp_path, kind, name, description):
    s = logged_in(tmp_path / "db.sqlite3")
    with pytest.raises(ValueError):
        s.add_designation(kind, name, description)
    assert s.list_designations() == []


@pytest.mark.parametrize("invalid", [-1, 0, True, "1", None, 1.5])
def test_invalid_ids(tmp_path, invalid):
    s = logged_in(tmp_path / "db.sqlite3")
    with pytest.raises(ValueError):
        s.delete_designation(invalid)
    with pytest.raises(ValueError):
        s.update_designation(invalid, "rank", "대표")


def test_failed_update_does_not_mutate(tmp_path):
    s = logged_in(tmp_path / "db.sqlite3")
    identifier = s.add_designation("rank", "대리", "초기")
    with pytest.raises(ValueError):
        s.update_designation(identifier, "superuser", "권한 상승")
    with pytest.raises(ValueError):
        s.update_designation(999, "rank", "없는 항목")
    with pytest.raises(ValueError):
        s.delete_designation(999)
    assert s.list_designations() == [{"id": identifier, "kind": "rank", "name": "대리", "description": "초기"}]


def test_owner_auth_required_for_every_operation(tmp_path):
    s = LocalStore(tmp_path / "db.sqlite3")
    operations = [lambda: s.list_designations(), lambda: s.list_designations("rank"),
                  lambda: s.add_designation("job", "조사"),
                  lambda: s.update_designation(1, "role", "검수"),
                  lambda: s.delete_designation(1)]
    for op in operations:
        with pytest.raises(AuthenticationError):
            op()
    s.setup_owner(USER, PASSWORD)
    s.add_designation("rank", "팀장")
    s.logout()
    for op in operations:
        with pytest.raises(AuthenticationError):
            op()


def test_old_data_and_roles_preserved_without_privilege_grant(tmp_path):
    path = tmp_path / "app.sqlite3"
    s = logged_in(path)
    s.save_note("do not lose me")
    s.save_company("회사X", "설명", "목표")
    g = s.add_goal("고객 지원")
    d = s.add_department("개발부")
    original_permissions = s.role()
    s.add_designation("role", "expenses:approve", "Catalog string does not authorize any action")
    s.add_designation("rank", "팀장")
    s._init_schema()  # idempotent schema migration, no data lost
    s.logout()
    new = LocalStore(path)
    new.login(USER, PASSWORD)
    assert new.read_note() == "do not lose me"
    assert new.read_company()["name"] == "회사X"
    assert new.list_goals()[0]["id"] == g
    assert new.list_departments()[0]["id"] == d
    assert new.role() == original_permissions == "owner"
    assert len(new.list_designations()) == 2
    with pytest.raises(AuthenticationError):
        new.require_permission("superuser:become")
    with sqlite3.connect(path) as con:
        assert con.execute("SELECT COUNT(*) FROM owner_accounts").fetchone()[0] == 1


def test_sql_payload_is_only_a_string(tmp_path):
    path = tmp_path / "app.sqlite3"
    s = logged_in(path)
    text = "job'); DROP TABLE owner_accounts; --"
    item = s.add_designation("job", text)
    assert s.list_designations()[0]["name"] == text
    s.update_designation(item, "role", "safe", text)
    assert s.list_designations()[0]["description"] == text
    assert s.has_owner()


def test_across_independent_processes(tmp_path):
    path = tmp_path / "app.sqlite3"
    s = logged_in(path)
    s.add_designation("role", "프로젝트 담당", "자율 AI 미연결")
    reader = '''from desktop.storage import LocalStore
import sys
s=LocalStore(sys.argv[1]); s.login("owner_test", "stage-thirteen-long-password-2026")
print(s.list_designations("role")[0]["name"])
'''
    p = subprocess.run([sys.executable, "-c", reader, str(path)], check=True,
                       capture_output=True, text=True, timeout=20)
    assert p.stdout.strip() == "프로젝트 담당"
