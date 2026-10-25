"""15부서·30업무 원본의 관리자 운영 현황과 보존형 확인 기록.

기존 총괄/직원 GGUF 실행·검수·영속 대기열을 재사용한다.
상태 조회/기록은 업무를 실행·승인·재시도하지 않는다.
"""
from __future__ import annotations

import hashlib
import json

from desktop import company_wide_campaign


def initialize(con):
    con.execute("""CREATE TABLE IF NOT EXISTS aiwack_campaign_owner_checkpoints (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        campaign_id INTEGER NOT NULL REFERENCES aiwack_wide_campaigns(id),
        snapshot_json TEXT NOT NULL,
        snapshot_sha256 TEXT NOT NULL CHECK(length(snapshot_sha256)=64),
        owner_note TEXT NOT NULL CHECK(length(owner_note) BETWEEN 5 AND 200),
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(campaign_id,snapshot_sha256)
    )""")
    for action in ("UPDATE", "DELETE"):
        con.execute("""CREATE TRIGGER IF NOT EXISTS aiwack_campaign_owner_checkpoints_no_"""
                    + action.lower() + """
            BEFORE """ + action + """ ON aiwack_campaign_owner_checkpoints
            BEGIN SELECT RAISE(ABORT,'회사 전체 운영 확인 기록 변경·삭제 금지'); END""")


def _id(value):
    if type(value) is not int or value < 1:
        raise ValueError("회사 전체 협업 번호는 양의 정수여야 합니다.")
    return value


def inspect_campaign(store, campaign_id):
    """30업무 원본과 영속 대기열을 교차 조회. 조회 간 상태 변경 가능성을 명시."""
    store.require_permission("company:manage")
    _id(campaign_id)
    from desktop import company_autopilot, company_owner_model_queue
    from desktop.company_campaign_resume_gate import snapshot
    company_autopilot.initialize(store)
    with store._connect() as con:
        company_wide_campaign.initialize(con)
        company_owner_model_queue.initialize(con)
        campaign = con.execute("""SELECT id,state,source_task_id,chief_employee_id
            FROM aiwack_wide_campaigns WHERE id=?""", (campaign_id,)).fetchone()
        if campaign is None:
            raise ValueError("원본 회사 전체 협업 계획이 없습니다.")
        steps = con.execute("""SELECT s.ordinal,s.department_id,s.employee_id,
                   s.task_id,t.status
            FROM aiwack_wide_campaign_steps s
            LEFT JOIN company_tasks t ON t.id=s.task_id
            WHERE s.campaign_id=? ORDER BY s.ordinal""", (campaign_id,)).fetchall()
        if len(steps) != 30 or [int(s[0]) for s in steps] != list(range(1,31)):
            raise ValueError("원본 30업무 단계 수·순서가 일치하지 않습니다.")
        task_ids = [int(s[3]) for s in steps if s[3] is not None]
        queue_rows = []
        if task_ids:
            marks = ",".join("?" for _ in task_ids)
            queue_rows = con.execute(
                "SELECT id,task_id,state FROM aiwack_owner_model_queue "
                "WHERE task_id IN (" + marks + ") ORDER BY id", task_ids).fetchall()
    queue = [{"queue_id":int(q[0]),"task_id":int(q[1]),"state":str(q[2])}
             for q in queue_rows]
    states = {}
    for step in steps:
        state = str(step[4] if step[4] is not None else "not_created")
        states[state] = states.get(state,0)+1
    try:
        gate = snapshot(store, campaign_id, require_genuine_provenance=True)
        status = str(gate.get("state","blocked"))
        reason = str(gate.get("reason","원본 판정 사유 없음"))
    except (ValueError, PermissionError, RuntimeError) as exc:
        gate = {"state":"blocked","reason":str(exc)[:500],
                "next_task_id":None,"next_ordinal":None}
        status,reason = "blocked",gate["reason"]
    pending = [q for q in queue if q["state"]=="pending"]
    running = [q for q in queue if q["state"]=="running"]
    failed = [q for q in queue if q["state"]=="failed"]
    next_task = gate.get("next_task_id")
    matching = next((q for q in queue if q["task_id"]==next_task), None)
    if status=="completed":
        action = "30업무 증빙 확인 완료: 기존 최종 총괄 보고·관리자 승인 별도 확인"
    elif running:
        action = "실제 모델 실행 중: 중복 실행·자동 재시도 금지"
    elif failed:
        action = "실패 감사 보존: 관리자 원본·하위 프로세스 확인 필요"
    elif matching and matching["state"]=="succeeded":
        action = "직원·총괄 결과물과 관리자 개별 검수 확인 필요"
    elif matching and matching["state"]=="pending":
        action = "기존 관리자 승인 대기열 등록됨: 실행 정책·선행 검수 확인"
    elif status=="ready":
        action = "관리자 개별 승인 후 다음 1건만 영속 대기열 등록 가능"
    else:
        action = "차단 원인과 이전 단계 실제 모델·관리자 승인 원본 확인"
    return {
        "campaign_id":campaign_id,"campaign_state":str(campaign[1]),
        "source_task_id":int(campaign[2]),"chief_employee_id":int(campaign[3]),
        "steps_total":30,"distinct_departments":len({int(s[1]) for s in steps}),
        "distinct_workers":len({int(s[2]) for s in steps}),
        "task_states":states,"queue_entries":queue,
        "pending_queue_count":len(pending),"running_queue_count":len(running),
        "failed_queue_count":len(failed),
        "verified_completed_tasks":gate.get("verified_completed_tasks"),
        "verified_genuine_prefix_tasks":gate.get("verified_genuine_prefix_tasks"),
        "next_task_id":next_task,"next_ordinal":gate.get("next_ordinal"),
        "gate_state":status,"gate_reason":reason,"owner_next_action":action,
        "observation_non_atomic":True,"model_called_during_read":False,
        "automatic_owner_approval":False,"automatic_retry":False,
        "external_actions":False,"actual_gguf_binary_verified":False}


