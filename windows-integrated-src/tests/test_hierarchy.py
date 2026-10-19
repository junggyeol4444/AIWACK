"""Stage 16, local-only organizational tree persistence, access control and invariants."""
import sqlite3
import pytest
from desktop.storage import LocalStore, AuthenticationError


def prepared(tmp_path):
    store = LocalStore(tmp_path / "hierarchy.sqlite3")
    store.setup_owner("owner_hierarchy", "strong-password-2026")
    research = store.add_department("연구개발", "부서")
    sales = store.add_department("마케팅", "부서")
    ceo = store.add_employee_draft("chief_001", "총괄 AI")
    head = store.add_employee_draft("research_lead", "연구개발 부서장", department_id=research)
    staff = store.add_employee_draft("research_staff", "연구개발 직원", department_id=research)
    other = store.add_employee_draft("sales_staff", "영업 직원", department_id=sales)
    return store, research, sales, ceo, head, staff, other


def assigned(tmp_path):
    store, research, sales, ceo, head, staff, other = prepared(tmp_path)
    store.assign_reporting_line(ceo, "ceo")
    store.assign_reporting_line(head, "department_head", ceo)
    store.assign_reporting_line(staff, "staff", head)
    return store, research, sales, ceo, head, staff, other


def test_real_reporting_tree_save_reopen_and_logout(tmp_path):
    s, research, sales, ceo, head, staff, _ = assigned(tmp_path)
    assert s.list_reporting_lines() == [
        {"employee_id": ceo, "tier": "ceo", "manager_id": None},
        {"employee_id": head, "tier": "department_head", "manager_id": ceo},
        {"employee_id": staff, "tier": "staff", "manager_id": head},
    ]
    s.logout()
    with pytest.raises(AuthenticationError):
        s.list_reporting_lines()
    fresh = LocalStore(s.path)
    with pytest.raises(AuthenticationError):
        fresh.assign_reporting_line(staff, "staff", head)
    fresh.login("owner_hierarchy", "strong-password-2026")
    assert len(fresh.list_reporting_lines()) == 3
    assert fresh.list_departments()[0]["id"] == research


def test_one_ceo_max_and_only_unassigned_ceo(tmp_path):
    s, _, _, ceo, head, staff, other = assigned(tmp_path)
    with pytest.raises(ValueError):
        s.assign_reporting_line(other, "ceo")
    with pytest.raises(ValueError):
        s.assign_reporting_line(head, "ceo")
    assert s.list_reporting_lines()[0]["employee_id"] == ceo
    assert len(s.list_reporting_lines()) == 3


def test_head_requires_ceo_and_staff_requires_matching_head(tmp_path):
    s, research, sales, ceo, head, staff, other = prepared(tmp_path)
    with pytest.raises(ValueError):
        s.assign_reporting_line(head, "department_head", ceo)
    with pytest.raises(ValueError):
        s.assign_reporting_line(staff, "staff", head)
    s.assign_reporting_line(ceo, "ceo")
    s.assign_reporting_line(head, "department_head", ceo)
    with pytest.raises(ValueError):
        s.assign_reporting_line(other, "staff", head)  # wrong department
    with pytest.raises(ValueError):
        s.assign_reporting_line(staff, "department_head", head)
    with pytest.raises(ValueError):
        s.assign_reporting_line(staff, "staff", ceo)
    with pytest.raises(ValueError):
        s.assign_reporting_line(ceo, "staff", ceo)  # cyclic/self link
    assert len(s.list_reporting_lines()) == 2


def test_invalid_manager_and_tier_are_rejected(tmp_path):
    s, research, sales, ceo, head, staff, other = prepared(tmp_path)
    for fn in (
        lambda: s.assign_reporting_line(ceo, "director"),
        lambda: s.assign_reporting_line(ceo, "ceo", head),
        lambda: s.assign_reporting_line(head, "department_head"),
        lambda: s.assign_reporting_line(head, "staff", 999),
        lambda: s.assign_reporting_line(head, "staff", -2),
        lambda: s.assign_reporting_line(999, "ceo"),
    ):
        with pytest.raises(ValueError):
            fn()
    assert s.list_reporting_lines() == []


def test_lead_with_reports_cannot_be_disabled_moved_or_unassigned(tmp_path):
    s, research, sales, ceo, head, staff, other = assigned(tmp_path)
    with pytest.raises(ValueError):
        s.unassign_reporting_line(ceo)
    with pytest.raises(ValueError):
        s.unassign_reporting_line(head)
    with pytest.raises(ValueError):
        s.assign_reporting_line(head, "staff", head)
    with pytest.raises((sqlite3.IntegrityError, ValueError)):
        s.set_employee_inactive(head)
    with pytest.raises((sqlite3.IntegrityError, ValueError)):
        s.update_employee_record(head, "옮기기", department_id=sales)
    with pytest.raises((sqlite3.IntegrityError, ValueError)):
        s.update_employee_record(staff, "잘못된 이동", department_id=sales)
    assert s.read_employee_record(head)["department_id"] == research
    assert s.read_employee_record(staff)["department_id"] == research
    assert len(s.list_reporting_lines()) == 3


def test_only_leaf_first_can_unassign(tmp_path):
    s, _, _, ceo, head, staff, _ = assigned(tmp_path)
    s.unassign_reporting_line(staff)
    s.unassign_reporting_line(head)
    s.unassign_reporting_line(ceo)
    assert s.list_reporting_lines() == []
    s.assign_reporting_line(ceo, "ceo")
    assert len(s.list_reporting_lines()) == 1


def test_existing_employee_records_migrate_without_loss(tmp_path):
    path = tmp_path / "migrated.sqlite3"
    s = LocalStore(path)
    s.setup_owner("owner_hierarchy", "strong-password-2026")
    s.save_note("기존 메모 유지")
    emp = s.add_employee_draft("legacy_employee", "기존 직원")
    # Re-initializing the schema leaves all existing employees intact.
    fresh = LocalStore(path)
    fresh.login("owner_hierarchy", "strong-password-2026")
    assert fresh.read_note() == "기존 메모 유지"
    assert fresh.read_employee_record(emp)["display_name"] == "기존 직원"
    assert fresh.list_reporting_lines() == []


def test_sql_triggers_enforce_rules_for_raw_mutations(tmp_path):
    s, research, sales, ceo, head, staff, other = assigned(tmp_path)
    with pytest.raises(sqlite3.IntegrityError):
        with s._connect() as con:
            con.execute("UPDATE ai_reporting_lines SET manager_id=? WHERE employee_id=?", (staff, head))
    with pytest.raises(sqlite3.IntegrityError):
        with s._connect() as con:
            con.execute("DELETE FROM ai_reporting_lines WHERE employee_id=?", (ceo,))
    with pytest.raises(sqlite3.IntegrityError):
        with s._connect() as con:
            con.execute("UPDATE ai_employee_profiles SET department_id=? WHERE id=?", (sales, staff))
    assert len(s.list_reporting_lines()) == 3
