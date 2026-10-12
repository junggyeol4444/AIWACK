"""Stage 14: persistent draft employee metadata, not agent execution."""
import sqlite3
import pytest
from desktop.storage import LocalStore, AuthenticationError

USER = "agent_owner"
PASS = "a-long-local-password-2026"

def owner(path):
    db = LocalStore(path)
    db.setup_owner(USER, PASS)
    return db

def links(db):
    return (db.add_department("연구개발부", "연구를 담당"),
            db.add_designation("rank", "팀장"),
            db.add_designation("job", "분석"),
            db.add_designation("role", "검수"))

def test_new_schema_empty_and_reinitialization_safe(tmp_path):
    p = tmp_path / "aiwack.sqlite3"
    db = owner(p)
    assert db.list_employee_records() == []
    db.save_company("테스트 회사", "기존 회사정보", "기존 목표")
    db.save_note("기존 메모")
    for _ in range(3):
        new = LocalStore(p)
        new.login(USER, PASS)
        assert new.list_employee_records() == []
        assert new.read_company()["name"] == "테스트 회사"
        assert new.read_note() == "기존 메모"

def test_draft_references_and_survives_restart(tmp_path):
    p = tmp_path / "aiwack.sqlite3"
    db = owner(p)
    dept, rank, job, role = links(db)
    identifier = db.add_employee_draft("agent_001", "연구 담당", "초안",
                 department_id=dept, rank_id=rank, job_id=job, role_id=role)
    db.logout()
    db = LocalStore(p)
    with pytest.raises(AuthenticationError):
        db.list_employee_records()
    db.login(USER, PASS)
    row = db.read_employee_record(identifier)
    assert row == {"id": identifier, "employee_key": "agent_001", "display_name": "연구 담당",
                   "description": "초안", "department_id": dept, "rank_id": rank, "job_id": job,
                   "role_id": role, "lifecycle": "draft"}
    assert db.list_employee_records() == [row]

def test_optional_references_are_none(tmp_path):
    db = owner(tmp_path / "db.sqlite3")
    row = db.read_employee_record(db.add_employee_draft("draft_123", "미배치 직원"))
    assert all(row[field] is None for field in ("department_id", "rank_id", "job_id", "role_id"))
    assert row["lifecycle"] == "draft"

@pytest.mark.parametrize("key", ["", "ab", "white space", "한글아이디", "x" * 65, "_abc", "a.b", " bad "])
def test_bad_employee_keys(tmp_path, key):
    db = owner(tmp_path / "db.sqlite3")
    with pytest.raises(ValueError):
        db.add_employee_draft(key, "테스트")
    assert db.list_employee_records() == []

@pytest.mark.parametrize("name", ["", " ", "n"*81, None])
def test_bad_names(tmp_path, name):
    db = owner(tmp_path / "db.sqlite3")
    with pytest.raises(ValueError):
        db.add_employee_draft("good_key", name)

def test_key_uniqueness_case_insensitive(tmp_path):
    db = owner(tmp_path / "db.sqlite3")
    db.add_employee_draft("Agent01", "직원1")
    with pytest.raises(ValueError):
        db.add_employee_draft("agent01", "직원2")
    assert len(db.list_employee_records()) == 1

@pytest.mark.parametrize("bad_id", [-1, 0, True, "1", 1.3])
def test_bad_reference_types(tmp_path, bad_id):
    db = owner(tmp_path / "db.sqlite3")
    with pytest.raises(ValueError):
        db.add_employee_draft("new_employee", "직원", department_id=bad_id)

def test_unknown_references_fail_atomically(tmp_path):
    db = owner(tmp_path / "db.sqlite3")
    with pytest.raises(ValueError):
        db.add_employee_draft("bad_dept", "직원", department_id=99)
    with pytest.raises(ValueError):
        db.add_employee_draft("bad_role", "직원", role_id=99)
    assert db.list_employee_records() == []

@pytest.mark.parametrize("wrong_field", ["rank_id", "job_id", "role_id"])
def test_wrong_designation_kind(tmp_path, wrong_field):
    db = owner(tmp_path / "db.sqlite3")
    _, rank, job, role = links(db)
    wrong = role if wrong_field != "role_id" else rank
    with pytest.raises(ValueError):
        db.add_employee_draft("invalid_kind", "직원", **{wrong_field: wrong})
    assert db.list_employee_records() == []

def test_direct_sql_trigger_and_lifecycle_checks(tmp_path):
    db = owner(tmp_path / "db.sqlite3")
    _, rank, job, role = links(db)
    with pytest.raises(sqlite3.IntegrityError):
        with db._connect() as con:
            con.execute("INSERT INTO ai_employee_profiles(employee_key,display_name,rank_id) VALUES (?,?,?)",
                        ("direct1", "직원", job))
    with pytest.raises(sqlite3.IntegrityError):
        with db._connect() as con:
            con.execute("INSERT INTO ai_employee_profiles(employee_key,display_name,lifecycle) VALUES (?,?,?)",
                        ("direct2", "직원", "active"))
    identifier = db.add_employee_draft("direct3", "직원", rank_id=rank)
    with pytest.raises(sqlite3.IntegrityError):
        with db._connect() as con:
            con.execute("UPDATE ai_employee_profiles SET role_id=? WHERE id=?", (job, identifier))
    assert db.read_employee_record(identifier)["role_id"] is None

def test_references_block_deletion_and_kind_change(tmp_path):
    db = owner(tmp_path / "db.sqlite3")
    dept, rank, job, role = links(db)
    db.add_employee_draft("agent_linked", "직원", department_id=dept,
                          rank_id=rank, job_id=job, role_id=role)
    with pytest.raises(ValueError, match="연결된"):
        db.delete_department(dept)
    with pytest.raises(ValueError, match="사용 중"):
        db.delete_designation(role)
    with pytest.raises(ValueError):
        db.update_designation(rank, "job", "팀장")
    assert db.list_departments()[0]["id"] == dept
    assert db.list_designations("rank")[0]["id"] == rank

def test_missing_and_unauthorized_access(tmp_path):
    db = owner(tmp_path / "db.sqlite3")
    with pytest.raises(ValueError):
        db.read_employee_record(100)
    for invalid in (0, True, "1"):
        with pytest.raises(ValueError):
            db.read_employee_record(invalid)
    db.logout()
    with pytest.raises(AuthenticationError):
        db.add_employee_draft("no_access", "직원")
    with pytest.raises(AuthenticationError):
        db.read_employee_record(1)
    with pytest.raises(AuthenticationError):
        db.list_employee_records()
