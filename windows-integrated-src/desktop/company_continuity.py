"""Native Tk heartbeat and explicit owner-reviewed interrupted-run recovery.

GUI poll logs are SQLite evidence, never a claim that the OS ran for 24 hours.
No failed subprocess is terminated, impersonated, or automatically retried.
"""
from __future__ import annotations
import re
import sqlite3
import time

_SESSION = re.compile(r'[a-f0-9]{32}\Z')

def initialize(con: sqlite3.Connection) -> None:
    con.execute("""CREATE TABLE IF NOT EXISTS aiwack_gui_heartbeat (
       id INTEGER PRIMARY KEY AUTOINCREMENT,
       session_token TEXT NOT NULL CHECK(length(session_token)=32),
       recorded_epoch INTEGER NOT NULL CHECK(recorded_epoch>0),
       autopilot_enabled INTEGER NOT NULL CHECK(autopilot_enabled IN (0,1)),
       created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
       UNIQUE(session_token,recorded_epoch))""")
    con.execute("CREATE INDEX IF NOT EXISTS aiwack_heartbeat_epoch ON aiwack_gui_heartbeat(recorded_epoch DESC)")
    con.execute("""CREATE TABLE IF NOT EXISTS aiwack_autopilot_recovery_audit (
       id INTEGER PRIMARY KEY AUTOINCREMENT,
       run_kind TEXT NOT NULL CHECK(run_kind IN ('tick','model')),
       run_id INTEGER NOT NULL CHECK(run_id>0),
       elapsed_seconds INTEGER NOT NULL CHECK(elapsed_seconds>=180),
       owner_confirmed INTEGER NOT NULL CHECK(owner_confirmed=1),
       operator_note TEXT NOT NULL CHECK(length(operator_note) BETWEEN 5 AND 200),
       created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
       UNIQUE(run_kind,run_id))""")
    for op in ('UPDATE','DELETE'):
        con.execute(f"""CREATE TRIGGER IF NOT EXISTS aiwack_recovery_audit_no_{op.lower()}
           BEFORE {op} ON aiwack_autopilot_recovery_audit BEGIN
           SELECT RAISE(ABORT,'관리자 복구 감사 수정·삭제 금지'); END""")

def record_gui_heartbeat(store, session_token: str, *, now: int | None=None) -> dict:
    store.require_permission('company:manage')
    if not isinstance(session_token,str) or not _SESSION.fullmatch(session_token):
        raise ValueError('인증된 GUI 세션 ID 오류')
    stamp=int(time.time()) if now is None else now
    if type(stamp) is not int or stamp<=0:raise ValueError('GUI 기록 시각 오류')
    with store._connect() as con:
        con.execute('BEGIN IMMEDIATE')
        initialize(con)
        present=con.execute("""SELECT 1 FROM sqlite_master
             WHERE type='table' AND name='aiwack_autopilot_settings'""").fetchone()
        row=con.execute("""SELECT enabled FROM aiwack_autopilot_settings WHERE id=1""").fetchone() if present else None
        enabled=bool(row and row[0])
        con.execute("""INSERT OR IGNORE INTO aiwack_gui_heartbeat
           (session_token,recorded_epoch,autopilot_enabled) VALUES(?,?,?)""",
           (session_token,stamp,int(enabled)))
    return {'recorded_epoch':stamp,'autopilot_enabled':enabled,'real_windows_uptime_attested':False}

def recent_stale_claims(store, *, min_age_seconds:int=180) -> list[dict]:
    from desktop import company_autopilot as auto
    store.require_permission('company:manage')
    if type(min_age_seconds) is not int or not 180<=min_age_seconds<=86400:
        raise ValueError('복구 가능 시간은 180~86400초')
    auto.initialize(store)
    with store._connect() as con:
        initialize(con)
        result=[]
        for kind,table,column in (('tick','aiwack_autopilot_runs','started_at'),
                                  ('model','aiwack_autopilot_model_runs','created_at')):
            rows=con.execute(f"""SELECT id,CAST((julianday('now')-julianday({column}))*86400 AS INTEGER)
                   FROM {table} WHERE state='running' ORDER BY id DESC LIMIT 100""").fetchall()
            for run_id,elapsed in rows:
                if elapsed is not None and elapsed>=min_age_seconds:
                    result.append({'kind':kind,'run_id':int(run_id),
                                   'elapsed_seconds':int(elapsed),'requires_process_inspection':True})
    return result

