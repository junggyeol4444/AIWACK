"""Local-only scope tests; none are evidence of real external business or a full release."""
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import pytest
from desktop.storage import LocalStore
from desktop.stage94_100_validation import verify_database_copy,file_sha256

@pytest.fixture
def owned(tmp_path):
    s=LocalStore(tmp_path/'source.sqlite3')
    s.setup_owner('owner','some-long-password-123')
    return s

def test_94_backup_and_new_path_restore_without_overwrite(owned,tmp_path):
    backup=tmp_path/'backup.sqlite3';restored=tmp_path/'restored.sqlite3'
    info=owned.backup_to_new_path(backup)
    assert info['integrity_ok'] and info['foreign_keys_ok']
    assert not info['full_application_recovery_verified']
    origin=file_sha256(owned.path)
    r=owned.restore_backup_as_new_database(backup,restored)
    assert r['active_database_untouched']
    assert file_sha256(owned.path)==origin
    assert verify_database_copy(restored)['integrity_ok']
    with pytest.raises(FileExistsError):owned.backup_to_new_path(backup)
    with pytest.raises(ValueError):owned.backup_to_new_path(owned.path)
    with pytest.raises(FileExistsError):owned.restore_backup_as_new_database(backup,restored)
    owned.logout()
    with pytest.raises(PermissionError):owned.backup_to_new_path(tmp_path/'forbidden.db')

def test_95_reopen_process_object_preserves_safety_stop(owned):
    assert owned.emergency_stop_local(True,'Local recovery rehearsal')['stopped']
    owned.logout()
    separate=LocalStore(owned.path)
    with pytest.raises(PermissionError):separate.offline_management_view('approvals')
    separate.login('owner','some-long-password-123')
    assert separate.offline_management_view('approvals')['local_emergency_stopped']
    assert not separate.emergency_stop_local(False,'Owner manual review')['stopped']
    assert not LocalStore(owned.path)._logged_in

def test_96_small_bounded_read_concurrency_not_model_stress(owned):
    def probe(_):
        view=owned.offline_management_view('organization')
        return view['read_only']
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert all(pool.map(probe,range(8)))
    # Not a parallel GGUF model load test and not a long-duration stress test.

def test_97_98_simulated_money_not_real(owned):
    data=owned.offline_integration_evidence()
    assert data['offline_simulation_only']
    assert all(not data[name] for name in ('real_orders_verified','real_refunds_verified',
                   'real_settlement_verified','real_profit_verified',
                   'real_operations_integration_test_passed'))
    assert data['budget']['foreign_currency_conversion']=='FORBIDDEN_UNVERIFIED'
    assert owned.local_spend_review_history()==[]

def test_99_100_release_qualification_is_explicitly_not_proven(owned):
    data=owned.offline_integration_evidence()
    assert not data['real_operations_integration_test_passed']
    assert not data['budget']['accounting_compliant']
