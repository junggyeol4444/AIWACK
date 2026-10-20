"""Actual SQLite online backup and safe isolated restore without destructive overwrite."""
import sqlite3
from pathlib import Path
import pytest
from desktop.storage import LocalStore
from desktop import company_backup as bk


@pytest.fixture
def company(tmp_path):
    s=LocalStore(tmp_path/'live.sqlite3')
    s.setup_owner('backup_owner','backup-owner-test-password-2026')
    s.save_company('AIWACK test company','Preserved state','Owner controlled')
    return s,tmp_path/'backup_root'


def test_snapshot_can_restore_a_verified_isolated_copy_without_modifying_live(company):
    s,folder=company
    first=bk.create_snapshot(s,root=folder)
    assert first['sqlite_integrity']=='ok'
    assert bk.verify_snapshot(s,Path(first['path']),root=folder)['verified']
    s.save_company('Changed company','New source content','After backup')
    restored=bk.restore_into_new_copy(s,Path(first['path']),root=folder)
    assert restored['live_database_untouched']
    assert s.read_company()['name']=='Changed company'
    with sqlite3.connect(restored['restored_copy']) as con:
        assert con.execute('SELECT name FROM company_profile WHERE id=1').fetchone()[0]=='AIWACK test company'


def test_snapshot_is_unique_and_repeatable(company):
    s,folder=company
    a=bk.create_snapshot(s,root=folder)
    b=bk.create_snapshot(s,root=folder)
    assert a['path']!=b['path']
    assert bk.verify_snapshot(s,Path(a['path']),root=folder)['verified']
    assert bk.verify_snapshot(s,Path(b['path']),root=folder)['verified']


def test_changed_snapshot_is_rejected_even_with_sqlite_magic(company):
    s,folder=company
    result=bk.create_snapshot(s,root=folder)
    p=Path(result['path'])
    with p.open('ab') as fp:fp.write(b'UNAPPROVED_EXTRA_BYTES')
    with pytest.raises(RuntimeError,match='SHA256'):
        bk.verify_snapshot(s,p,root=folder)


def test_snapshot_refuses_nonowner_paths_and_missing_manifest(company):
    s,folder=company
    result=bk.create_snapshot(s,root=folder)
    p=Path(result['path'])
    with pytest.raises(PermissionError):
        bk.verify_snapshot(s,s.path,root=folder)
    Path(result['manifest']).unlink()
    with pytest.raises(ValueError):
        bk.verify_snapshot(s,p,root=folder)


def test_backup_during_emergency_stop_is_read_only(company):
    s,folder=company
    s.emergency_stop_local(True,'Owner halted company')
    result=bk.create_snapshot(s,root=folder)
    assert bk.verify_snapshot(s,Path(result['path']),root=folder)['verified']
    assert s.read_company()['name']=='AIWACK test company'


def test_snapshot_during_active_owner_writes_has_consistent_foreign_keys(company):
    from threading import Event, Thread
    s,folder=company
    ready=Event()
    done=Event()
    errors=[]
    def writer():
        try:
            ready.set()
            for n in range(12):
                with s._connect() as con:
                    con.execute('BEGIN IMMEDIATE')
                    con.execute("UPDATE company_profile SET description=? WHERE id=1",
                                (f'concurrent-writer-{n}',))
        except Exception as exc:
            errors.append(exc)
        finally:
            done.set()
    thread=Thread(target=writer)
    thread.start()
    try:
        assert ready.wait(10)
        info=bk.create_snapshot(s,root=folder)
        assert bk.verify_snapshot(s,Path(info['path']),root=folder)['verified']
        assert done.wait(12)
        assert errors==[]
    finally:
        thread.join(timeout=15)
    assert not thread.is_alive()
    original=s.read_company()
    with sqlite3.connect(info['path']) as con:
        assert con.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
        assert con.execute('PRAGMA foreign_key_check').fetchall()==[]
        assert con.execute('SELECT description FROM company_profile WHERE id=1').fetchone()[0].startswith(
            'concurrent-writer-') or con.execute('SELECT description FROM company_profile WHERE id=1').fetchone()[0]=='Preserved state'
    assert original['name']=='AIWACK test company'
