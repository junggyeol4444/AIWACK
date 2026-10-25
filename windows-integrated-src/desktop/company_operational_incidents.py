"""운영 중단·장기 검수 지연의 실제 SQLite 근거를 보존하는 관리자 대응 큐.

오래된 running 행은 프로세스 사망 증거가 아니다. 이 모듈은 기존
직원/총괄 결과를 변경하거나 모델을 재실행하지 않는다.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
from desktop.stage87_90_management import stopped

SOURCES = {
    "staff_running": ("company_task_runs", "status", "running"),
    "tick_running": ("aiwack_autopilot_runs", "state", "running"),
    "model_running": ("aiwack_autopilot_model_runs", "state", "running"),
    "artifact_pending": ("company_task_artifacts", "review_status", "pending"),
    "chief_pending": ("company_chief_task_reports", "owner_decision", "pending"),
}


def _digest(value):
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True,
                     separators=(",", ":"))
    return raw, hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _note(value):
    if not isinstance(value, str) or not 5 <= len(value.strip()) <= 200:
        raise ValueError("관리자 판단 사유는 5~200자입니다.")
    return value.strip()


def initialize(con):
    con.execute("""CREATE TABLE IF NOT EXISTS aiwack_operational_incidents(
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      source_kind TEXT NOT NULL CHECK(source_kind IN
        ('staff_running','tick_running','model_running',
         'artifact_pending','chief_pending')),
      source_id INTEGER NOT NULL CHECK(source_id>0),
      evidence_json TEXT NOT NULL,
      evidence_sha256 TEXT NOT NULL CHECK(length(evidence_sha256)=64),
      detected_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
      UNIQUE(source_kind,source_id))""")
    con.execute("""CREATE TABLE IF NOT EXISTS aiwack_operational_incident_decisions(
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      incident_id INTEGER NOT NULL UNIQUE REFERENCES aiwack_operational_incidents(id),
      decision TEXT NOT NULL CHECK(decision IN ('acknowledged','followup','dismissed')),
      owner_note TEXT NOT NULL CHECK(length(owner_note) BETWEEN 5 AND 200),
      followup_task_id INTEGER UNIQUE REFERENCES company_tasks(id),
      decided_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
      CHECK((decision='followup' AND followup_task_id IS NOT NULL)
        OR (decision!='followup' AND followup_task_id IS NULL)))""")
    for table in ("aiwack_operational_incidents", "aiwack_operational_incident_decisions"):
        for op in ("UPDATE", "DELETE"):
            con.execute(f"""CREATE TRIGGER IF NOT EXISTS {table}_immutable_{op.lower()}
              BEFORE {op} ON {table}
              BEGIN SELECT RAISE(ABORT,'운영 이상 원본 감사 변경 금지'); END""")


def _source_rows(con, kind, minimum_age, limit):
    table, state_column, state = SOURCES[kind]
    date_column = {
        "staff_running": "started_at", "tick_running": "started_at",
        "model_running": "created_at", "artifact_pending": "created_at",
        "chief_pending": "created_at",
    }[kind]
    # Identifiers are exclusively from the fixed internal whitelist above.
    sql = f"""SELECT id,CAST((julianday('now')-julianday({date_column}))*86400 AS INTEGER)
              FROM {table} WHERE {state_column}=? AND
              (julianday('now')-julianday({date_column}))*86400>=?
              ORDER BY id LIMIT ?"""
    return [(int(row[0]), int(row[1])) for row in
            con.execute(sql, (state, minimum_age, limit))
            if row[1] is not None and int(row[1]) >= minimum_age]


def scan(store, *, running_age=1800, review_age=86400, limit=100):
    """기존 원본에서만 탐지; 같은 원본 행에 이상 감사는 최대 한 건."""
    store.require_permission("company:manage")
    if (type(running_age) is not int or not 180 <= running_age <= 604800
            or type(review_age) is not int or not 3600 <= review_age <= 2592000
            or type(limit) is not int or not 1 <= limit <= 100):
        raise ValueError("운영 탐지 기간 또는 조회 건수 오류")
    from desktop import company_autopilot
    company_autopilot.initialize(store)
    created = []
    with store._connect() as con:
        con.execute("BEGIN IMMEDIATE")
        initialize(con)
        if stopped(con):
            return {"created": [], "blocked": "emergency_stop"}
        for kind in SOURCES:
            threshold = review_age if kind.endswith("pending") else running_age
            for source_id, age in _source_rows(con, kind, threshold, limit):
                if len(created) >= limit:
                    break
                evidence = {"source_kind": kind, "source_id": source_id,
                            "observed_age_seconds": age,
                            "process_liveness_verified": False,
                            "external_action_executed": False}
                raw, sha = _digest(evidence)
                cur = con.execute("""INSERT OR IGNORE INTO aiwack_operational_incidents
                  (source_kind,source_id,evidence_json,evidence_sha256)
                  VALUES(?,?,?,?)""", (kind, source_id, raw, sha))
                if cur.rowcount == 1:
                    created.append(int(cur.lastrowid))
            if len(created) >= limit:
                break
    return {"created": created, "requires_owner_review": True,
            "model_called": False, "external_action_executed": False,
            "stale_means_process_dead": False}


def _current(con, kind, source_id):
    table, column, _ = SOURCES[kind]
    row = con.execute(f"SELECT {column} FROM {table} WHERE id=?",
                      (source_id,)).fetchone()
    return str(row[0]) if row else None


def history(store, limit=50):
    store.require_permission("company:manage")
    from desktop import company_autopilot
    company_autopilot.initialize(store)
    if type(limit) is not int or not 1 <= limit <= 100:
        raise ValueError("운영 이상 조회 건수는 1~100입니다.")
    with store._connect() as con:
        initialize(con)
        rows = con.execute("""SELECT i.id,i.source_kind,i.source_id,
             i.evidence_json,i.evidence_sha256,i.detected_at,
             d.decision,d.followup_task_id,d.decided_at
             FROM aiwack_operational_incidents i
             LEFT JOIN aiwack_operational_incident_decisions d
               ON d.incident_id=i.id ORDER BY i.id DESC LIMIT ?""",
             (limit,)).fetchall()
        result = []
        for row in rows:
            raw, sha = row[3], row[4]
            if hashlib.sha256(raw.encode("utf-8")).hexdigest() != sha:
                raise ValueError("운영 이상 감사 SHA256 불일치")
            result.append({
                "id": int(row[0]), "kind": row[1], "source_id": int(row[2]),
                "evidence": json.loads(raw), "evidence_sha256": sha,
                "detected_at": row[5], "decision": row[6],
                "followup_task_id": row[7], "decided_at": row[8],
                "current_source_state": _current(con, row[1], int(row[2])),
                "process_liveness_verified": False,
            })
    return result


def decide(store, incident_id, decision, owner_note):
    store.require_permission("company:manage")
    if type(incident_id) is not int or incident_id <= 0:
        raise ValueError("운영 이상 번호 오류")
    if decision not in ("acknowledged", "followup", "dismissed"):
        raise ValueError("관리자 확인/후속업무/반려만 허용합니다.")
    note = _note(owner_note)
    with store._connect() as con:
        con.execute("BEGIN IMMEDIATE")
        initialize(con)
        if stopped(con):
            raise PermissionError("비상정지 중 운영 이상 처리 금지")
        row = con.execute("""SELECT source_kind,source_id,evidence_json,
            evidence_sha256 FROM aiwack_operational_incidents WHERE id=?""",
            (incident_id,)).fetchone()
        if not row:
            raise ValueError("운영 이상 원본을 찾을 수 없습니다.")
        kind, source_id, raw, sha = row
        if hashlib.sha256(raw.encode("utf-8")).hexdigest() != sha:
            raise ValueError("운영 이상 근거가 변경되었습니다.")
        if con.execute("""SELECT 1 FROM aiwack_operational_incident_decisions
            WHERE incident_id=?""", (incident_id,)).fetchone():
            raise ValueError("이미 관리자 판단이 확정된 이상입니다.")
        current = _current(con, kind, source_id)
        task_id = None
        if decision == "followup":
            if current != SOURCES[kind][2]:
                raise ValueError("원본 상태가 변경되었습니다. 다시 조회한 뒤 판단하세요.")
            title = f"운영 이상 확인: {kind} #{source_id}"
            detail = (f"기존 운영 이상 #{incident_id}의 실제 SQLite 감사 SHA256 {sha}. "
                      f"관리자 사유: {note}. 실제 프로세스 상태 확인·검수 후 별도 승인 필요. "
                      "AI 자동 재호출·외부 조치는 수행하지 않습니다.")
            task_id = int(con.execute("""INSERT INTO company_tasks(title,description)
                VALUES(?,?)""", (title, detail[:1000])).lastrowid)
            con.execute("""INSERT INTO company_task_status_events
                (task_id,old_status,new_status) VALUES(?,NULL,'todo')""",
                (task_id,))
        decision_id = int(con.execute("""INSERT INTO aiwack_operational_incident_decisions
            (incident_id,decision,owner_note,followup_task_id)
            VALUES(?,?,?,?)""", (incident_id, decision, note, task_id)).lastrowid)
    return {"decision_id": decision_id, "incident_id": incident_id,
            "followup_task_id": task_id, "model_called": False,
            "process_terminated": False, "owner_approval_required_for_execution": True}
