"""Owner-authenticated real SQLite GUI heartbeat and manual crash recovery regressions."""
import sqlite3
import pytest
from desktop.storage import LocalStore,AuthenticationError
from desktop import company_autopilot as auto
from desktop import company_continuity as continuity

@pytest.fixture
def owner(tmp_path):
    db=LocalStore(tmp_path/'continuity.sqlite3')
    db.setup_owner('owner','continuity-owner-password-2026')
    return db

def test_real_owner_gui_heartbeat_persists_without_fake_24h(owner):
    auto.configure(owner,True,now=10000)
    for _ in range(2):continuity.record_gui_heartbeat(owner,'a'*32,now=10001)
    evidence=continuity.observed_gui_continuity(owner,now=10003)
    assert evidence['observed_heartbeat_rows']==1
    assert not evidence['observed_uninterrupted_gui_24h']
    assert not evidence['actual_windows_24h_soak_verified']
    owner.logout()
    with pytest.raises(AuthenticationError):
        continuity.record_gui_heartbeat(owner,'a'*32,now=10003)
    owner.login('owner','continuity-owner-password-2026')
    assert continuity.observed_gui_continuity(owner,now=10003)['observed_heartbeat_rows']==1

def test_owner_inspected_stale_tick_is_immutable_and_survives_restart(owner):
    auto.configure(owner,True,now=100)
    with owner._connect() as con:
        con.execute("INSERT INTO aiwack_autopilot_runs(planned_at,state,started_at) VALUES(100,'running',datetime('now','-300 seconds'))")
        rid=con.execute('SELECT MAX(id) FROM aiwack_autopilot_runs').fetchone()[0]
    assert any(r['run_id']==rid for r in continuity.recent_stale_claims(owner))
    with pytest.raises(PermissionError):
        continuity.inspect_and_close_stale(owner,'tick',rid,'수기 확인 내용',owner_confirmed=False)
    result=continuity.inspect_and_close_stale(owner,'tick',rid,'다른 EXE 창/실제 OS 프로세스 직접 확인',owner_confirmed=True)
    assert result['state']=='failed' and not result['model_retried'] and not result['subprocess_termination_verified']
    assert continuity.recent_stale_claims(owner)==[]
    with owner._connect() as con:
        with pytest.raises(sqlite3.DatabaseError):
            con.execute("DELETE FROM aiwack_autopilot_recovery_audit WHERE run_id=?",(rid,))
        with pytest.raises(sqlite3.DatabaseError):
            con.execute("UPDATE aiwack_autopilot_recovery_audit SET run_kind='model' WHERE run_id=?",(rid,))
    owner.logout()
    fresh=LocalStore(owner.path);fresh.login('owner','continuity-owner-password-2026')
    assert continuity.read_recovery_audit(fresh)[0]['run_id']==rid

def test_live_claim_never_automatically_recovered(owner):
    auto.configure(owner,True,now=100)
    with owner._connect() as con:
        con.execute("INSERT INTO aiwack_autopilot_runs(planned_at,state) VALUES(100,'running')")
        rid=con.execute('SELECT MAX(id) FROM aiwack_autopilot_runs').fetchone()[0]
    with pytest.raises(PermissionError,match='180'):
        continuity.inspect_and_close_stale(owner,'tick',rid,'관리자 직접 확인 기록',owner_confirmed=True)
    assert continuity.read_recovery_audit(owner)==[]

def test_stale_model_is_marked_failed_never_rerun(owner):
    auto.configure(owner,True,now=100)
    task=owner.add_task('Stopped local model')
    with owner._connect() as con:
        con.execute("INSERT INTO aiwack_autopilot_model_runs(task_id,state,created_at) VALUES(?,'running',datetime('now','-300 seconds'))",(task,))
        rid=con.execute('SELECT MAX(id) FROM aiwack_autopilot_model_runs').fetchone()[0]
    result=continuity.inspect_and_close_stale(owner,'model',rid,'Windows 모델 프로세스 직접 종료 확인',owner_confirmed=True)
    assert not result['model_retried']
    assert owner.list_task_runs(task)==[]
    assert auto.approved_model_history(owner)[0]['state']=='failed'

def test_simulated_gui_polling_gaps_are_detected_but_not_os_soak(owner):
    auto.configure(owner,True,now=100000)
    with owner._connect() as con:
        continuity.initialize(con)
        con.executemany("INSERT INTO aiwack_gui_heartbeat(session_token,recorded_epoch,autopilot_enabled) VALUES(?,?,1)",
                        (('b'*32,t) for t in range(100000,186401,30)))
    result=continuity.observed_gui_continuity(owner,now=186400)
    assert result['observed_uninterrupted_gui_24h'] and not result['actual_windows_24h_soak_verified']
    with owner._connect() as con:
        con.execute('DELETE FROM aiwack_gui_heartbeat WHERE recorded_epoch BETWEEN 128000 AND 128600')
    assert not continuity.observed_gui_continuity(owner,now=186400)['observed_uninterrupted_gui_24h']
