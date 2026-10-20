"""승인된 Windows 기본 명령의 실제 호출·SQLite 중복·철회·복구 감사."""
from concurrent.futures import ThreadPoolExecutor
import os
import sqlite3
from threading import Event

import pytest

from desktop import company_native_diagnostics as native
from desktop.storage import LocalStore


@pytest.fixture
def approved_office(tmp_path):
    store = LocalStore(tmp_path / 'native_command.sqlite3')
    store.setup_owner('owner', 'native-command-test-password')
    employee = store.add_employee_draft('windows_diag_staff', '운영 점검 담당')
    store.save_employee_access(employee, ['company:read'], [native.TOOL_KEY])
    tool = store.register_ai_tool(native.TOOL_KEY, 'Windows 버전 확인', 'operations',
                                  'Windows 기본 명령 ver 실행', 'company:read')
    request = store.request_ai_tool_use('windows_version_001', tool, employee,
                                        'Windows 실제 운영체제 버전 점검')
    store.decide_ai_tool_use(request, 'approved', '관리자 명시 실행 승인')
    return store, employee, request


def test_command_runs_once_and_persists_after_login(approved_office, monkeypatch):
    store, _, request = approved_office
    calls = []
    monkeypatch.setattr(native, '_run_windows_version', lambda: calls.append(1) or 'Microsoft Windows [Version 10.0]')
    first = store.execute_approved_windows_version_tool(request)
    again = store.execute_approved_windows_version_tool(request)
    assert first['state'] == 'success' and not first['already_executed']
    assert again['already_executed'] and first['sha256'] == again['sha256']
    assert first['result']['read_only'] and not first['result']['payment_performed']
    assert calls == [1]
    store.logout()
    new = LocalStore(store.path)
    new.login('owner', 'native-command-test-password')
    assert new.approved_windows_version_tool_history()[0]['sha256'] == first['sha256']
    with new._connect() as con:
        with pytest.raises(sqlite3.DatabaseError):
            con.execute("UPDATE aiwack_native_tool_runs SET result_json='{}'")
        with pytest.raises(sqlite3.DatabaseError):
            con.execute('DELETE FROM aiwack_native_tool_runs')


def test_two_windows_cannot_execute_same_request(approved_office, monkeypatch):
    store, _, request = approved_office
    second = LocalStore(store.path)
    second.login('owner', 'native-command-test-password')
    started, release = Event(), Event()
    calls = []
    def slow():
        calls.append(1)
        started.set()
        assert release.wait(5)
        return 'Windows 11'
    monkeypatch.setattr(native, '_run_windows_version', slow)
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(store.execute_approved_windows_version_tool, request)
        assert started.wait(5)
        with pytest.raises(RuntimeError, match='running'):
            second.execute_approved_windows_version_tool(request)
        release.set()
        assert first.result(timeout=5)['state'] == 'success'
    assert calls == [1]


def test_emergency_stop_after_real_call_blocks_success(approved_office, monkeypatch):
    store, _, request = approved_office
    second = LocalStore(store.path)
    second.login('owner', 'native-command-test-password')
    started, release = Event(), Event()
    def slow():
        started.set()
        assert release.wait(5)
        return 'Windows 10'
    monkeypatch.setattr(native, '_run_windows_version', slow)
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(store.execute_approved_windows_version_tool, request)
        assert started.wait(5)
        second.emergency_stop_local(True, '운영 중지')
        release.set()
        with pytest.raises(RuntimeError, match='cancelled'):
            future.result(timeout=5)
    assert store.approved_windows_version_tool_history()[0]['state'] == 'cancelled'


def test_permission_revoked_during_execution_is_not_success(approved_office, monkeypatch):
    store, employee, request = approved_office
    other = LocalStore(store.path)
    other.login('owner', 'native-command-test-password')
    started, release = Event(), Event()
    def slow():
        started.set()
        assert release.wait(5)
        return 'Windows 10'
    monkeypatch.setattr(native, '_run_windows_version', slow)
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(store.execute_approved_windows_version_tool, request)
        assert started.wait(5)
        other.save_employee_access(employee, [], [])
        release.set()
        with pytest.raises(RuntimeError, match='cancelled'):
            future.result(timeout=5)
    assert store.approved_windows_version_tool_history()[0]['error_code'] == 'approval_or_permission_revoked'


def test_crashed_claim_never_retries_automatically(approved_office, monkeypatch):
    store, employee, request = approved_office
    with store._connect() as con:
        native.initialize(con)
        con.execute('''INSERT INTO aiwack_native_tool_runs
            (request_id,employee_id,tool_key,token,state) VALUES(?,?,?,?, 'running')''',
            (request, employee, native.TOOL_KEY, 'a'*32))
    monkeypatch.setattr(native, '_run_windows_version', lambda: pytest.fail('중단된 명령 재호출 금지'))
    with pytest.raises(RuntimeError, match='running'):
        store.execute_approved_windows_version_tool(request)


def test_failed_command_is_audited_without_retry(approved_office, monkeypatch):
    store, _, request = approved_office
    monkeypatch.setattr(native, '_run_windows_version', lambda: (_ for _ in ()).throw(OSError('fail')))
    with pytest.raises(RuntimeError, match='failed'):
        store.execute_approved_windows_version_tool(request)
    assert store.approved_windows_version_tool_history()[0]['error_code'] == 'OSError'
    with pytest.raises(RuntimeError, match='failed'):
        store.execute_approved_windows_version_tool(request)


def test_pending_and_wrong_tool_never_execute(approved_office, monkeypatch):
    store, employee, _ = approved_office
    tool = store.register_ai_tool('local_company_reader', '회사 읽기', 'management',
                                  '로컬 SQLite', 'company:read')
    store.save_employee_access(employee, ['company:read'], [native.TOOL_KEY, 'local_company_reader'])
    request = store.request_ai_tool_use('pending_native_002', tool, employee, '실행 금지')
    monkeypatch.setattr(native, '_run_windows_version', lambda: pytest.fail('실행 금지'))
    with pytest.raises(PermissionError):
        store.execute_approved_windows_version_tool(request)
    for bad in (None, True, 0, '1'):
        with pytest.raises(ValueError):
            store.execute_approved_windows_version_tool(bad)


def test_owner_logout_during_command_cancels_result(approved_office, monkeypatch):
    store, _, request = approved_office
    started, release = Event(), Event()
    def slow():
        started.set()
        assert release.wait(5)
        return 'Windows 11'
    monkeypatch.setattr(native, '_run_windows_version', slow)
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(store.execute_approved_windows_version_tool, request)
        assert started.wait(5)
        store.logout()
        release.set()
        with pytest.raises(RuntimeError, match='cancelled'):
            future.result(timeout=5)
    reopened = LocalStore(store.path)
    reopened.login('owner', 'native-command-test-password')
    assert reopened.approved_windows_version_tool_history()[0]['error_code'] == 'owner_session_ended'


@pytest.mark.skipif(os.name != 'nt', reason='실제 Windows 기본 명령 실행은 Windows runner에서만')
def test_actual_windows_cmd_exe_version(approved_office):
    store, _, request = approved_office
    result = store.execute_approved_windows_version_tool(request)
    assert result['state'] == 'success'
    assert 'Windows' in result['result']['windows_version']
    assert result['external_action_performed']
