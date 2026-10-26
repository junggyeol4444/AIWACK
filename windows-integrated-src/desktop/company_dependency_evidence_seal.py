"""AIWACK 승인된 부서 간 선행 업무의 실제 GGUF 근거 원장.

후속 직원이 실제 GGUF를 실행하기 전에, 다른 부서에서 수행한 선행
업무들의 직원 모델 호출/원문 해시·총괄 모델 검토/원문 해시·관리자 승인
및 현재 배정·지시를 원자적 스냅샷으로 고정할 수 있다.

검수/결제/상품 전송을 자동 승인하지 않고, 원본 업무/모델/감사 변경 시
추가 모델 호출 전에 차단한다. 기존 업무는 소유자가 이 기능으로
별도 서명(seal)하지 않는 한 이전 실행 경로를 유지한다.
"""
from __future__ import annotations

import hashlib
import json

from desktop.stage87_90_management import stopped


def _id(value, label):
    if type(value) is not int or value<=0:
        raise ValueError(label+" 번호는 양의 정수여야 합니다.")
    return value


def _json(data):
    return json.dumps(data,sort_keys=True,ensure_ascii=False,
                      separators=(",",":"))


def _hash(data):
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


def initialize(con):
    con.execute("""CREATE TABLE IF NOT EXISTS aiwack_sealed_dependency_handoffs(
        task_id INTEGER PRIMARY KEY REFERENCES company_tasks(id),
        target_sha256 TEXT NOT NULL CHECK(length(target_sha256)=64),
        source_json TEXT NOT NULL,
        evidence_sha256 TEXT NOT NULL CHECK(length(evidence_sha256)=64),
        dependency_count INTEGER NOT NULL CHECK(dependency_count BETWEEN 1 AND 30),
        owner_note TEXT NOT NULL CHECK(length(owner_note) BETWEEN 5 AND 200),
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    )""")
    con.execute("""CREATE TABLE IF NOT EXISTS aiwack_sealed_dependency_events(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        task_id INTEGER NOT NULL REFERENCES aiwack_sealed_dependency_handoffs(task_id),
        event_type TEXT NOT NULL CHECK(event_type='owner_sealed'),
        evidence_sha256 TEXT NOT NULL CHECK(length(evidence_sha256)=64),
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(task_id,event_type)
    )""")
    for table in ("aiwack_sealed_dependency_handoffs",
                  "aiwack_sealed_dependency_events"):
        for action in ("UPDATE","DELETE"):
            con.execute("""CREATE TRIGGER IF NOT EXISTS %s_no_%s BEFORE %s ON %s
                BEGIN SELECT RAISE(ABORT,'부서간 모델 인계 승인 근거 원본 변경 금지'); END"""
                % (table,action.lower(),action,table))


def _latest_verified_artifact(con,prereq):
    # Require exactly one finished, approved, REAL staff model execution
    # and an accepted chief report from the SAME actual artifact. A manual
    # 'done' marker or owner-written chief text is not real GGUF evidence.
    rows=con.execute("""SELECT a.id,a.body,a.sha256,r.id,r.employee_id,
            r.model_id,r.model_call_id,r.status,m.employee_id,m.model_id,
            m.status,m.output_chars,
            c.id,c.body,c.sha256,c.owner_decision,c.chief_model_call_id,
            cm.employee_id,cm.model_id,cm.status,cm.output_chars,
            o.id,o.worker_employee_id,o.chief_employee_id
        FROM company_task_artifacts a
        JOIN company_task_runs r ON r.id=a.run_id AND r.task_id=a.task_id
        JOIN ai_model_call_history m ON m.id=r.model_call_id
        JOIN company_chief_task_reports c ON c.artifact_id=a.id
        JOIN company_chief_task_orders o ON o.id=c.order_id
            AND o.task_id=a.task_id
        JOIN company_chief_task_dispatches d ON d.order_id=o.id AND d.run_id=r.id
        JOIN ai_model_call_history cm ON cm.id=c.chief_model_call_id
        WHERE a.task_id=? AND a.review_status='approved'
            AND r.status='success' AND m.status='success'
            AND c.owner_decision='accepted' AND cm.status='success'
        ORDER BY a.id DESC LIMIT 2""",(prereq,)).fetchall()
    if len(rows)!=1:
        raise PermissionError(
            "선행 업무 #"+str(prereq)+": 실제 직원·총괄 GGUF 성공 및 관리자 양쪽 검수 증빙이 한 건 필요합니다.")
    row=rows[0]
    (aid,body,digest,run_id,worker,model,call_id,run_state,
     caller,call_model,call_state,call_chars,
     cid,chief_body,chief_sha,chief_decision,chief_call,
     chief_caller,chief_model,chief_state,chief_chars,
     order,ordered_worker,ordered_chief)=row
    if (not isinstance(body,str) or not isinstance(chief_body,str)
            or not body or not chief_body
            or _hash(body)!=digest or _hash(chief_body)!=chief_sha
            or worker!=caller or worker!=ordered_worker
            or model!=call_model or ordered_chief!=chief_caller
            or int(call_chars)<1 or int(chief_chars)<1):
        raise PermissionError("선행 업무 #"+str(prereq)+": 원본 모델 호출/해시/직원 연결 불일치")
    return {"task_id":int(prereq),"artifact_id":int(aid),
            "artifact_sha256":digest,"run_id":int(run_id),
            "staff_id":int(worker),"staff_model_id":int(model),
            "staff_call_id":int(call_id),
            "chief_report_id":int(cid),"chief_sha256":chief_sha,
            "chief_call_id":int(chief_call),
            "chief_employee_id":int(chief_caller),
            "chief_model_id":int(chief_model),
            "chief_order_id":int(order)}


