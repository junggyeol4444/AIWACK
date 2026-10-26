"""장기 AIWACK 회사 운영: 소유자 명시 허용 기반 실제 GGUF 승인업무 자동 배치.

현재 로그인한 네이티브 GUI의 tick에 종속된다. Windows 서비스나
24시간 실제 무중단 보장이 아니다. 본 모듈은 기존 개별 관리자 승인
대기열과 부서장 전달 승인 대기열만 한 회차씩 실행한다.

안전 규칙
- 원래 자동운영+실제 GGUF 동의 및 별도 장기 배치 동의 세 개 필수
- 기존 영속 실행 회차/실제 모델 실패/잠금 불확실 시 재실행 금지
- 각 배치의 due를 먼저 단일 SQLite 트랜잭션에서 선점, 외부 모델
  호출 시에는 DB 잠금을 풀고 원본 runtime에 실제 모델 소유권 위임
- 모델/재무/고객/최종 품질 관리자 승인 자동 생성 금지
- 이전 프로세스 중단된 running 회차는 소유자가 확인해 닫을 때까지 보존
"""
from __future__ import annotations

import threading
import time
from desktop.stage87_90_management import stopped

MIN_INTERVAL=900
MAX_INTERVAL=86400


def initialize(con):
    con.execute("""CREATE TABLE IF NOT EXISTS aiwack_long_operating_policy(
        id INTEGER PRIMARY KEY CHECK(id=1),
        enabled INTEGER NOT NULL DEFAULT 0 CHECK(enabled IN (0,1)),
        interval_seconds INTEGER NOT NULL DEFAULT 3600
            CHECK(interval_seconds BETWEEN 900 AND 86400),
        max_staff INTEGER NOT NULL DEFAULT 5 CHECK(max_staff BETWEEN 1 AND 30),
        max_chief INTEGER NOT NULL DEFAULT 5 CHECK(max_chief BETWEEN 1 AND 10),
        next_due_epoch INTEGER NOT NULL DEFAULT 0,
        owner_note TEXT NOT NULL DEFAULT ''
    )""")
    con.execute("""INSERT OR IGNORE INTO aiwack_long_operating_policy(id)
        VALUES(1)""")
    con.execute("""CREATE TABLE IF NOT EXISTS aiwack_long_operating_attempts(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        due_epoch INTEGER NOT NULL UNIQUE,
        state TEXT NOT NULL DEFAULT 'running'
            CHECK(state IN ('running','finished','cancelled','failed')),
        operating_round_id INTEGER REFERENCES aiwack_owner_operating_rounds(id),
        actually_invoked_staff INTEGER NOT NULL DEFAULT 0,
        actually_saved_chief INTEGER NOT NULL DEFAULT 0,
        exit_reason TEXT NOT NULL DEFAULT '',
        started_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        finished_at TEXT
    )""")
    con.execute("""CREATE TABLE IF NOT EXISTS aiwack_long_operating_events(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        attempt_id INTEGER NOT NULL REFERENCES aiwack_long_operating_attempts(id),
        kind TEXT NOT NULL CHECK(kind IN
            ('claimed','finished','failed','cancelled','owner_closed')),
        detail TEXT NOT NULL DEFAULT '',
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(attempt_id,kind)
    )""")
    for action in ("UPDATE","DELETE"):
        con.execute("""CREATE TRIGGER IF NOT EXISTS aiwack_long_operating_events_no_%s
            BEFORE %s ON aiwack_long_operating_events
            BEGIN SELECT RAISE(ABORT,'장기 실 GGUF 운영 감사 이벤트 변경 금지'); END"""
            %(action.lower(),action))


def _authorizations(con):
    if stopped(con):return False
    if not con.execute("""SELECT 1 FROM sqlite_master WHERE type='table'
        AND name='aiwack_autopilot_settings'""").fetchone():
        return False
    a=con.execute("""SELECT a.enabled,b.enabled FROM
        aiwack_autopilot_settings a CROSS JOIN aiwack_autopilot_model_policy b
        WHERE a.id=1 AND b.id=1""").fetchone()
    return bool(a and a[0] and a[1])


