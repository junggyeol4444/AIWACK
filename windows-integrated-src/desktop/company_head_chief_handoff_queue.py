"""관리자 전달 승인된 실제 부서장 GGUF 결과를 총괄 실모델로 연속 회수.

총괄이 실제 발굴한 부서 업무만 대상으로 한다. 부서장 수락과 관리자
개별 전달 승인이 선행돼야 하며 실제 직원 결과물과 모델 호출 감사의
연결을 검사한다. 연속 호출은 사용자 명시 버튼으로만 시작한다.
기존 총괄 collect_chief_review이 모델 잠금·실제 호출·보고서 원본을 관리.
최종 보고서, 결과물, 매출, 완료 상태는 이 모듈에서 승인하지 않는다.
"""
from __future__ import annotations

import hashlib
import sqlite3
import threading

from desktop.stage87_90_management import stopped

BATCH_LIMIT=10


def initialize(con):
    con.execute("""CREATE TABLE IF NOT EXISTS aiwack_head_chief_batches(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        owner_note TEXT NOT NULL CHECK(length(owner_note) BETWEEN 5 AND 200),
        max_items INTEGER NOT NULL CHECK(max_items BETWEEN 1 AND 10),
        state TEXT NOT NULL CHECK(state IN
            ('running','finished','failed','cancelled')),
        completed_count INTEGER NOT NULL DEFAULT 0,
        exit_reason TEXT NOT NULL DEFAULT '',
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        closed_at TEXT)""")
    con.execute("""CREATE TABLE IF NOT EXISTS aiwack_head_chief_batch_items(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        batch_id INTEGER NOT NULL REFERENCES aiwack_head_chief_batches(id),
        ordinal INTEGER NOT NULL,
        artifact_id INTEGER NOT NULL REFERENCES company_task_artifacts(id),
        head_review_id INTEGER NOT NULL REFERENCES aiwack_department_head_reviews(id),
        state TEXT NOT NULL CHECK(state IN
            ('pending','running','success','failed','cancelled')),
        report_id INTEGER UNIQUE REFERENCES company_chief_task_reports(id),
        error_kind TEXT NOT NULL DEFAULT '',
        changed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(batch_id,ordinal),UNIQUE(batch_id,artifact_id))""")
    con.execute("""CREATE TABLE IF NOT EXISTS aiwack_head_chief_batch_events(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        batch_id INTEGER NOT NULL REFERENCES aiwack_head_chief_batches(id),
        item_id INTEGER REFERENCES aiwack_head_chief_batch_items(id),
        event_type TEXT NOT NULL CHECK(event_type IN
            ('opened','claimed','succeeded','failed','cancelled','finished','owner_closed')),
        detail TEXT NOT NULL DEFAULT '',
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)""")
    for operation in ("UPDATE","DELETE"):
        con.execute("""CREATE TRIGGER IF NOT EXISTS aiwack_head_chief_events_no_%s
            BEFORE %s ON aiwack_head_chief_batch_events
            BEGIN SELECT RAISE(ABORT,'총괄 회수 모델 실행 감사 원본 수정 금지'); END"""
            % (operation.lower(),operation))


def _positive(value,name):
    if type(value) is not int or value<1:
        raise ValueError(name+" 번호는 양의 정수여야 합니다.")
    return value


def _note(value):
    if type(value) is not str or not 5<=len(value.strip())<=200:
        raise ValueError("관리자 실행 사유를 5~200자로 입력하세요.")
    return value.strip()