def _snapshot_in_tx(con,task_id):
    task=con.execute("""SELECT title,description,status
        FROM company_tasks WHERE id=?""",(task_id,)).fetchone()
    if not task:
        raise ValueError("인계 대상 업무가 없습니다.")
    if task[2]!="todo":
        raise PermissionError("미실행 todo 후속 업무만 인계 근거를 고정할 수 있습니다.")
    order=con.execute("""SELECT id,worker_employee_id,chief_employee_id,
        instruction,task_fingerprint FROM company_chief_task_orders
        WHERE task_id=?""",(task_id,)).fetchone()
    staff=con.execute("""SELECT a.employee_id,m.model_id
        FROM company_task_assignments a
        JOIN ai_employee_model_assignments m ON m.employee_id=a.employee_id
        WHERE a.task_id=?""",(task_id,)).fetchone()
    if not order or not staff or staff[0]!=order[1]:
        raise PermissionError("후속 업무 관리자 승인 총괄 지시와 모델 연결 직원이 필요합니다.")
    from desktop.company_model_queue_readiness import _ready_in_tx
    # Legacy prerequisite and wider campaign gates remain authoritative;
    # never bypass them because a new snapshot exists.
    # Avoid recursion: this function performs its own direct predecessor
    # provenance checks instead of calling _ready_in_tx.
    if con.execute("SELECT 1 FROM company_task_runs WHERE task_id=?",(task_id,)).fetchone():
        raise PermissionError("후속 직원에 기존 모델 호출/실패 기록이 있어 서명 금지")
    deps=[int(row[0]) for row in con.execute("""SELECT prerequisite_id
        FROM company_task_dependencies WHERE task_id=?
        ORDER BY prerequisite_id""",(task_id,)).fetchall()]
    if not 1<=len(deps)<=30:
        raise ValueError("부서간 선행 업무 1~30건이 있어야 인계 원장 생성 가능")
    source=[]
    for previous in deps:
        prev=con.execute("SELECT status FROM company_tasks WHERE id=?",
                         (previous,)).fetchone()
        if not prev or prev[0]!="done":
            raise PermissionError("선행 업무 #"+str(previous)+" 관리자 완료 승인 대기")
        source.append(_latest_verified_artifact(con,previous))
    target={"task_id":task_id,
            "title_sha256":_hash(str(task[0])),
            "description_sha256":_hash(str(task[1])),
            "order_id":int(order[0]),
            "order_instruction_sha256":_hash(str(order[3])),
            "order_task_fingerprint":str(order[4]),
            "worker_id":int(staff[0]),
            "worker_model_id":int(staff[1]),
            "chief_employee_id":int(order[2])}
    return {"target":target,"prerequisites":source}


def _has_seal(con,task_id):
    return (con.execute("""SELECT 1 FROM sqlite_master
        WHERE type='table' AND name='aiwack_sealed_dependency_handoffs'""").fetchone()
        and con.execute("""SELECT 1 FROM aiwack_sealed_dependency_handoffs
            WHERE task_id=?""",(task_id,)).fetchone())