def _active(con):
    row=con.execute("""SELECT enabled FROM aiwack_long_operating_policy
        WHERE id=1""").fetchone()
    return bool(row and row[0] and _authorizations(con))


def configure(store,enabled,*,interval_minutes=60,max_staff=5,max_chief=5,note=""):
    store.require_permission("company:manage")
    store.require_permission("agents:manage")
    if type(enabled) is not bool:raise ValueError("장기 GGUF 동의 값 오류")
    if type(interval_minutes) is not int or not 15<=interval_minutes<=1440:
        raise ValueError("장기 GGUF 실행 주기 15~1440분")
    if type(max_staff) is not int or not 1<=max_staff<=30:
        raise ValueError("주기별 승인 직원 업무 수 1~30")
    if type(max_chief) is not int or not 1<=max_chief<=10:
        raise ValueError("주기별 부서장 승인 총괄 회수 수 1~10")
    if type(note) is not str or not 5<=len(note.strip())<=200:
        raise ValueError("장기 AI 운영 관리자 정책 이유 5~200자")
    from desktop.company_autopilot import initialize as init_auto
    init_auto(store)
    with store._connect() as con:
        con.execute("BEGIN IMMEDIATE")
        initialize(con)
        if enabled and not _authorizations(con):
            raise PermissionError("회사 자동 운영 및 실제 GGUF 별도 허용 두 개가 먼저 필요합니다.")
        if enabled and con.execute("""SELECT 1 FROM aiwack_long_operating_attempts
            WHERE state='running' LIMIT 1""").fetchone():
            raise PermissionError("미종료 실 GGUF 장기 회차 확인 없이 재활성화 금지")
        con.execute("""UPDATE aiwack_long_operating_policy SET
            enabled=?,interval_seconds=?,max_staff=?,max_chief=?,
            next_due_epoch=?,owner_note=? WHERE id=1""",
            (int(enabled),interval_minutes*60,max_staff,max_chief,
             int(time.time()) if enabled else 0,note.strip()))
    return status(store)


def status(store):
    store.require_permission("company:manage")
    from desktop.company_autopilot import initialize as init_auto
    init_auto(store)
    with store._connect() as con:
        initialize(con)
        record=con.execute("""SELECT enabled,interval_seconds,max_staff,max_chief,
            next_due_epoch,owner_note FROM aiwack_long_operating_policy
            WHERE id=1""").fetchone()
        pending=con.execute("""SELECT COUNT(*) FROM aiwack_long_operating_attempts
            WHERE state='running'""").fetchone()[0]
        enabled_now=_active(con)
    return {"enabled":bool(record[0]),
            "interval_minutes":record[1]//60,"max_staff":record[2],
            "max_chief":record[3],"next_due_epoch":record[4],
            "owner_note":record[5],
            "all_three_permissions_active":enabled_now,
            "unfinished_actual_model_batches":int(pending),
            "automatic_owner_final_approval":False,
            "unattended_24h_windows_verified":False}


def _ready(con):
    from desktop.company_owner_operating_rounds import _evidence
    # Existing approved queue / forwarded head selection is read-only.
    evidence,_=_evidence(con)
    return bool(evidence["first_ready_employee_task"] is not None
                or evidence["chief_forwarded_artifacts"])


def due(store,*,now=None):
    store.require_permission("company:manage")
    stamp=int(time.time()) if now is None else now
    if type(stamp) is not int or stamp<0:raise ValueError("실 GGUF 자동 회차 시각 오류")
    with store._connect() as con:
        if not con.execute("""SELECT 1 FROM sqlite_master
            WHERE type='table' AND name='aiwack_long_operating_policy'""").fetchone():
            return False
        row=con.execute("""SELECT enabled,next_due_epoch FROM
            aiwack_long_operating_policy WHERE id=1""").fetchone()
        if not row or not row[0] or row[1]>stamp or not _authorizations(con):
            return False
        if con.execute("""SELECT 1 FROM aiwack_long_operating_attempts
            WHERE state='running' LIMIT 1""").fetchone():
            return False
        return _ready(con)


