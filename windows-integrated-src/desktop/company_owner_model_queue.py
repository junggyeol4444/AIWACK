"""관리자가 이미 승인한 실제 직원→총괄 GGUF 업무의 SQLite 영속 실행 대기열.

대기열 등록은 별도 관리자 행위이고 실제 모델 실행은 기존 이중 opt-in
(company_autopilot 설정 + 모델 정책)으로만 허용한다. 실패/중단 업무는
절대 자동 재시도하지 않는다. 외부 결제·전송·게시·결과물 승인 없음.
"""
from __future__ import annotations

from desktop.stage87_90_management import stopped


def _id(value):
    if type(value) is not int or value < 1:
        raise ValueError("업무/대기열 번호는 양의 정수여야 합니다.")
    return value


def _note(value):
    if not isinstance(value, str) or not 5 <= len(value.strip()) <= 200:
        raise ValueError("관리자 사유는 5~200자여야 합니다.")
    return value.strip()


def initialize(con):
    con.execute("""CREATE TABLE IF NOT EXISTS aiwack_owner_model_queue (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        task_id INTEGER NOT NULL UNIQUE REFERENCES company_tasks(id),
        owner_note TEXT NOT NULL CHECK(length(owner_note) BETWEEN 5 AND 200),
        state TEXT NOT NULL DEFAULT 'pending'
          CHECK(state IN ('pending','running','succeeded','failed','cancelled')),
        error_kind TEXT NOT NULL DEFAULT '',
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        finished_at TEXT)""")
    con.execute("""CREATE TABLE IF NOT EXISTS aiwack_owner_model_queue_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        queue_id INTEGER NOT NULL REFERENCES aiwack_owner_model_queue(id),
        event_kind TEXT NOT NULL
          CHECK(event_kind IN ('enqueued','claimed','succeeded','failed','cancelled','owner_process_exited')),
        detail TEXT NOT NULL DEFAULT '',
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(queue_id,event_kind))""")
    for action in ("UPDATE", "DELETE"):
        con.execute(f"""CREATE TRIGGER IF NOT EXISTS aiwack_owner_model_queue_events_no_{action.lower()}
            BEFORE {action} ON aiwack_owner_model_queue_events
            BEGIN SELECT RAISE(ABORT,'실제 GGUF 대기열 감사 변경·삭제 금지'); END""")


def _readiness(store, task_id):
    task = store.read_task(task_id)
    if task["status"] != "todo":
        raise ValueError("아직 실행하지 않은 todo 업무만 대기열에 등록합니다.")
    if store.read_chief_task_order(task_id) is None:
        raise PermissionError("관리자가 승인한 총괄 지시가 없습니다.")
    route = store.read_task_routing(task_id)
    employee_id = route.get("employee_id")
    if not employee_id or store.read_employee_model(int(employee_id)) is None:
        raise PermissionError("실제 모델이 연결된 담당 직원 배정이 필요합니다.")
    if store.list_task_runs(task_id) or store.list_task_artifacts(task_id):
        raise PermissionError("이미 직원 실행/결과물 이력이 있어 자동 중복 실행 금지")
    return int(employee_id)


def enqueue(store, task_id, owner_note):
    store.require_permission("company:manage")
    store.require_permission("agents:manage")
    _id(task_id)
    note = _note(owner_note)
    from desktop import company_autopilot
    company_autopilot.initialize(store)
    employee_id = _readiness(store, task_id)
    with store._connect() as con:
        con.execute("BEGIN IMMEDIATE")
        initialize(con)
        if stopped(con):
            raise PermissionError("비상정지 중 대기열 등록 금지")
        if con.execute("SELECT 1 FROM aiwack_autopilot_model_runs WHERE task_id=?",
                       (task_id,)).fetchone():
            raise PermissionError("기존 자동 GGUF 호출 이력 존재, 재시도 금지")
        if con.execute("SELECT 1 FROM aiwack_owner_model_queue WHERE task_id=?",
                       (task_id,)).fetchone():
            raise ValueError("이 업무는 이전에 대기열에 등록됐습니다. 이력 보존/중복 금지")
        current = con.execute("SELECT status FROM company_tasks WHERE id=?",
                              (task_id,)).fetchone()
        if not current or current[0] != "todo":
            raise ValueError("등록 직전 업무 상태가 변경됐습니다.")
        qid = int(con.execute("""INSERT INTO aiwack_owner_model_queue(task_id,owner_note)
            VALUES(?,?)""", (task_id,note)).lastrowid)
        con.execute("""INSERT INTO aiwack_owner_model_queue_events(queue_id,event_kind,detail)
            VALUES(?,'enqueued',?)""", (qid,note))
    return {"queue_id":qid,"task_id":task_id,"employee_id":employee_id,
            "state":"pending","model_called":False,"owner_result_review_required":True}


