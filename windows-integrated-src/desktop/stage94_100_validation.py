"""Stages94-100 local verification helpers. Never claim Windows/LLM/real money tests.
Backups use SQLite online backup API and restore only to a new, previously absent path.
"""
from __future__ import annotations
import hashlib
import os
import sqlite3
from pathlib import Path
from desktop.local_budget_scenarios import calculate
from desktop.stage87_90_management import stopped, stop_history
from desktop.stage91_93_security import spend_history


def file_sha256(path):
    with Path(path).open('rb') as stream:
        h=hashlib.sha256()
        for chunk in iter(lambda:stream.read(1024*1024),b''):
            h.update(chunk)
    return h.hexdigest()


def _destination(store,output):
    dest=Path(output).expanduser().resolve(strict=False)
    if dest.suffix.lower() not in ('.db','.sqlite3'):
        raise ValueError('new SQLite file path required')
    if dest==store.path.resolve():
        raise ValueError('cannot overwrite active database')
    if dest.exists():raise FileExistsError('refuse to overwrite any existing file')
    if not dest.parent.exists() or not dest.parent.is_dir():
        raise ValueError('destination parent directory must already exist')
    return dest


def create_backup(store,destination):
    store.require_permission('company:manage')
    dest=_destination(store,destination)
    # Atomic file creation prevents overwriting race. Destination is exclusive.
    fd=os.open(dest,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
    os.close(fd)
    try:
        with sqlite3.connect(dest) as backup_con:
            with store._connect() as source:
                source.backup(backup_con)
        report=verify_database_copy(dest)
        if not report['integrity_ok']:
            raise ValueError('backup integrity check failed')
        return {'path':str(dest),'sha256':file_sha256(dest),**report,'actual_remote_backup':False}
    except BaseException:
        dest.unlink(missing_ok=True)
        raise


def verify_database_copy(path):
    # URI mode=ro prevents creation or writes on open.
    p=Path(path).resolve()
    if not p.is_file() or p.suffix.lower() not in ('.db','.sqlite3'):
        raise ValueError('SQLite file not found')
    with sqlite3.connect(p.as_uri()+'?mode=ro',uri=True) as con:
        result=con.execute('PRAGMA integrity_check').fetchone()[0]
        fk=con.execute('PRAGMA foreign_key_check').fetchall()
        rows=con.execute('SELECT COUNT(*) FROM owner_accounts').fetchone()[0]
    return {'integrity_ok':result=='ok','foreign_keys_ok':len(fk)==0,
            'owner_account_row_count':rows,'full_application_recovery_verified':False}


def copy_backup_to_new_file(backup,new_destination,store):
    store.require_permission('company:manage')
    source=Path(backup).resolve()
    check=verify_database_copy(source)
    if not check['integrity_ok'] or not check['foreign_keys_ok']:
        raise ValueError('backup verification failed')
    dest=_destination(store,new_destination)
    if dest==source:raise ValueError('refuse to overwrite backup')
    fd=os.open(dest,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
    os.close(fd)
    try:
        with sqlite3.connect(dest) as receiver:
            with sqlite3.connect(source.as_uri()+'?mode=ro',uri=True) as provider:
                provider.backup(receiver)
        verified=verify_database_copy(dest)
        if not verified['integrity_ok'] or not verified['foreign_keys_ok']:
            raise ValueError('restored copy failed validation')
        return {'restored_to_new_path':str(dest),'sha256':file_sha256(dest),
                'active_database_untouched':True,'requires_manual_application_reopen':True}
    except BaseException:
        dest.unlink(missing_ok=True)
        raise


def local_validation_snapshot(con):
    """Stages97-98: deterministic, *simulated-only* invariant probe."""
    from desktop.local_hypothetical_finance import history as assumed_finance
    # Counts do not represent provider fulfillment.
    orders=con.execute('SELECT COUNT(*) FROM local_simulated_orders').fetchone()[0]
    invoices=con.execute('SELECT COUNT(*) FROM local_payment_fixture_audit').fetchone()[0]
    subscriptions=con.execute('SELECT COUNT(*) FROM local_mock_subscriptions').fetchone()[0]
    ledger=assumed_finance(con)
    budget=calculate(con)
    audit_events=stop_history(con)
    spend=spend_history(con)
    return {'mock_orders':orders,'test_payment_fixtures':invoices,
            'mock_subscriptions':subscriptions,'hypothetical_finance_entries':len(ledger),
            'budget':budget,'safety_stop_active':stopped(con),
            'safety_stop_audit_entries':len(audit_events),'spending_review_entries':len(spend),
            'real_orders_verified':False,'real_refunds_verified':False,
            'real_settlement_verified':False,'real_profit_verified':False,
            'real_operations_integration_test_passed':False,
            'offline_simulation_only':True}