def _still_allowed(store):
    with store._connect() as con:
        return _active(con)


def run_due(store,*,cancel=None,now=None):
    """A single real-GGUF operating batch on a claimed local due time."""
    store.require_permission("company:manage")
    store.require_permission("agents:manage")
    stamp=int(time.time()) if now is None else now
    if type(stamp) is not int or stamp<0:raise ValueError("실 GGUF 자동 회차 시각 오류")
    if cancel is not None and cancel.is_set():
        raise InterruptedError("소유자 GGUF 장기 운영 시작 취소")
    with store._connect() as con:
        con.execute("BEGIN IMMEDIATE")
        initialize(con)
        policy=con.execute("""SELECT enabled,interval_seconds,max_staff,max_chief,
            next_due_epoch,owner_note FROM aiwack_long_operating_policy
            WHERE id=1""").fetchone()
        if not policy or not _active(con):
            return {"executed":False,"reason":"not_authorized"}
        if policy[4]>stamp:
            return {"executed":False,"reason":"not_due"}
        if con.execute("""SELECT 1 FROM aiwack_long_operating_attempts
            WHERE state='running' LIMIT 1""").fetchone():
            return {"executed":False,"reason":"previous_process_unresolved"}
        if not _ready(con):
            # Nothing is claimed; no fabricated model run.
            return {"executed":False,"reason":"no_owner_approved_ready_tasks"}
        con.execute("""UPDATE aiwack_long_operating_policy
            SET next_due_epoch=? WHERE id=1""",(stamp+policy[1],))
        attempt_id=int(con.execute("""INSERT INTO aiwack_long_operating_attempts
            (due_epoch,state) VALUES(?,'running')""",(stamp,)).lastrowid)
        con.execute("""INSERT INTO aiwack_long_operating_events
            (attempt_id,kind) VALUES(?,'claimed')""",(attempt_id,))
    signal=cancel if cancel is not None else threading.Event()
    stop=threading.Event()
    def watch_permissions():
        while not stop.wait(0.5):
            try:still=_still_allowed(store)
            except Exception:still=False
            if not still:
                signal.set()
                break
    watcher=threading.Thread(target=watch_permissions,
            name="AIWACK-approved-longrun-consent",daemon=True)
    watcher.start()
    result=None
    state="failed"
    error=""
    try:
        if signal.is_set() or not _still_allowed(store):
            raise InterruptedError("실 GGUF 장기 운영 동의 해제")
        from desktop.company_owner_operating_rounds import run as run_existing
        result=run_existing(store,max_employee_jobs=int(policy[2]),
            max_chief_reviews=int(policy[3]),owner_note=policy[5],cancel=signal)
        if signal.is_set() or not _still_allowed(store):
            state="cancelled"
        else:
            state="finished"
        return {"executed":bool(result.get("executed")),
            "long_attempt_id":attempt_id,
            "actual_operating_round_id":result.get("round_id"),
            "state":state,
            "staff_model_jobs":int(result.get("staff_calls_started",0)),
            "actual_chief_reports":int(result.get("chief_reports_saved",0)),
            "owner_review_required":True,"automatic_model_retry":False,
            "independent_real_revenue_verified":False}
    except Exception as exc:
        state="cancelled" if isinstance(exc,InterruptedError) else "failed"
        error=type(exc).__name__[:70]
        raise
    finally:
        stop.set()
        watcher.join(timeout=2)
        with store._connect() as con:
            con.execute("BEGIN IMMEDIATE")
            # Write outcome even on policy revocation; no model replay.
            updated=con.execute("""UPDATE aiwack_long_operating_attempts
                SET state=?,operating_round_id=?,
                    actually_invoked_staff=?,actually_saved_chief=?,
                    exit_reason=?,finished_at=CURRENT_TIMESTAMP
                WHERE id=? AND state='running'""",
                (state,result.get("round_id") if result else None,
                 int(result.get("staff_calls_started",0)) if result else 0,
                 int(result.get("chief_reports_saved",0)) if result else 0,
                 error or state,attempt_id)).rowcount
            if updated==1:
                con.execute("""INSERT INTO aiwack_long_operating_events
                    (attempt_id,kind,detail) VALUES(?,?,?)""",
                    (attempt_id,state,error))