def board(store, limit=20):
    store.require_permission("company:manage")
    if type(limit) is not int or not 1<=limit<=100:
        raise ValueError("회사 전체 운영 조회는 1~100건입니다.")
    with store._connect() as con:
        company_wide_campaign.initialize(con)
        ids = [int(row[0]) for row in con.execute(
            "SELECT id FROM aiwack_wide_campaigns ORDER BY id DESC LIMIT ?",(limit,))]
    return {"campaigns":[inspect_campaign(store, cid) for cid in ids],
            "returned_count":len(ids),"read_only":True,
            "automatic_execution":False,"owner_approval_per_step":True}


def capture(store, campaign_id, owner_note):
    """관리자가 확인한 관측값만 별도 보존. 동시 수정이 없는 원자 스냅샷이라 주장하지 않음."""
    store.require_permission("company:manage")
    _id(campaign_id)
    if not isinstance(owner_note,str) or not 5<=len(owner_note.strip())<=200:
        raise ValueError("관리자 확인 사유는 5~200자여야 합니다.")
    observation = inspect_campaign(store,campaign_id)
    payload = json.dumps(observation,ensure_ascii=False,sort_keys=True,
                         separators=(",",":"))
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    with store._connect() as con:
        con.execute("BEGIN IMMEDIATE")
        company_wide_campaign.initialize(con)
        initialize(con)
        existing = con.execute("""SELECT id FROM aiwack_campaign_owner_checkpoints
            WHERE campaign_id=? AND snapshot_sha256=?""",
            (campaign_id,digest)).fetchone()
        if existing:
            return {"checkpoint_id":int(existing[0]),"existing":True,
                    "snapshot_sha256":digest,"model_called":False}
        row = con.execute("""INSERT INTO aiwack_campaign_owner_checkpoints
            (campaign_id,snapshot_json,snapshot_sha256,owner_note)
            VALUES(?,?,?,?)""",(campaign_id,payload,digest,owner_note.strip()))
        checkpoint_id = int(row.lastrowid)
    return {"checkpoint_id":checkpoint_id,"existing":False,
            "snapshot_sha256":digest,"observation_non_atomic":True,
            "model_called":False,"owner_decision_not_automatically_granted":True}


def history(store, campaign_id, limit=30):
    store.require_permission("company:manage")
    _id(campaign_id)
    if type(limit) is not int or not 1<=limit<=100:
        raise ValueError("기록 조회는 1~100건입니다.")
    with store._connect() as con:
        company_wide_campaign.initialize(con)
        initialize(con)
        rows = con.execute("""SELECT id,snapshot_json,snapshot_sha256,owner_note,created_at
            FROM aiwack_campaign_owner_checkpoints
            WHERE campaign_id=? ORDER BY id DESC LIMIT ?""",
            (campaign_id,limit)).fetchall()
    result = []
    for ident,raw,digest,note,created in rows:
        actual = hashlib.sha256(raw.encode("utf-8")).hexdigest()
        result.append({"id":int(ident),"campaign_id":campaign_id,
                       "created_at":created,"owner_note":note,
                       "snapshot_sha256":digest,"integrity_ok":actual==digest,
                       "snapshot":json.loads(raw) if actual==digest else None})
    return result
