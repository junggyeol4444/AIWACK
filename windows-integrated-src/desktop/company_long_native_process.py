"""Windows native process evidence for the recurring approved GGUF company batches.

A long company batch may launch existing subordinate staff/chief subprocess
calls. The original GUI Python/EXE process dying is NOT proof that the GGUF
children died. This feature never automatically restarts or closes those
children, creates successful model outputs, or alters old snapshots.

Use separate append-only tables rather than changing CHECK constraints
in pre-existing owner/chief PID tables and breaking user databases.
"""
from __future__ import annotations

import os
import time
from desktop.company_native_process_watch import _probe


def initialize(con):
    con.execute("""CREATE TABLE IF NOT EXISTS aiwack_long_batch_native_owners(
        attempt_id INTEGER NOT NULL PRIMARY KEY
            REFERENCES aiwack_long_operating_attempts(id),
        pid INTEGER NOT NULL CHECK(pid>0),
        process_birth INTEGER NOT NULL CHECK(process_birth>0),
        claimed_at_epoch INTEGER NOT NULL CHECK(claimed_at_epoch>0)
    )""")
    con.execute("""CREATE TABLE IF NOT EXISTS aiwack_long_batch_native_crashes(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        attempt_id INTEGER NOT NULL UNIQUE
            REFERENCES aiwack_long_operating_attempts(id),
        pid INTEGER NOT NULL,
        process_birth INTEGER NOT NULL,
        detected_at_epoch INTEGER NOT NULL,
        kernel_observation TEXT NOT NULL CHECK(kernel_observation='dead')
    )""")
    con.execute("""CREATE TABLE IF NOT EXISTS aiwack_long_batch_native_owner_closures(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        crash_id INTEGER NOT NULL UNIQUE REFERENCES aiwack_long_batch_native_crashes(id),
        owner_note TEXT NOT NULL CHECK(length(owner_note) BETWEEN 5 AND 200),
        closed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    )""")
    for table in ("aiwack_long_batch_native_owners",
                  "aiwack_long_batch_native_crashes",
                  "aiwack_long_batch_native_owner_closures"):
        for verb in ("UPDATE","DELETE"):
            con.execute("""CREATE TRIGGER IF NOT EXISTS %s_no_%s
                BEFORE %s ON %s BEGIN
                SELECT RAISE(ABORT,'Windows 장기 GGUF 프로세스 소유권 원본 불변'); END"""
                %(table,verb.lower(),verb,table))


def bind_in_transaction(con,attempt_id):
    if type(attempt_id) is not int or attempt_id<1:
        raise ValueError("Windows 장기 실제 모델 회차 번호 오류")
    if os.name!="nt":
        return {"bound":False,"reason":"not_windows"}
    observation,birth=_probe(os.getpid())
    if observation!="alive" or type(birth) is not int or birth<1:
        raise PermissionError("실제 Windows 커널 장기 GGUF 회차 PID/생성시각 확인 불가")
    initialize(con)
    con.execute("""INSERT INTO aiwack_long_batch_native_owners
        (attempt_id,pid,process_birth,claimed_at_epoch) VALUES(?,?,?,?)""",
        (attempt_id,os.getpid(),birth,int(time.time())))
    return {"bound":True,"attempt_id":attempt_id,
            "pid":os.getpid(),"process_birth":birth}


def _prove_dead(con,attempt_id,now,min_age):
    row=con.execute("""SELECT pid,process_birth,claimed_at_epoch
        FROM aiwack_long_batch_native_owners WHERE attempt_id=?""",
        (attempt_id,)).fetchone()
    if row is None:
        return {"verified_dead":False,"kernel_state":"not_bound"}
    pid,birth,claimed=row
    if now-claimed<min_age:
        return {"verified_dead":False,"kernel_state":"too_recent"}
    status,_=_probe(int(pid),int(birth))
    return {"verified_dead":status=="dead","kernel_state":status,
            "pid":int(pid),"original_process_birth":int(birth),
            "claim_age_seconds":now-claimed}