def assert_current_in_tx(con,task_id):
    """Shared read-only gate used before claiming a real model run."""
    _id(task_id,"후속 업무")
    if not _has_seal(con,task_id):
        return False
    row=con.execute("""SELECT target_sha256,source_json,evidence_sha256,
        dependency_count FROM aiwack_sealed_dependency_handoffs
        WHERE task_id=?""",(task_id,)).fetchone()
    if not row or _hash(row[1])!=row[2]:
        raise PermissionError("저장된 부서간 인계 원장 자체 무결성이 변경됐습니다")
    current=_snapshot_in_tx(con,task_id)
    raw=_json(current)
    if (row[0]!=_hash(_json(current["target"])) or
        row[1]!=raw or row[2]!=_hash(raw) or
        row[3]!=len(current["prerequisites"])):
        raise PermissionError("선행 부서 결과물·실제 GGUF 호출·관리자 승인/업무 배정이 변경되어 실행 차단")
    return True


def seal(store,task_id,owner_note):
    """Owner-triggered, transactionally immutable approved handoff evidence."""
    store.require_permission("company:manage")
    store.require_permission("agents:manage")
    _id(task_id,"후속 업무")
    if type(owner_note) is not str or not 5<=len(owner_note.strip())<=200:
        raise ValueError("부서간 실제 GGUF 인계 관리자 사유 5~200자")
    with store._connect() as con:
        con.execute("BEGIN IMMEDIATE")
        initialize(con)
        if stopped(con):
            raise PermissionError("비상정지 중 부서 업무 인계 승인 불가")
        if _has_seal(con,task_id):
            raise ValueError("기존 부서간 인계 근거가 있습니다. 원본 덮어쓰기/재서명 불가")
        snapshot=_snapshot_in_tx(con,task_id)
        raw=_json(snapshot)
        digest=_hash(raw)
        target_hash=_hash(_json(snapshot["target"]))
        con.execute("""INSERT INTO aiwack_sealed_dependency_handoffs
            (task_id,target_sha256,source_json,evidence_sha256,
            dependency_count,owner_note) VALUES(?,?,?,?,?,?)""",
            (task_id,target_hash,raw,digest,
             len(snapshot["prerequisites"]),owner_note.strip()))
        con.execute("""INSERT INTO aiwack_sealed_dependency_events
            (task_id,event_type,evidence_sha256)
            VALUES(?,'owner_sealed',?)""",(task_id,digest))
    return {"task_id":task_id,"evidence_sha256":digest,
            "prerequisite_count":len(snapshot["prerequisites"]),
            "owner_sealed":True,"new_model_called":False,
            "employee_task_executed":False,"final_approval_automatic":False}


def inspect(store,task_id):
    store.require_permission("company:manage")
    _id(task_id,"후속 업무")
    with store._connect() as con:
        if not _has_seal(con,task_id):
            return {"task_id":task_id,"sealed":False,
                    "ready_for_sealed_execution":False,
                    "new_model_invoked":False}
        row=con.execute("""SELECT evidence_sha256,dependency_count,created_at
            FROM aiwack_sealed_dependency_handoffs WHERE task_id=?""",
            (task_id,)).fetchone()
        try:
            verified=assert_current_in_tx(con,task_id)
            reason="원본 선행 직원/총괄 모델 호출·관리자 승인·배정 동일"
        except (ValueError,PermissionError) as e:
            verified=False
            reason=str(e)[:240]
    return {"task_id":task_id,"sealed":True,
            "evidence_sha256":row[0],"dependency_count":int(row[1]),
            "created_at":row[2],"ready_for_sealed_execution":verified,
            "reason":reason,"new_model_invoked":False}


def history(store,limit=50):
    store.require_permission("company:manage")
    if type(limit) is not int or not 1<=limit<=100:
        raise ValueError("부서간 인계 근거 조회 1~100건")
    with store._connect() as con:
        initialize(con)
        rows=con.execute("""SELECT task_id,evidence_sha256,dependency_count,
            created_at FROM aiwack_sealed_dependency_handoffs
            ORDER BY created_at DESC,task_id DESC LIMIT ?""",(limit,)).fetchall()
    results=[]
    for task,digest,count,created in rows:
        report=inspect(store,int(task))
        results.append({"task_id":int(task),"evidence_sha256":digest,
                        "dependency_count":count,"created_at":created,
                        "source_unchanged":report["ready_for_sealed_execution"],
                        "reason":report["reason"]})
    return results
