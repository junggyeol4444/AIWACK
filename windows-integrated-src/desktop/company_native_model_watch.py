"""Windows GUI 소유자 프로세스가 실제 종료된 GGUF 실행 감사의 안전한 정리.

PID+Windows 커널 생성시각을 함께 확인한다. 모델 하위 프로세스 생존은
확정할 수 없으므로 기존 lease를 지우지 않고 자동 재실행도 하지 않는다.
"""
from __future__ import annotations

import os
import time
from desktop.stage87_90_management import stopped


def initialize(con):
    from desktop.company_native_process_watch import initialize as init_sessions
    init_sessions(con)
    con.execute("""CREATE TABLE IF NOT EXISTS aiwack_native_model_owners (
        run_id INTEGER PRIMARY KEY REFERENCES aiwack_autopilot_model_runs(id),
        session_token TEXT NOT NULL REFERENCES aiwack_native_sessions(token))""")
    con.execute("""CREATE TABLE IF NOT EXISTS aiwack_native_model_exit_audit (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        run_id INTEGER NOT NULL UNIQUE REFERENCES aiwack_autopilot_model_runs(id),
        task_id INTEGER NOT NULL REFERENCES company_tasks(id),
        session_token TEXT NOT NULL, pid INTEGER NOT NULL, birth INTEGER NOT NULL,
        observed_epoch INTEGER NOT NULL,
        subprocess_verified_stopped INTEGER NOT NULL DEFAULT 0
          CHECK(subprocess_verified_stopped=0))""")
    con.execute("""CREATE TABLE IF NOT EXISTS aiwack_native_model_lease_release (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        run_id INTEGER NOT NULL UNIQUE REFERENCES aiwack_autopilot_model_runs(id),
        owner_note TEXT NOT NULL CHECK(length(owner_note) BETWEEN 5 AND 200),
        owner_attested_subprocess_inspected INTEGER NOT NULL CHECK(owner_attested_subprocess_inspected=1),
        released_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)""")
    for action in ("UPDATE","DELETE"):
        con.execute(f"""CREATE TRIGGER IF NOT EXISTS aiwack_native_model_release_no_{action.lower()}
            BEFORE {action} ON aiwack_native_model_lease_release
            BEGIN SELECT RAISE(ABORT,'모델 잠금 해제 확인 감사 수정·삭제 금지'); END""")
    for action in ("UPDATE","DELETE"):
        con.execute(f"""CREATE TRIGGER IF NOT EXISTS aiwack_native_model_exit_no_{action.lower()}
            BEFORE {action} ON aiwack_native_model_exit_audit
            BEGIN SELECT RAISE(ABORT,'실제 GGUF 종료 관측 감사 수정·삭제 금지'); END""")


def bind(con, run_id, session_token):
    from desktop.company_native_process_watch import _probe
    if type(run_id) is not int or run_id <= 0:
        raise ValueError("실제 모델 실행 번호 오류")
    if not isinstance(session_token,str) or len(session_token)!=32:
        raise ValueError("GUI 프로세스 토큰 오류")
    initialize(con)
    row=con.execute("SELECT pid,birth FROM aiwack_native_sessions WHERE token=?",
                    (session_token,)).fetchone()
    if not row or _probe(int(row[0]),int(row[1]))[0]!="alive":
        raise PermissionError("실행 중인 Windows GUI 소유 프로세스를 확인하지 못했습니다.")
    con.execute("""INSERT INTO aiwack_native_model_owners(run_id,session_token)
        VALUES(?,?)""",(run_id,session_token))


