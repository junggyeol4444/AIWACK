"""Stage 17: offline agent permissions/tool configuration, deliberately non-executable."""
from __future__ import annotations

import sqlite3
import pytest

from desktop.access_policy import CAPABILITIES, TOOLS, validate_grants
from desktop.storage import AuthenticationError, LocalStore


def prepared(tmp_path):
    store = LocalStore(tmp_path / 'access.sqlite3')
    store.setup_owner('local_owner', 'secure-passphrase-2026')
    a = store.add_employee_draft('research_agent_01', '리서치 초안 직원')
    b = store.add_employee_draft('writer_agent_01', '집필 초안 직원')
    return store, a, b


def test_default_deny_and_unknown_employee(tmp_path):
    store, employee, _ = prepared(tmp_path)
    assert store.read_employee_access(employee) == {'capabilities': [], 'tools': []}
    assert not store.is_employee_allowed(employee, 'company:read')
    assert not store.is_employee_allowed(employee, 'company:read', 'local_company_reader')
    assert not store.is_employee_allowed(9999, 'company:read')
    with pytest.raises(AuthenticationError):
        store.require_employee_access(employee, 'company:read')
    with pytest.raises(ValueError):
        store.read_employee_access(9999)


def test_atomic_save_and_reopen_isolation(tmp_path):
    store, employee, other = prepared(tmp_path)
    store.save_employee_access(employee, ['goals:read', 'company:read'],
                               ['local_goals_reader', 'local_company_reader'])
    fresh = LocalStore(store.path)
    with pytest.raises(AuthenticationError):
        fresh.read_employee_access(employee)
    fresh.login('local_owner', 'secure-passphrase-2026')
    assert fresh.read_employee_access(employee) == {
        'capabilities': ['company:read', 'goals:read'],
        'tools': ['local_company_reader', 'local_goals_reader'],
    }
    assert fresh.is_employee_allowed(employee, 'company:read', 'local_company_reader')
    assert not fresh.is_employee_allowed(employee, 'company:read', 'local_goals_reader')
    assert not fresh.is_employee_allowed(other, 'company:read')
    assert not fresh.is_employee_allowed(employee, 'tasks:propose')
    with pytest.raises(AuthenticationError):
        fresh.require_employee_access(other, 'company:read')


def test_invalid_configuration_rolls_back(tmp_path):
    store, employee, _ = prepared(tmp_path)
    store.save_employee_access(employee, ['company:read'], ['local_company_reader'])
    invalid = [
        (['company:read'], ['local_goals_reader']),
        (['owner:manage'], []),
        (['company:read', 'company:read'], []),
        (['company:read'], ['shell_exec']),
        (['company:read'], ['local_company_reader', 'local_company_reader']),
        ('company:read', []),
        (['company:read'], 'local_company_reader'),
        ([], ["https://external.example/run"]),
    ]
    for cap, tools in invalid:
        with pytest.raises(ValueError):
            store.save_employee_access(employee, cap, tools)
        assert store.read_employee_access(employee) == {
            'capabilities': ['company:read'], 'tools': ['local_company_reader']}


def test_replace_revocation_and_tool_dependency(tmp_path):
    store, employee, _ = prepared(tmp_path)
    store.save_employee_access(employee, ['company:read'], ['local_company_reader'])
    store.save_employee_access(employee, ['goals:read'], [])
    assert not store.is_employee_allowed(employee, 'company:read')
    assert store.is_employee_allowed(employee, 'goals:read')
    assert store.read_employee_access(employee)['tools'] == []
    store.save_employee_access(employee, [], [])
    assert store.read_employee_access(employee) == {'capabilities': [], 'tools': []}


def test_disabled_employee_forbidden_and_reactivation_does_not_restore(tmp_path):
    store, employee, _ = prepared(tmp_path)
    store.save_employee_access(employee, ['company:read'], ['local_company_reader'])
    store.set_employee_inactive(employee)
    assert store.read_employee_access(employee) == {'capabilities': [], 'tools': []}
    assert not store.is_employee_allowed(employee, 'company:read')
    with pytest.raises(ValueError, match='비활성'):
        store.save_employee_access(employee, ['company:read'], ['local_company_reader'])
    store.restore_employee_draft(employee)
    assert not store.is_employee_allowed(employee, 'company:read')
    store.save_employee_access(employee, ['company:read'], ['local_company_reader'])
    assert store.is_employee_allowed(employee, 'company:read', 'local_company_reader')