def _ready(con,artifact_id):
    from desktop.company_department_head_review import _verified_in_tx
    row=con.execute("""SELECT a.task_id,a.body,a.sha256,a.review_status,
        r.id,r.status,r.employee_id,r.model_call_id,
        c.id,c.status,c.employee_id,c.model_id,c.output_chars,
        p.id,o.id,
        (SELECT id FROM company_chief_task_reports WHERE artifact_id=a.id)
        FROM company_task_artifacts a
        JOIN company_task_runs r ON r.id=a.run_id AND r.task_id=a.task_id
        JOIN ai_model_call_history c ON c.id=r.model_call_id
        JOIN company_chief_task_dispatches d ON d.run_id=r.id
        JOIN company_chief_task_orders o ON o.id=d.order_id AND o.task_id=a.task_id
        JOIN aiwack_chief_department_proposal_decisions p
          ON p.task_id=a.task_id AND p.decision='approved'
        WHERE a.id=?""",(artifact_id,)).fetchone()
    if not row:
        return None
    (task_id,body,digest,owner_review,run_id,run_state,worker,call_id,
     worker_call,call_state,call_employee,worker_model,worker_chars,
     proposal,order,existing_report)=row
    if (existing_report is not None or owner_review!='pending' or
        run_state!='success' or call_state!='success' or
        worker!=call_employee or not body or
        hashlib.sha256(str(body).encode('utf8')).hexdigest()!=digest or
        int(worker_chars)<1):
        return None
    if con.execute("""SELECT 1 FROM aiwack_head_chief_batch_items
        WHERE artifact_id=? AND state IN ('running','success','failed')
        LIMIT 1""",(artifact_id,)).fetchone():
        return None
    if con.execute("""SELECT 1 FROM aiwack_chief_review_leases
        WHERE artifact_id=?""",(artifact_id,)).fetchone() if con.execute(
        """SELECT 1 FROM sqlite_master WHERE name='aiwack_chief_review_leases'
        AND type='table'""").fetchone() else False:
        return None
    proof=_verified_in_tx(con,artifact_id)
    if not proof or proof["verdict"]!="accept" or proof["decision"]!="forward":
        return None
    return {"artifact_id":int(artifact_id),"task_id":int(task_id),
            "head_review_id":int(proof["review_id"]),
            "manager_model_call_id":int(proof["model_call_id"]),
            "worker_model_call_id":int(call_id),
            "owner_forwarded":True}


def _candidates(con,limit):
    if not con.execute("""SELECT 1 FROM sqlite_master
        WHERE type='table' AND name='aiwack_department_head_reviews'""").fetchone():
        return []
    result=[]
    for (aid,) in con.execute("""SELECT h.artifact_id
        FROM aiwack_department_head_reviews h
        JOIN aiwack_department_head_decisions d ON d.review_id=h.id
        WHERE h.state='success' AND d.decision='forward'
        ORDER BY d.id,h.id""").fetchall():
        item=_ready(con,int(aid))
        if item is not None:
            result.append(item)
            if len(result)>=limit:
                break
    return result


def preview(store,limit=30):
    """모델 실행하지 않는 실제 SQLite 원본 읽기 전용 선행 승인 현황."""
    store.require_permission('company:manage')
    if type(limit) is not int or not 1<=limit<=100:
        raise ValueError("조회 개수는 1~100입니다.")
    with store._connect() as con:
        initialize(con)
        from desktop.company_department_head_review import initialize as init_head
        init_head(con)
        ready=_candidates(con,limit)
        unfinished=int(con.execute("""SELECT COUNT(*) FROM aiwack_head_chief_batches
            WHERE state='running'""").fetchone()[0])
    return {"ready_for_real_chief":ready,"total_listed":len(ready),
            "unfinished_batch_count":unfinished,
            "chief_called_by_preview":False,"final_approval_required":True}


def _event(con,batch_id,kind,*,item_id=None,detail=''):
    con.execute("""INSERT INTO aiwack_head_chief_batch_events
        (batch_id,item_id,event_type,detail) VALUES(?,?,?,?)""",
        (batch_id,item_id,kind,detail))


def _close(store,batch_id,state,count,reason):
    with store._connect() as con:
        con.execute("BEGIN IMMEDIATE")
        initialize(con)
        if con.execute("""UPDATE aiwack_head_chief_batches SET
            state=?,completed_count=?,exit_reason=?,closed_at=CURRENT_TIMESTAMP
            WHERE id=? AND state='running'""",
            (state,count,reason,batch_id)).rowcount!=1:
            raise RuntimeError("총괄 회수 실행 회차 소유권 변경됨")
        con.execute("""UPDATE aiwack_head_chief_batch_items SET
            state='cancelled',changed_at=CURRENT_TIMESTAMP
            WHERE batch_id=? AND state='pending'""",(batch_id,))
        _event(con,batch_id,'finished' if state=='finished' else
               ('cancelled' if state=='cancelled' else 'failed'),detail=reason)