def inspect_and_close_stale(store,kind:str,run_id:int,note:str,*,owner_confirmed:bool=False) -> dict:
    from desktop import company_autopilot as auto
    store.require_permission('company:manage')
    if kind not in ('tick','model') or type(run_id) is not int or run_id<=0:
        raise ValueError('기존 모델·운영 실행 번호 오류')
    if owner_confirmed is not True:
        raise PermissionError('다른 Windows 실행 창/모델 프로세스를 직접 확인해야 합니다.')
    if not isinstance(note,str) or not 5<=len(note.strip())<=200:
        raise ValueError('소유자 직접 확인 사유는 5~200자여야 합니다.')
    auto.initialize(store)
    table,column=(('aiwack_autopilot_runs','started_at') if kind=='tick'
                  else ('aiwack_autopilot_model_runs','created_at'))
    with store._connect() as con:
        con.execute('BEGIN IMMEDIATE')
        initialize(con)
        row=con.execute(f"""SELECT state,CAST((julianday('now')-julianday({column}))*86400 AS INTEGER)
                FROM {table} WHERE id=?""",(run_id,)).fetchone()
        if row is None or row[0]!='running':
            raise ValueError('running 상태인 미완료 감사 기록이 아닙니다.')
        if row[1] is None or row[1]<180:
            raise PermissionError('실행 중인 다른 Windows 창을 보호하려면 최소 180초가 필요합니다.')
        change=con.execute(f"""UPDATE {table} SET state='failed',
                error_kind='OwnerInspectedStaleClaim',finished_at=CURRENT_TIMESTAMP
                WHERE id=? AND state='running'""",(run_id,))
        if change.rowcount!=1:raise RuntimeError('다른 창에서 상태를 변경했습니다.')
        audit=con.execute("""INSERT INTO aiwack_autopilot_recovery_audit
                (run_kind,run_id,elapsed_seconds,owner_confirmed,operator_note)
                VALUES(?,?,?,?,?)""",(kind,run_id,int(row[1]),1,note.strip())).lastrowid
    return {'audit_id':int(audit),'run_kind':kind,'run_id':run_id,
            'state':'failed','model_retried':False,'subprocess_termination_verified':False}

def read_recovery_audit(store,limit:int=30) -> list[dict]:
    store.require_permission('company:manage')
    if type(limit) is not int or not 1<=limit<=100:raise ValueError('감사 조회는 1~100건')
    with store._connect() as con:
        initialize(con)
        rows=con.execute("""SELECT id,run_kind,run_id,elapsed_seconds,operator_note,created_at
                 FROM aiwack_autopilot_recovery_audit ORDER BY id DESC LIMIT ?""",(limit,)).fetchall()
    return [dict(zip(('id','kind','run_id','elapsed_seconds','note','created_at'),row)) for row in rows]

def observed_gui_continuity(store, *, now:int|None=None) -> dict:
    store.require_permission('company:manage')
    stamp=int(time.time()) if now is None else now
    if type(stamp) is not int or stamp<=0:raise ValueError('관측 시각 오류')
    with store._connect() as con:
        initialize(con)
        rows=con.execute("""SELECT session_token,recorded_epoch,autopilot_enabled
           FROM aiwack_gui_heartbeat WHERE recorded_epoch BETWEEN ? AND ?
           ORDER BY session_token,recorded_epoch""",(max(1,stamp-86490),stamp)).fetchall()
    sessions={}
    for sid,epoch,enabled in rows:
        sessions.setdefault(sid,[]).append((int(epoch),bool(enabled)))
    complete=False;gaps=0
    for records in sessions.values():
        missed=sum(records[i][0]-records[i-1][0]>90 for i in range(1,len(records)))
        gaps+=missed
        if records[0][0]<=stamp-86400 and records[-1][0]>=stamp-90 and missed==0 and all(e for _,e in records):
            complete=True
    return {'observed_heartbeat_rows':len(rows),'distinct_gui_sessions':len(sessions),
            'observed_gaps_gt_90s':gaps,'observed_uninterrupted_gui_24h':complete,
            'actual_windows_24h_soak_verified':False,
            'external_accounts_or_provider_verification':False}