def test_auth_logout_blocks_all_employee_policy_calls(tmp_path):
    store, employee, _ = prepared(tmp_path)
    store.logout()
    for operation in (
        lambda: store.read_employee_access(employee),
        lambda: store.save_employee_access(employee, [], []),
        lambda: store.is_employee_allowed(employee, 'company:read'),
        lambda: store.require_employee_access(employee, 'company:read'),
    ):
        with pytest.raises(AuthenticationError):
            operation()


@pytest.mark.parametrize('wrong_id', [0, -1, True, None, '1'])
def test_employee_id_validation(tmp_path, wrong_id):
    store, employee, _ = prepared(tmp_path)
    with pytest.raises(ValueError):
        store.save_employee_access(wrong_id, [], [])
    with pytest.raises(ValueError):
        store.read_employee_access(wrong_id)


def test_builtin_catalog_has_no_network_or_shell_connector():
    assert len(CAPABILITIES) == 4
    assert len(TOOLS) == 4
    for key, (label, required) in TOOLS.items():
        assert key.startswith('local_')
        assert required in CAPABILITIES
        if key in {'local_company_reader', 'local_goals_reader'}:
            assert '로컬 읽기 전용' in label
        else:
            assert '실행 미구현' in label
    assert validate_grants([], []) == (set(), set())


def test_schema_rejects_invalid_or_inactive_direct_sql(tmp_path):
    store, employee, other = prepared(tmp_path)
    with pytest.raises(sqlite3.IntegrityError):
        with store._connect() as con:
            con.execute('INSERT INTO ai_employee_capability_grants VALUES (?, ?)', (employee, 'shell:execute'))
    store.set_employee_inactive(other)
    with pytest.raises(sqlite3.IntegrityError):
        with store._connect() as con:
            con.execute('INSERT INTO ai_employee_capability_grants VALUES (?, ?)', (other, 'company:read'))


def test_preserves_earlier_company_department_and_notes(tmp_path):
    store, employee, _ = prepared(tmp_path)
    store.save_note('기존 검사 메모')
    store.save_company('기존 회사', '이전', '유지')
    department = store.add_department('연구팀', '부서 보존')
    store.save_employee_access(employee, ['company:read'], ['local_company_reader'])
    restarted = LocalStore(store.path)
    restarted.login('local_owner', 'secure-passphrase-2026')
    assert restarted.read_note() == '기존 검사 메모'
    assert restarted.read_company()['name'] == '기존 회사'
    assert restarted.list_departments()[0]['id'] == department
    assert restarted.is_employee_allowed(employee, 'company:read', 'local_company_reader')


def test_raw_sql_cannot_grant_tool_without_permission(tmp_path):
    store, employee, _ = prepared(tmp_path)
    with pytest.raises(sqlite3.IntegrityError, match='requires capability'):
        with store._connect() as con:
            con.execute('INSERT INTO ai_employee_tool_grants VALUES (?, ?)', (employee, 'local_company_reader'))
    store.save_employee_access(employee, ['company:read'], ['local_company_reader'])
    with store._connect() as con:
        con.execute('DELETE FROM ai_employee_capability_grants WHERE employee_id=? AND capability=?',
                    (employee, 'company:read'))
    assert store.read_employee_access(employee) == {'capabilities': [], 'tools': []}


def test_unknown_permission_or_tool_fails_closed(tmp_path):
    store, employee, _ = prepared(tmp_path)
    store.save_employee_access(employee, ['company:read'], ['local_company_reader'])
    assert not store.is_employee_allowed(employee, 'owner:manage')
    assert not store.is_employee_allowed(employee, 'company:read', 'remote_shell')
    assert not store.is_employee_allowed(employee, 'company:read', ['not-hashable'])
    assert not store.is_employee_allowed(employee, [], 'local_company_reader')
