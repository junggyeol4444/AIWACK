"""Windows process-bound, non-replaying continuation guard for genuine GGUF rounds.

Bind each manually started owner operating round/chief handoff batch to the
actual kernel process ID *and creation time*. On restart, distinguish a dead
original process from PID reuse or inaccessible process metadata. The guard
never starts models, changes user settings, or removes existing run evidence.

Recording a suspected crash is NOT authorization to release model leases:
the spawned GGUF subprocess may survive its GUI parent. Only a separate
owner-confirmed action that passes original queue close gates may mark the
top-level round interrupted. Existing model attempts remain untouched.
"""
from __future__ import annotations

import os
import sqlite3
import time

from desktop.company_native_process_watch import _probe
from desktop.stage87_90_management import stopped

_KINDS={
    "operating":("aiwack_owner_operating_rounds","state"),
    "chief":("aiwack_head_chief_batches","state"),
}
_MIN_AGE=180


def initialize(con):
    con.execute("""CREATE TABLE IF NOT EXISTS aiwack_native_round_owners(
        kind TEXT NOT NULL CHECK(kind IN ('operating','chief')),
        run_id INTEGER NOT NULL CHECK(run_id>0),
        pid INTEGER NOT NULL CHECK(pid>0),
        process_birth INTEGER NOT NULL CHECK(process_birth>0),
        claimed_epoch INTEGER NOT NULL CHECK(claimed_epoch>0),
        PRIMARY KEY(kind,run_id))""")
    con.execute("""CREATE TABLE IF NOT EXISTS aiwack_native_round_interruptions(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        kind TEXT NOT NULL CHECK(kind IN ('operating','chief')),
        run_id INTEGER NOT NULL CHECK(run_id>0),
        pid INTEGER NOT NULL,
        process_birth INTEGER NOT NULL,
        observed_epoch INTEGER NOT NULL,
        observed_state TEXT NOT NULL CHECK(observed_state='dead'),
        reason TEXT NOT NULL CHECK(reason='windows_process_exited'),
        UNIQUE(kind,run_id))""")
    con.execute("""CREATE TABLE IF NOT EXISTS aiwack_native_round_owner_resolutions(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        interruption_id INTEGER NOT NULL UNIQUE
            REFERENCES aiwack_native_round_interruptions(id),
        owner_note TEXT NOT NULL CHECK(length(owner_note) BETWEEN 5 AND 200),
        action TEXT NOT NULL CHECK(action='closed_without_replay'),
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)""")
    for table in ("aiwack_native_round_owners",
                  "aiwack_native_round_interruptions",
                  "aiwack_native_round_owner_resolutions"):
        for op in ("UPDATE","DELETE"):
            con.execute("""CREATE TRIGGER IF NOT EXISTS %s_no_%s
                BEFORE %s ON %s BEGIN
                SELECT RAISE(ABORT,'Windows GGUF 회차 소유권·복구 감사 원본 변경 금지'); END"""
                %(table,op.lower(),op,table))


def bind_in_transaction(con,kind,run_id):
    """Called in the same SQLite transaction that claims an actual new round."""
    if kind not in _KINDS or type(run_id) is not int or run_id<=0:
        raise ValueError("회차 소유권 종류/번호 오류")
    # On non-Windows developer systems retain current original behavior;
    # only a genuine Windows kernel observation creates an owner binding.
    if os.name!="nt":
        return False
    state,birth=_probe(os.getpid())
    if state!="alive" or type(birth) is not int or birth<1:
        raise PermissionError("실제 Windows GUI 커널 프로세스 소유권 확인 실패")
    initialize(con)
    con.execute("""INSERT INTO aiwack_native_round_owners
        (kind,run_id,pid,process_birth,claimed_epoch) VALUES(?,?,?,?,?)""",
        (kind,run_id,os.getpid(),birth,int(time.time())))
    return True


def _aged_dead(con,kind,run_id,now,age):
    row=con.execute("""SELECT pid,process_birth,claimed_epoch
        FROM aiwack_native_round_owners WHERE kind=? AND run_id=?""",
        (kind,run_id)).fetchone()
    if row is None:
        return {"state":"not_kernel_bound","verified":False}
    pid,birth,claimed=row
    if now-claimed<age:
        return {"state":"too_recent","verified":False}
    status,_=_probe(int(pid),int(birth))
    # Reused PID is "dead" only if the original creation time differs.
    return {"state":status,"verified":status=="dead",
            "pid":int(pid),"original_creation_time":int(birth),
            "claimed_epoch":int(claimed)}


def inspect(store,*,min_age_seconds=180,limit=50):
    """Read-only Windows restart inventory, including unknown PID evidence."""
    store.require_permission("company:manage")
    if type(min_age_seconds) is not int or not 180<=min_age_seconds<=86400:
        raise ValueError("Windows 모델 회차 최소 확인 시각 180~86400초")
    if type(limit) is not int or not 1<=limit<=100:
        raise ValueError("조회할 미종료 회차 1~100건")
    now=int(time.time())
    with store._connect() as con:
        initialize(con)
        candidates=[]
        for kind,(table,_) in _KINDS.items():
            if not con.execute("""SELECT 1 FROM sqlite_master
                WHERE type='table' AND name=?""",(table,)).fetchone():
                continue
            for (rid,) in con.execute(f"""SELECT id FROM {table}
                WHERE state='running' ORDER BY id LIMIT ?""",(limit,)).fetchall():
                proof=_aged_dead(con,kind,int(rid),now,min_age_seconds)
                candidates.append({"kind":kind,"run_id":int(rid),**proof})
                if len(candidates)>=limit:break
            if len(candidates)>=limit:break
        pending=con.execute("""SELECT i.id,i.kind,i.run_id,
            CASE WHEN r.id IS NULL THEN 'pending' ELSE 'owner_closed' END
            FROM aiwack_native_round_interruptions i
            LEFT JOIN aiwack_native_round_owner_resolutions r
               ON r.interruption_id=i.id
            ORDER BY i.id DESC LIMIT ?""",(limit,)).fetchall()
    return {"os_is_windows":os.name=="nt","unclosed_rounds":candidates,
            "interruption_audits":[dict(zip(
                ("id","kind","run_id","owner_resolution_state"),row)) for row in pending],
            "models_or_payments_replayed":False,"24h_soak_verified":False}