def run(store,max_items,owner_note,*,cancel:threading.Event|None=None):
    """관리자 1회 실행: 준비된 서로 다른 결과물 최대 10건을 순차적으로 회수."""
    store.require_permission('company:manage')
    store.require_permission('agents:manage')
    if type(max_items) is not int or not 1<=max_items<=BATCH_LIMIT:
        raise ValueError("총괄 연속 회수는 한 번에 1~10건입니다.")
    note=_note(owner_note)
    if cancel is not None and cancel.is_set():
        raise InterruptedError("모델 회수 실행 전 관리자 취소")
    from desktop import company_operations
    company_operations.assert_running_allowed(store)
    with store._connect() as con:
        con.execute("BEGIN IMMEDIATE")
        initialize(con)
        from desktop.company_department_head_review import initialize as init_head
        init_head(con)
        if stopped(con):
            raise PermissionError("비상정지 중 총괄 모델 호출 금지")
        if con.execute("""SELECT 1 FROM aiwack_head_chief_batches
            WHERE state='running' LIMIT 1""").fetchone():
            raise PermissionError("이전 총괄 회수 미종료 회차: 실제 프로세스 관리자 확인 필요")
        chosen=_candidates(con,max_items)
        if not chosen:
            return {"executed":False,"reason":"no_owner_forwarded_head_review",
                    "model_called":False}
        batch_id=int(con.execute("""INSERT INTO aiwack_head_chief_batches
            (owner_note,max_items,state) VALUES(?,?,'running')""",
            (note,max_items)).lastrowid)
        _event(con,batch_id,'opened',detail=note)
        item_ids=[]
        for ordinal,candidate in enumerate(chosen,1):
            item_id=int(con.execute("""INSERT INTO aiwack_head_chief_batch_items
                (batch_id,ordinal,artifact_id,head_review_id,state)
                VALUES(?,?,?,?,'pending')""",
                (batch_id,ordinal,candidate["artifact_id"],
                 candidate["head_review_id"])).lastrowid)
            item_ids.append((item_id,candidate))
    completed=0
    reports=[]
    try:
        for item_id,snapshot in item_ids:
            if cancel is not None and cancel.is_set():
                _close(store,batch_id,'cancelled',completed,'owner_cancelled')
                return {"executed":True,"batch_id":batch_id,
                        "chief_reports_created":completed,
                        "state":"cancelled","report_ids":reports,
                        "owner_final_approval_required":True}
            company_operations.assert_running_allowed(store)
            with store._connect() as con:
                con.execute('BEGIN IMMEDIATE')
                ready=_ready(con,snapshot["artifact_id"])
                if ready!=snapshot:
                    raise PermissionError("실행 전 부서장 검토·업무 원본 변경: 총괄 호출 금지")
                if con.execute("""UPDATE aiwack_head_chief_batch_items
                    SET state='running',changed_at=CURRENT_TIMESTAMP
                    WHERE id=? AND state='pending'""",(item_id,)).rowcount!=1:
                    raise RuntimeError("실제 총괄 대기 회차 변경 충돌")
                _event(con,batch_id,'claimed',item_id=item_id)
            # Reuse existing chief-review lease, genuine GGUF subprocess and
            # provenance-checked report store. No artificial completion.
            try:
                result=company_operations.collect_chief_review(
                    store,snapshot["artifact_id"],cancel=cancel)
            except Exception as exc:
                with store._connect() as con:
                    con.execute('BEGIN IMMEDIATE')
                    if con.execute("""UPDATE aiwack_head_chief_batch_items
                        SET state='failed',error_kind=?,changed_at=CURRENT_TIMESTAMP
                        WHERE id=? AND state='running'""",
                        (type(exc).__name__[:70],item_id)).rowcount:
                        _event(con,batch_id,'failed',item_id=item_id,
                               detail=type(exc).__name__[:70])
                raise
            if (type(result.get('report_id')) is not int or result['report_id']<1
                    or result.get('chief_model_called') is not True):
                raise RuntimeError("총괄 실 GGUF 원본 보고서/실호출 감사 누락")
            with store._connect() as con:
                con.execute("BEGIN IMMEDIATE")
                report=con.execute("""SELECT id,artifact_id,chief_model_call_id
                    FROM company_chief_task_reports WHERE id=?""",
                    (result['report_id'],)).fetchone()
                if (not report or report[1]!=snapshot["artifact_id"]
                        or report[2] is None):
                    raise PermissionError("총괄 실제 모델 호출과 보고서 원본 연결 불일치")
                if con.execute("""UPDATE aiwack_head_chief_batch_items
                    SET state='success',report_id=?,changed_at=CURRENT_TIMESTAMP
                    WHERE id=? AND state='running'""",
                    (result["report_id"],item_id)).rowcount!=1:
                    raise RuntimeError("총괄 모델 회수 원장 상태 변경")
                _event(con,batch_id,'succeeded',item_id=item_id,
                       detail="genuine_chief_report_id="+str(result["report_id"]))
            reports.append(int(result["report_id"]))
            completed+=1
        _close(store,batch_id,'finished',completed,'owner_approved_batch_finished')
    except Exception as exc:
        _close(store,batch_id,'failed',completed,type(exc).__name__[:70])
        raise
    return {"executed":True,"batch_id":batch_id,"state":"finished",
            "chief_reports_created":completed,"report_ids":reports,
            "owner_final_approval_required":True,
            "employee_reexecuted":False,"external_transactions":False}


