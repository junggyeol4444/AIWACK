"""Windows 커널 프로세스 종료 확인 기반 로컬 자동운영 tick 복구.

모델·결제·외부 작업을 재시도하지 않는다. PID 생성시각 불명확 시 변경 금지.
"""
from __future__ import annotations
import ctypes
from ctypes import wintypes
import os
import re
import time
from desktop.stage87_90_management import stopped

_TOKEN=re.compile(r"[0-9a-f]{32}\Z")

def _probe(pid, birth=None):
    if os.name!="nt":
        return "unsupported",None
    dll=ctypes.WinDLL("kernel32",use_last_error=True)
    dll.OpenProcess.argtypes=[wintypes.DWORD,wintypes.BOOL,wintypes.DWORD]
    dll.OpenProcess.restype=wintypes.HANDLE
    dll.GetProcessTimes.argtypes=[wintypes.HANDLE]+[ctypes.POINTER(wintypes.FILETIME)]*4
    dll.GetProcessTimes.restype=wintypes.BOOL
    dll.WaitForSingleObject.argtypes=[wintypes.HANDLE,wintypes.DWORD]
    dll.WaitForSingleObject.restype=wintypes.DWORD
    dll.CloseHandle.argtypes=[wintypes.HANDLE]
    handle=dll.OpenProcess(0x1000,False,pid)
    if not handle:
        return ("dead" if ctypes.get_last_error()==87 else "unknown"),None
    try:
        a,b,c,d=(wintypes.FILETIME() for _ in range(4))
        if not dll.GetProcessTimes(handle,ctypes.byref(a),ctypes.byref(b),
                                   ctypes.byref(c),ctypes.byref(d)):
            return "unknown",None
        creation=(int(a.dwHighDateTime)<<32)|int(a.dwLowDateTime)
        if birth is not None and creation!=birth:
            return "dead",creation
        wait=dll.WaitForSingleObject(handle,0)
        return ("dead" if wait==0 else "alive" if wait==258 else "unknown"),creation
    finally:
        dll.CloseHandle(handle)

def initialize(con):
    con.execute("""CREATE TABLE IF NOT EXISTS aiwack_native_sessions(
        token TEXT PRIMARY KEY CHECK(length(token)=32),
        pid INTEGER NOT NULL, birth INTEGER NOT NULL,
        first_seen INTEGER NOT NULL,last_seen INTEGER NOT NULL)""")
    con.execute("""CREATE TABLE IF NOT EXISTS aiwack_native_tick_owners(
        run_id INTEGER PRIMARY KEY REFERENCES aiwack_autopilot_runs(id),
        token TEXT NOT NULL REFERENCES aiwack_native_sessions(token))""")
    con.execute("""CREATE TABLE IF NOT EXISTS aiwack_native_tick_recoveries(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        run_id INTEGER NOT NULL UNIQUE REFERENCES aiwack_autopilot_runs(id),
        token TEXT NOT NULL,pid INTEGER NOT NULL,birth INTEGER NOT NULL,
        observed_epoch INTEGER NOT NULL,reason TEXT NOT NULL)""")
    for op in ("UPDATE","DELETE"):
        con.execute(f"""CREATE TRIGGER IF NOT EXISTS aiwack_native_recovery_no_{op.lower()}
            BEFORE {op} ON aiwack_native_tick_recoveries BEGIN
            SELECT RAISE(ABORT,'종료 확인 복구 감사 변경 금지'); END""")

def register(store,token):
    store.require_permission("company:manage")
    if not isinstance(token,str) or not _TOKEN.fullmatch(token):
        raise ValueError("GUI 프로세스 토큰 오류")
    pid=os.getpid()
    state,birth=_probe(pid)
    if state!="alive" or not birth:
        return False
    now=int(time.time())
    with store._connect() as con:
        con.execute("BEGIN IMMEDIATE")
        initialize(con)
        row=con.execute("SELECT pid,birth FROM aiwack_native_sessions WHERE token=?",
                        (token,)).fetchone()
        if row and tuple(row)!=(pid,birth):
            raise PermissionError("GUI 프로세스 토큰 충돌")
        if row:
            con.execute("UPDATE aiwack_native_sessions SET last_seen=? WHERE token=?",
                        (now,token))
        else:
            con.execute("""INSERT INTO aiwack_native_sessions
                (token,pid,birth,first_seen,last_seen) VALUES(?,?,?,?,?)""",
                (token,pid,birth,now,now))
    return True

def bind(con,run_id,token):
    if not isinstance(token,str) or not _TOKEN.fullmatch(token):
        raise ValueError("자동 운영 소유 토큰 오류")
    initialize(con)
    row=con.execute("SELECT pid,birth FROM aiwack_native_sessions WHERE token=?",
                    (token,)).fetchone()
    if not row or row[0]!=os.getpid() or _probe(row[0],row[1])[0]!="alive":
        raise PermissionError("현재 GUI Windows 프로세스 소유권 확인 실패")
    con.execute("INSERT INTO aiwack_native_tick_owners(run_id,token) VALUES(?,?)",
                (run_id,token))

def recover(store,minimum_age=180):
    store.require_permission("company:manage")
    if type(minimum_age) is not int or minimum_age<180:
        raise ValueError("최소 180초 경과 후에만 종료 확인")
    if os.name!="nt":
        return []
    from desktop import company_autopilot
    company_autopilot.initialize(store)
    now=int(time.time())
    result=[]
    with store._connect() as con:
        con.execute("BEGIN IMMEDIATE")
        initialize(con)
        if stopped(con):
            return result
        rows=con.execute("""SELECT r.id,s.token,s.pid,s.birth
            FROM aiwack_autopilot_runs r
            JOIN aiwack_native_tick_owners o ON o.run_id=r.id
            JOIN aiwack_native_sessions s ON s.token=o.token
            WHERE r.state='running' AND r.planned_at<=?
            ORDER BY r.id LIMIT 30""",(now-minimum_age,)).fetchall()
        for run_id,token,pid,birth in rows:
            if _probe(int(pid),int(birth))[0]!="dead":
                continue
            change=con.execute("""UPDATE aiwack_autopilot_runs
                SET state='failed',error_kind='WindowsOwnerProcessExited',
                    finished_at=CURRENT_TIMESTAMP
                WHERE id=? AND state='running'""",(run_id,))
            if change.rowcount!=1:continue
            con.execute("""INSERT INTO aiwack_native_tick_recoveries
                (run_id,token,pid,birth,observed_epoch,reason)
                VALUES(?,?,?,?,?,'windows_process_exited')""",
                (run_id,token,pid,birth,now))
            result.append(int(run_id))
    return result

def history(store,limit=30):
    store.require_permission("company:manage")
    if type(limit) is not int or not 1<=limit<=100:
        raise ValueError("복구 감사 조회 1~100건")
    with store._connect() as con:
        initialize(con)
        rows=con.execute("""SELECT run_id,pid,observed_epoch,reason
            FROM aiwack_native_tick_recoveries ORDER BY id DESC LIMIT ?""",
            (limit,)).fetchall()
    return [dict(zip(("run_id","pid","observed_epoch","reason"),row)) for row in rows]