def record_dead_process(store,kind,run_id,*,min_age_seconds=180):
    """Persist evidence of a dead *GUI process*, not of a dead model child."""
    store.require_permission("company:manage")
    store.require_permission("agents:manage")
    if kind not in _KINDS or type(run_id) is not int or run_id<=0:
        raise ValueError("관측할 Windows 실행 회차 오류")
    if type(min_age_seconds) is not int or min_age_seconds<180:
        raise ValueError("프로세스 중단 판별 최소 180초")
    if os.name!="nt":
        raise OSError("실제 Windows 커널 종료 확인만 기록할 수 있습니다")
    table,_=_KINDS[kind]
    now=int(time.time())
    with store._connect() as con:
        con.execute("BEGIN IMMEDIATE")
        initialize(con)
        if stopped(con):raise PermissionError("비상정지 중에는 복구 기록을 변경하지 않습니다")
        if not con.execute(f"SELECT 1 FROM {table} WHERE id=? AND state='running'",
                           (run_id,)).fetchone():
            raise ValueError("원래 실행 회차가 미종료 상태가 아닙니다")
        proof=_aged_dead(con,kind,run_id,now,min_age_seconds)
        if not proof["verified"]:
            raise PermissionError("Windows 원 프로세스 종료 확인 불가: "+proof["state"])
        old=con.execute("""SELECT id FROM aiwack_native_round_interruptions
            WHERE kind=? AND run_id=?""",(kind,run_id)).fetchone()
        if old:
            return {"interruption_id":int(old[0]),"already_recorded":True,
                    "owner_review_required":True,"model_restarted":False}
        rid=int(con.execute("""INSERT INTO aiwack_native_round_interruptions
            (kind,run_id,pid,process_birth,observed_epoch,observed_state,reason)
            VALUES(?,?,?,?,?,'dead','windows_process_exited')""",
            (kind,run_id,proof["pid"],proof["original_creation_time"],
             now)).lastrowid)
    return {"interruption_id":rid,"already_recorded":False,
            "original_process_verified_dead":True,
            "subprocesses_independently_verified_dead":False,
            "owner_review_required":True,"model_restarted":False}


def close_after_owner_verification(store,interruption_id,note,*,owner_confirmed=False):
    """Use old owner close gates; don't bypass any real GGUF model lease."""
    store.require_permission("company:manage")
    store.require_permission("agents:manage")
    if type(interruption_id) is not int or interruption_id<=0:
        raise ValueError("Windows 프로세스 중단 감사 번호 오류")
    if type(note) is not str or not 5<=len(note.strip())<=200:
        raise ValueError("소유자 직접 확인 사유 5~200자")
    if owner_confirmed is not True:
        raise PermissionError("GGUF 자식 프로세스 종료·대기 원장 관리자 직접 확인 필수")
    if os.name!="nt":
        raise OSError("Windows 소유 프로세스 확인 전용")
    with store._connect() as con:
        initialize(con)
        row=con.execute("""SELECT kind,run_id,pid,process_birth
            FROM aiwack_native_round_interruptions WHERE id=?""",
            (interruption_id,)).fetchone()
        if not row:raise ValueError("실제 Windows 프로세스 종료 감사가 없습니다")
        kind,run_id,pid,birth=row
        if con.execute("""SELECT 1 FROM aiwack_native_round_owner_resolutions
            WHERE interruption_id=?""",(interruption_id,)).fetchone():
            raise ValueError("이미 확인 종료된 Windows 프로세스 감사")
        if _probe(int(pid),int(birth))[0]!="dead":
            raise PermissionError("원래 Windows 소유 프로세스가 종료됐는지 재확인 불가")
    # Existing conservative close functions check every outstanding model
    # call / lease, and NEVER rerun, delete, or release child-model claims.
    if kind=="operating":
        from desktop.company_owner_operating_rounds import close_after_owner_inspection
    else:
        from desktop.company_head_chief_handoff_queue import close_after_owner_inspection
    closed=close_after_owner_inspection(
        store,int(run_id),note,owner_confirmed=True)
    with store._connect() as con:
        con.execute("BEGIN IMMEDIATE")
        initialize(con)
        if con.execute("""SELECT 1 FROM aiwack_native_round_owner_resolutions
            WHERE interruption_id=?""",(interruption_id,)).fetchone():
            raise ValueError("관리자 복구 감사 이중 기록")
        con.execute("""INSERT INTO aiwack_native_round_owner_resolutions
            (interruption_id,owner_note,action)
            VALUES(? ,?,'closed_without_replay')""",
            (interruption_id,note.strip()))
    return {"interruption_id":interruption_id,"kind":kind,
            "run_id":int(run_id),"owner_closed":True,
            "models_reinvoked":False,"external_payments_replayed":False,
            "original_close_audit":closed}