def recover(store,minimum_age=180):
    store.require_permission("company:manage")
    if type(minimum_age) is not int or minimum_age < 180:
        raise ValueError("실제 GGUF 프로세스 종료 판정은 최소 180초 이후")
    if os.name!="nt":
        return []
    from desktop import company_autopilot
    from desktop.company_native_process_watch import _probe
    company_autopilot.initialize(store)
    now=int(time.time())
    result=[]
    with store._connect() as con:
        con.execute("BEGIN IMMEDIATE")
        initialize(con)
        if stopped(con):
            return result
        rows=con.execute("""SELECT r.id,r.task_id,s.token,s.pid,s.birth
            FROM aiwack_autopilot_model_runs r
            JOIN aiwack_autopilot_model_leases l ON l.run_id=r.id
            JOIN aiwack_native_model_owners o ON o.run_id=r.id
            JOIN aiwack_native_sessions s ON s.token=o.session_token
            WHERE r.state='running' AND l.started_epoch<=?
            ORDER BY r.id LIMIT 30""",(now-minimum_age,)).fetchall()
        for run_id,task_id,token,pid,birth in rows:
            if _probe(int(pid),int(birth))[0]!="dead":
                continue
            updated=con.execute("""UPDATE aiwack_autopilot_model_runs
                SET state='failed',error_kind='WindowsOwnerProcessExited',
                    finished_at=CURRENT_TIMESTAMP
                WHERE id=? AND state='running'""",(run_id,)).rowcount
            if updated!=1:
                continue
            con.execute("""INSERT INTO aiwack_native_model_exit_audit
                (run_id,task_id,session_token,pid,birth,observed_epoch)
                VALUES(?,?,?,?,?,?)""",(run_id,task_id,token,pid,birth,now))
            has_queue=con.execute("""SELECT 1 FROM sqlite_master
                WHERE type='table' AND name='aiwack_owner_model_queue'""").fetchone()
            if has_queue:
                queue=con.execute("""SELECT id FROM aiwack_owner_model_queue
                    WHERE task_id=? AND state='running'""",(task_id,)).fetchone()
                if queue:
                    con.execute("""UPDATE aiwack_owner_model_queue
                        SET state='failed',error_kind='WindowsOwnerProcessExited',
                            finished_at=CURRENT_TIMESTAMP WHERE id=?""",(queue[0],))
                    con.execute("""INSERT INTO aiwack_owner_model_queue_events
                        (queue_id,event_kind,detail)
                        VALUES(?,'owner_process_exited','WindowsOwnerProcessExited')""",
                        (queue[0],))
            result.append({"run_id":int(run_id),"task_id":int(task_id),
                           "gui_process_confirmed_dead":True,
                           "model_subprocess_confirmed_dead":False,
                           "lease_released":False,"model_retried":False})
    return result


def history(store,limit=30):
    store.require_permission("company:manage")
    if type(limit) is not int or not 1<=limit<=100:
        raise ValueError("종료 확인 감사 조회는 1~100건")
    with store._connect() as con:
        initialize(con)
        rows=con.execute("""SELECT run_id,task_id,pid,observed_epoch
            FROM aiwack_native_model_exit_audit ORDER BY id DESC LIMIT ?""",
            (limit,)).fetchall()
    return [{"run_id":int(a),"task_id":int(b),"pid":int(c),
             "observed_epoch":int(d),"model_subprocess_confirmed_dead":False,
             "lease_released":False} for a,b,c,d in rows]


def release_after_owner_inspection(store,run_id,owner_note,*,owner_confirmed=False):
    """관리자가 모델 하위 프로세스를 직접 확인한 후에만 기존 실패 lease를 해제."""
    store.require_permission("company:manage")
    if type(run_id) is not int or run_id<=0:
        raise ValueError("실제 모델 실행 번호 오류")
    if owner_confirmed is not True:
        raise PermissionError("관리자의 하위 GGUF 프로세스 직접 확인이 필요합니다.")
    if not isinstance(owner_note,str) or not 5<=len(owner_note.strip())<=200:
        raise ValueError("모델 프로세스 확인 사유는 5~200자")
    if os.name!="nt":
        raise OSError("Windows 커널 확인 기능만 지원합니다.")
    from desktop.company_native_process_watch import _probe
    with store._connect() as con:
        con.execute("BEGIN IMMEDIATE")
        initialize(con)
        row=con.execute("""SELECT a.pid,a.birth,r.state,r.error_kind,l.task_id
            FROM aiwack_native_model_exit_audit a
            JOIN aiwack_autopilot_model_runs r ON r.id=a.run_id
            JOIN aiwack_autopilot_model_leases l ON l.run_id=a.run_id
            WHERE a.run_id=?""",(run_id,)).fetchone()
        if not row or row[2]!="failed" or row[3]!="WindowsOwnerProcessExited":
            raise PermissionError("Windows 종료 확인된 실패 모델 감사 및 해당 잠금이 없습니다.")
        if _probe(int(row[0]),int(row[1]))[0]!="dead":
            raise PermissionError("원래 Windows 소유 프로세스 종료를 재확인하지 못했습니다.")
        if con.execute("DELETE FROM aiwack_autopilot_model_leases WHERE run_id=?",
                       (run_id,)).rowcount!=1:
            raise RuntimeError("잠금 소유권이 변경됐습니다.")
        con.execute("""INSERT INTO aiwack_native_model_lease_release
            (run_id,owner_note,owner_attested_subprocess_inspected)
            VALUES(?,?,1)""",(run_id,owner_note.strip()))
    return {"run_id":run_id,"lease_released":True,"model_retried":False,
            "subprocess_inspected_by_owner":True,
            "subprocess_stopped_independently_verified":False}
