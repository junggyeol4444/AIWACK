"""Stage 15 employee *profile* management; does not run agent models."""
import sqlite3
import subprocess
import sys
import pytest

from desktop.storage import AuthenticationError, LocalStore


def owner(tmp_path):
    db = LocalStore(tmp_path / "employee.sqlite3")
    db.setup_owner("stage15_owner", "strong-password-2026-test")
    return db


def linked(db):
    return {
        "department_id": db.add_department("전략기획부"),
        "rank_id": db.add_designation("rank", "부서장"),
        "job_id": db.add_designation("job", "기획"),
        "role_id": db.add_designation("role", "기획 검수"),
    }


def test_profile_crud_inactivation_and_restart(tmp_path):
    db = owner(tmp_path)
    references = linked(db)
    employee = db.add_employee_draft("planner001", "기획 AI", "초안", **references)
    db.update_employee_record(employee, "수정된 기획 AI", "검토 대기", **references)
    assert db.read_employee_record(employee)["display_name"] == "수정된 기획 AI"
    assert db.read_employee_record(employee)["employee_key"] == "planner001"
    db.set_employee_inactive(employee)
    db.logout()
    reopened = LocalStore(db.path)
    with pytest.raises(AuthenticationError):
        reopened.read_employee_record(employee)
    reopened.login("stage15_owner", "strong-password-2026-test")
    record = reopened.read_employee_record(employee)
    assert record["lifecycle"] == "inactive"
    assert record["department_id"] == references["department_id"]
    assert record["description"] == "검토 대기"
    reopened.restore_employee_draft(employee)
    assert reopened.read_employee_record(employee)["lifecycle"] == "draft"
    assert reopened.read_employee_record(employee)["employee_key"] == "planner001"


def test_update_can_unassign_links(tmp_path):
    db = owner(tmp_path)
    refs = linked(db)
    employee = db.add_employee_draft("creator001", "창작 AI", **refs)
    db.update_employee_record(employee, "창작 AI 개편")
    saved = db.read_employee_record(employee)
    assert saved["display_name"] == "창작 AI 개편"
    assert all(saved[col] is None for col in refs)
    db.delete_department(refs["department_id"])
    for key in ["rank_id", "job_id", "role_id"]:
        db.delete_designation(refs[key])


@pytest.mark.parametrize("invalid", [0, -1, True, "1", 2.5])
def test_invalid_employee_ids_rejected(tmp_path, invalid):
    db = owner(tmp_path)
    with pytest.raises(ValueError):
        db.update_employee_record(invalid, "변경")
    with pytest.raises(ValueError):
        db.set_employee_inactive(invalid)
    with pytest.raises(ValueError):
        db.restore_employee_draft(invalid)


def test_missing_employee_id_and_atomicity(tmp_path):
    db = owner(tmp_path)
    with pytest.raises(ValueError):
        db.update_employee_record(100, "새이름")
    with pytest.raises(ValueError):
        db.set_employee_inactive(100)
    with pytest.raises(ValueError):
        db.restore_employee_draft(100)
    assert db.list_employee_records() == []


def test_wrong_state_transition_rejected(tmp_path):
    db = owner(tmp_path)
    employee = db.add_employee_draft("agent_state", "상태 검사")
    with pytest.raises(ValueError):
        db.restore_employee_draft(employee)
    db.set_employee_inactive(employee)
    with pytest.raises(ValueError):
        db.set_employee_inactive(employee)
    assert db.read_employee_record(employee)["lifecycle"] == "inactive"
    db.restore_employee_draft(employee)
    assert db.read_employee_record(employee)["lifecycle"] == "draft"


def test_owner_permission_gates_all_mutations(tmp_path):
    db = owner(tmp_path)
    employee = db.add_employee_draft("agent_locked", "잠금 검사")
    db.logout()
    for action in (lambda: db.update_employee_record(employee, "탈취"),
                   lambda: db.set_employee_inactive(employee),
                   lambda: db.restore_employee_draft(employee),
                   lambda: db.list_employee_records()):
        with pytest.raises(AuthenticationError):
            action()
    db.login("stage15_owner", "strong-password-2026-test")
    assert db.read_employee_record(employee)["display_name"] == "잠금 검사"


@pytest.mark.parametrize("display,description", [(None, ""), ("", ""), (" ", ""), ("x" * 81, ""), ("정상", "x" * 501)])
def test_invalid_updates_do_not_change_database(tmp_path, display, description):
    db = owner(tmp_path)
    employee = db.add_employee_draft("agent_valid", "기존 직원", "기존 메모")
    with pytest.raises(ValueError):
        db.update_employee_record(employee, display, description)
    assert db.read_employee_record(employee)["display_name"] == "기존 직원"
    assert db.read_employee_record(employee)["description"] == "기존 메모"


@pytest.mark.parametrize("kind,reference", [("rank_id", "job"), ("job_id", "role"), ("role_id", "rank")])
def test_typed_reference_guard_applies_to_updates(tmp_path, kind, reference):
    db = owner(tmp_path)
    wrong = db.add_designation(reference, "부적합 항목")
    employee = db.add_employee_draft("agent_kind", "검사 직원")
    with pytest.raises(ValueError):
        db.update_employee_record(employee, "잘못된 배치", **{kind: wrong})
    assert db.read_employee_record(employee)[kind] is None
    assert db.read_employee_record(employee)["display_name"] == "검사 직원"


def test_references_prevent_deleting_even_inactive_employee(tmp_path):
    db = owner(tmp_path)
    refs = linked(db)
    employee = db.add_employee_draft("agent_ref", "연결 검사", **refs)
    db.set_employee_inactive(employee)
    with pytest.raises(ValueError):
        db.delete_department(refs["department_id"])
    with pytest.raises(ValueError):
        db.delete_designation(refs["rank_id"])


def test_sqlite_state_rejects_executable_state(tmp_path):
    db = owner(tmp_path)
    employee = db.add_employee_draft("agent_noexec", "AI 미실행")
    with pytest.raises(sqlite3.IntegrityError):
        with db._connect() as conn:
            conn.execute("UPDATE ai_employee_profiles SET lifecycle='running' WHERE id=?", (employee,))
    assert db.read_employee_record(employee)["lifecycle"] == "draft"


def test_separate_python_process_uses_persisted_lifecycle(tmp_path):
    db = owner(tmp_path)
    employee = db.add_employee_draft("agent_process", "프로세스 지속")
    db.set_employee_inactive(employee)
    script = 'from desktop.storage import LocalStore; import sys; s=LocalStore(sys.argv[1]); s.login("stage15_owner", "strong-password-2026-test"); print(s.read_employee_record(int(sys.argv[2]))["lifecycle"])'
    result = subprocess.run([sys.executable, "-c", script, str(db.path), str(employee)],
                            capture_output=True, text=True, check=True, timeout=15)
    assert result.stdout.strip() == "inactive"