def inspect(store,*,min_age_seconds=180,limit=50):
    store.require_permission("company:manage")
    if type(limit) is not int or not 1<=limit<=100:
        raise ValueError("Windows 장기 회차 조회 1~100")
    if type(min_age_seconds) is not int or not 180<=min_age_seconds<=86400:
        raise ValueError("Windows 장기 중단 확인 180~86400초")
    stamp=int(time.time())
    with store._connect() as con:
        initialize(con)
        if not con.execute("""SELECT 1 FROM sqlite_master WHERE type='table'
            AND name='aiwack_long_operating_attempts'""").fetchone():
            return {"running":[],"recorded_crashes":[],
                    "os_is_windows":os.name=="nt",
                    "models_restarted":False}
        rows=con.execute("""SELECT id FROM aiwack_long_operating_attempts
            WHERE state='running' ORDER BY id LIMIT ?""",(limit,)).fetchall()
        running=[{"attempt_id":int(row[0]),
                  **_prove_dead(con,int(row[0]),stamp,min_age_seconds)}
                 for row in rows]
        crashes=con.execute("""SELECT c.id,c.attempt_id,
            CASE WHEN r.id IS NULL THEN 'unresolved' ELSE 'owner_closed' END
            FROM aiwack_long_batch_native_crashes c
            LEFT JOIN aiwack_long_batch_native_owner_closures r ON r.crash_id=c.id
            ORDER BY c.id DESC LIMIT ?""",(limit,)).fetchall()
    return {"os_is_windows":os.name=="nt","running":running,
            "recorded_crashes":[{"id":int(i),"attempt_id":int(a),
                                 "owner_resolution":s} for i,a,s in crashes],
            "models_restarted":False,
            "gui_crash_does_not_prove_model_child_exit":True,
            "24h_native_soak_verified":False}


def record_verified_crash(store,attempt_id,*,min_age_seconds=180):
    store.require_permission("company:manage")
    store.require_permission("agents:manage")
    if type(attempt_id) is not int or attempt_id<1:
        raise ValueError("Windows 장기 배치 중단 회차 번호 오류")
    if type(min_age_seconds) is not int or min_age_seconds<180:
        raise ValueError("Windows 커널 모델 중단 관측 최소 180초")
    if os.name!="nt":
        raise OSError("Windows 커널 프로세스 종료 관측 전용")
    with store._connect() as con:
        con.execute("BEGIN IMMEDIATE")
        initialize(con)
        row=con.execute("""SELECT state FROM aiwack_long_operating_attempts
            WHERE id=?""",(attempt_id,)).fetchone()
        if not row or row[0]!="running":
            raise ValueError("현재 미종료 실제 장기 GGUF 운영 회차가 아닙니다")
        proof=_prove_dead(con,attempt_id,int(time.time()),min_age_seconds)
        if not proof["verified_dead"]:
            raise PermissionError("실제 Windows 원 프로세스 종료가 확인되지 않음: "
                +proof["kernel_state"])
        prior=con.execute("""SELECT id FROM aiwack_long_batch_native_crashes
            WHERE attempt_id=?""",(attempt_id,)).fetchone()
        if prior:
            return {"crash_id":int(prior[0]),"already_recorded":True,
                    "owner_review_required":True}
        crash=int(con.execute("""INSERT INTO aiwack_long_batch_native_crashes
            (attempt_id,pid,process_birth,detected_at_epoch,kernel_observation)
            VALUES(?,?,?,?,'dead')""",
            (attempt_id,proof["pid"],proof["original_process_birth"],
             int(time.time()))).lastrowid)
    return {"crash_id":crash,"already_recorded":False,
            "original_gui_dead":True,
            "GGUF_children_verified_exited":False,
            "model_retried":False}


def close_after_owner_inspection(store,crash_id,note,*,owner_confirmed=False):
    store.require_permission("company:manage")
    store.require_permission("agents:manage")
    if type(crash_id) is not int or crash_id<1:
        raise ValueError("Windows 장기 GGUF 중단 감사 번호 오류")
    if type(note) is not str or not 5<=len(note.strip())<=200:
        raise ValueError("장기 모델 프로세스 관리자 중단 사유 5~200자")
    if owner_confirmed is not True:
        raise PermissionError("자식 GGUF 프로세스 종료/모델 lease 관리자 확인 필요")
    if os.name!="nt":raise OSError("Windows 중단 관측 감사 전용")
    with store._connect() as con:
        initialize(con)
        row=con.execute("""SELECT c.attempt_id,c.pid,c.process_birth
            FROM aiwack_long_batch_native_crashes c
            WHERE c.id=?""",(crash_id,)).fetchone()
        if not row:raise ValueError("원본 Windows 장기 프로세스 종료 감사 없음")
        attempt,pid,birth=row
        if con.execute("""SELECT 1 FROM aiwack_long_batch_native_owner_closures
            WHERE crash_id=?""",(crash_id,)).fetchone():
            raise ValueError("해당 Windows 장기 모델 중단 기록 이미 확인됨")
        if _probe(int(pid),int(birth))[0]!="dead":
            raise PermissionError("원래 커널 프로세스 종료 확인 실패")
    from desktop.company_long_running_batch import close_after_owner_inspection as old_close
    response=old_close(store,int(attempt),note,owner_confirmed=True)
    with store._connect() as con:
        con.execute("BEGIN IMMEDIATE")
        initialize(con)
        con.execute("""INSERT INTO aiwack_long_batch_native_owner_closures
            (crash_id,owner_note) VALUES(?,?)""",(crash_id,note.strip()))
    return {"crash_id":crash_id,"attempt_id":int(attempt),
            "original_long_batch_close":response,
            "model_reexecuted":False,"payments_replayed":False}