def history(store,limit=30):
    store.require_permission('company:manage')
    if type(limit) is not int or not 1<=limit<=100:
        raise ValueError("총괄 회수 감사 1~100회차 조회")
    with store._connect() as con:
        initialize(con)
        batches=con.execute("""SELECT id,state,max_items,completed_count,
            exit_reason,created_at,closed_at FROM aiwack_head_chief_batches
            ORDER BY id DESC LIMIT ?""",(limit,)).fetchall()
        result=[]
        for row in batches:
            items=con.execute("""SELECT artifact_id,head_review_id,
                state,report_id,error_kind FROM aiwack_head_chief_batch_items
                WHERE batch_id=? ORDER BY ordinal""",(row[0],)).fetchall()
            result.append(dict(zip(("id","state","max_items","completed_count",
                "exit_reason","created_at","closed_at"),row))|
                {"items":[dict(zip(("artifact_id","head_review_id","state",
                "report_id","error_kind"),v)) for v in items]})
    return result


def close_after_owner_inspection(store,batch_id,note,*,owner_confirmed=False):
    """비정상 종료 실모델 프로세스 종료 확인 후 회차만 닫기, 재호출 절대 없음."""
    store.require_permission('company:manage')
    store.require_permission('agents:manage')
    _positive(batch_id,"회차")
    note=_note(note)
    if owner_confirmed is not True:
        raise PermissionError("프로세스 종료 관리자 직접 확인 필수")
    with store._connect() as con:
        con.execute('BEGIN IMMEDIATE')
        initialize(con)
        state=con.execute("""SELECT state FROM aiwack_head_chief_batches
            WHERE id=?""",(batch_id,)).fetchone()
        if not state or state[0]!='running':
            raise ValueError("중단된 실행 중 회차만 확인 종료할 수 있습니다.")
        if con.execute("""SELECT 1 FROM aiwack_chief_review_leases LIMIT 1""").fetchone() if con.execute(
            """SELECT 1 FROM sqlite_master WHERE name='aiwack_chief_review_leases'
                AND type='table'""").fetchone() else False:
            raise PermissionError("실제 총괄 모델 검토 잠금 존재")
        if con.execute("""SELECT 1 FROM ai_model_call_history
            WHERE status='running' LIMIT 1""").fetchone():
            raise PermissionError("아직 실행 중인 모델 호출 감사가 있습니다.")
        done=con.execute("""SELECT COUNT(*) FROM aiwack_head_chief_batch_items
            WHERE batch_id=? AND state='success'""",(batch_id,)).fetchone()[0]
        if con.execute("""UPDATE aiwack_head_chief_batches SET state='cancelled',
            completed_count=?,exit_reason='owner_inspected_interruption',
            closed_at=CURRENT_TIMESTAMP WHERE id=? AND state='running'""",
            (done,batch_id)).rowcount!=1:
            raise RuntimeError("회차 소유권이 변경됐습니다.")
        con.execute("""UPDATE aiwack_head_chief_batch_items SET
            state='cancelled',changed_at=CURRENT_TIMESTAMP
            WHERE batch_id=? AND state='pending'""",(batch_id,))
        # Leave a claimed, uncertain result in 'running' so the next invocation
        # is blocked until independent owner reconciliation.
        _event(con,batch_id,'owner_closed',detail=note)
    return {"batch_id":batch_id,"state":"cancelled",
            "previous_reports_preserved":int(done),
            "models_reinvoked":False,"requires_existing_item_inspection":True}