def history(store,limit=50):
    store.require_permission("company:manage")
    if type(limit) is not int or not 1<=limit<=100:
        raise ValueError("실 GGUF 장기 회차 감사 1~100건")
    with store._connect() as con:
        initialize(con)
        records=con.execute("""SELECT id,due_epoch,state,operating_round_id,
            actually_invoked_staff,actually_saved_chief,exit_reason,
            started_at,finished_at FROM aiwack_long_operating_attempts
            ORDER BY id DESC LIMIT ?""",(limit,)).fetchall()
    fields=("id","due_epoch","state","real_operating_round_id",
            "actual_staff_jobs","actual_chief_reports",
            "exit_reason","started_at","finished_at")
    return [dict(zip(fields,row)) for row in records]


def close_after_owner_inspection(store,attempt_id,note,*,owner_confirmed=False):
    """Never release unresolved model locks or manufacture missing results."""
    store.require_permission("company:manage")
    store.require_permission("agents:manage")
    if type(attempt_id) is not int or attempt_id<1:
        raise ValueError("미종료 장기 GGUF 회차 번호 오류")
    if owner_confirmed is not True:
        raise PermissionError("원본 프로세스·모델 호출 관리자 직접 확인 필수")
    if type(note) is not str or not 5<=len(note.strip())<=200:
        raise ValueError("장기 중단 회차 감사 사유 5~200자")
    with store._connect() as con:
        con.execute("BEGIN IMMEDIATE")
        initialize(con)
        row=con.execute("""SELECT state FROM aiwack_long_operating_attempts
            WHERE id=?""",(attempt_id,)).fetchone()
        if not row or row[0]!="running":
            raise ValueError("존재하지 않거나 종료된 장기 GGUF 실행")
        if con.execute("""SELECT 1 FROM ai_model_call_history
            WHERE status='running' LIMIT 1""").fetchone():
            raise PermissionError("실제 GGUF 모델 호출 미종료")
        for table in ("aiwack_owner_operating_rounds",
                      "aiwack_approved_model_batches",
                      "aiwack_head_chief_batches"):
            if con.execute("""SELECT 1 FROM sqlite_master
                WHERE type='table' AND name=?""",(table,)).fetchone() and \
               con.execute("SELECT 1 FROM "+table+" WHERE state='running' LIMIT 1").fetchone():
                raise PermissionError("기존 실행/모델 잠금 중단 확인 필요: "+table)
        if con.execute("""SELECT 1 FROM sqlite_master WHERE type='table'
            AND name='aiwack_chief_review_leases'""").fetchone() and \
           con.execute("SELECT 1 FROM aiwack_chief_review_leases LIMIT 1").fetchone():
            raise PermissionError("총괄 모델 lease가 아직 있습니다")
        if con.execute("""UPDATE aiwack_long_operating_attempts
            SET state='cancelled',exit_reason='owner_inspected_interruption',
                finished_at=CURRENT_TIMESTAMP
            WHERE id=? AND state='running'""",(attempt_id,)).rowcount!=1:
            raise RuntimeError("장기 GGUF 회차 소유권 변경")
        con.execute("""INSERT INTO aiwack_long_operating_events
            (attempt_id,kind,detail) VALUES(?,'owner_closed',?)""",
            (attempt_id,note.strip()))
    return {"attempt_id":attempt_id,"state":"cancelled",
            "real_models_retried":False,
            "previous_data_and_audit_preserved":True}