def list_entries(store, limit=50):
    store.require_permission("company:manage")
    if type(limit) is not int or not 1 <= limit <= 100:
        raise ValueError("대기열 조회는 1~100건입니다.")
    with store._connect() as con:
        initialize(con)
        rows = con.execute("""SELECT q.id,q.task_id,q.state,q.error_kind,q.owner_note,
               q.created_at,q.finished_at,
               (SELECT COUNT(*) FROM aiwack_owner_model_queue_events e
                WHERE e.queue_id=q.id) AS audit_events
            FROM aiwack_owner_model_queue q ORDER BY q.id DESC LIMIT ?""",
            (limit,)).fetchall()
    return [dict(zip(("id","task_id","state","error_kind","owner_note",
                       "created_at","finished_at","audit_events"),r)) for r in rows]


def next_pending(store):
    store.require_permission("company:manage")
    with store._connect() as con:
        initialize(con)
        row = con.execute("""SELECT id,task_id FROM aiwack_owner_model_queue
            WHERE state='pending' ORDER BY id LIMIT 1""").fetchone()
    return None if row is None else {"id":int(row[0]),"task_id":int(row[1])}


def cancel_pending(store, queue_id, owner_note):
    store.require_permission("company:manage")
    _id(queue_id)
    note = _note(owner_note)
    with store._connect() as con:
        con.execute("BEGIN IMMEDIATE")
        initialize(con)
        if con.execute("""UPDATE aiwack_owner_model_queue
            SET state='cancelled',finished_at=CURRENT_TIMESTAMP
            WHERE id=? AND state='pending'""",(queue_id,)).rowcount != 1:
            raise ValueError("대기 상태의 업무만 취소할 수 있습니다.")
        con.execute("""INSERT INTO aiwack_owner_model_queue_events(queue_id,event_kind,detail)
            VALUES(?,'cancelled',?)""",(queue_id,note))
    return {"queue_id":queue_id,"state":"cancelled","model_called":False}


def run_next(store, *, session_token=None, cancel=None):
    """한 번에 정확히 하나의 기존 승인 업무만 실행; 실패 후 자동 재시도 없음."""
    store.require_permission("company:manage")
    store.require_permission("agents:manage")
    from desktop import company_autopilot
    if not company_autopilot.approved_models_enabled(store):
        raise PermissionError("소유자 자율운영·실제 GGUF 별도 동의가 비활성화됐습니다.")
    if cancel is not None and cancel.is_set():
        raise InterruptedError("실제 모델 실행 전 취소")
    with store._connect() as con:
        con.execute("BEGIN IMMEDIATE")
        initialize(con)
        if stopped(con):
            raise PermissionError("비상정지 중 실행 금지")
        policy = con.execute("""SELECT a.enabled,b.enabled
            FROM aiwack_autopilot_settings a CROSS JOIN aiwack_autopilot_model_policy b
            WHERE a.id=1 AND b.id=1""").fetchone()
        if not policy or not all(policy):
            raise PermissionError("실행 직전 모델 동의가 해제됐습니다.")
        row = con.execute("""SELECT id,task_id FROM aiwack_owner_model_queue
            WHERE state='pending' ORDER BY id LIMIT 1""").fetchone()
        if row is None:
            return {"executed":False,"reason":"empty"}
        queue_id, task_id = map(int,row)
        if con.execute("SELECT 1 FROM aiwack_autopilot_model_runs WHERE task_id=?",
                       (task_id,)).fetchone():
            raise PermissionError("기존 모델 실행 감사가 있어 자동 재실행 금지")
        if con.execute("""UPDATE aiwack_owner_model_queue SET state='running'
            WHERE id=? AND state='pending'""",(queue_id,)).rowcount != 1:
            raise RuntimeError("대기열 소유권 충돌")
        con.execute("""INSERT INTO aiwack_owner_model_queue_events(queue_id,event_kind)
            VALUES(?,'claimed')""",(queue_id,))
    try:
        result = company_autopilot.run_one_approved_model(
            store,(task_id,),cancel=cancel,session_token=session_token)
    except Exception as exc:
        with store._connect() as con:
            con.execute("BEGIN IMMEDIATE")
            changed = con.execute("""UPDATE aiwack_owner_model_queue
                SET state='failed',error_kind=?,finished_at=CURRENT_TIMESTAMP
                WHERE id=? AND state='running'""",
                (type(exc).__name__[:60],queue_id)).rowcount
            if changed:
                con.execute("""INSERT INTO aiwack_owner_model_queue_events
                    (queue_id,event_kind,detail) VALUES(?,'failed',?)""",
                    (queue_id,type(exc).__name__[:60]))
        raise
    with store._connect() as con:
        con.execute("BEGIN IMMEDIATE")
        if con.execute("""UPDATE aiwack_owner_model_queue
            SET state='succeeded',finished_at=CURRENT_TIMESTAMP
            WHERE id=? AND state='running'""",(queue_id,)).rowcount != 1:
            raise RuntimeError("실제 모델 실행 후 대기열 상태가 변경됐습니다.")
        con.execute("""INSERT INTO aiwack_owner_model_queue_events(queue_id,event_kind)
            VALUES(?,'succeeded')""",(queue_id,))
    return {**result,"queue_id":queue_id,"task_id":task_id,
            "owner_result_review_required":True,"external_actions":False}
