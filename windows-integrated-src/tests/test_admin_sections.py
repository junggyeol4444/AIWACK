"""Stage 10: admin navigation is a real UI scaffold, not an implemented business backend."""
import pytest
from desktop.admin_sections import SECTIONS, SECTION_BY_KEY, section_for
from desktop.storage import AuthenticationError, LocalStore


def test_admin_sections_have_unique_ids_and_clear_future_states():
    keys = [section.key for section in SECTIONS]
    assert keys == ["overview", "departments", "tasks", "business", "finance", "permissions", "settings"]
    assert len(keys) == len(set(keys)) == len(SECTION_BY_KEY)
    assert all(section.title and section.summary and section.status and section.planned_features for section in SECTIONS)
    assert all(not section.implemented for section in SECTIONS if section.key not in ("overview", "permissions", "departments", "settings", "tasks"))
    assert section_for("departments").implemented
    assert "부서" in section_for("departments").status
    assert section_for("tasks").implemented
    assert "로컬 AI 텍스트 실행 구현" in section_for("tasks").status
    assert "자동 운영 미구현" in section_for("tasks").status
    assert "미구현" in section_for("finance").status


def test_unknown_section_rejected():
    with pytest.raises(ValueError, match="알 수 없는"):
        section_for("dangerous_external_command")


def test_authentication_permission_required_for_admin_access(tmp_path):
    store = LocalStore(tmp_path / "private.sqlite3")
    with pytest.raises(AuthenticationError):
        store.require_permission("company:manage")
    store.setup_owner("owner_user", "safe-password-2026")
    store.require_permission("company:manage")
    store.logout()
    with pytest.raises(AuthenticationError):
        store.require_permission("company:manage")
