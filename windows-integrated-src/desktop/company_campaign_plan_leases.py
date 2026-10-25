"""15부서 실제 총괄 GGUF 계획 생성의 Windows 창 간 중복 호출 방지.

계획 생성 중 종료되면 잠금은 자동 해제되지 않는다. 원본·모델 실행 상태를
관리자가 직접 확인한 뒤에만 복구하고, 불변 감사 원본은 유지한다.
"""
from __future__ import annotations

import time
from uuid import uuid4

from desktop import company_wide_campaign as wide
from desktop.stage87_90_management import stopped


def initialize(con) -> None:
    wide.initialize(con)
    con.execute("""CREATE TABLE IF NOT EXISTS aiwack_chief_plan_leases(
        source_task_id INTEGER PRIMARY KEY REFERENCES company_tasks(id),
        chief_employee_id INTEGER NOT NULL REFERENCES ai_employee_profiles(id),
        owner_token TEXT NOT NULL CHECK(length(owner_token)=32),
        started_epoch INTEGER NOT NULL CHECK(started_epoch>0),
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)""")
    con.execute("""CREATE TABLE IF NOT EXISTS aiwack_chief_plan_lease_recoveries(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        source_task_id INTEGER NOT NULL,
        chief_employee_id INTEGER NOT NULL,
        lease_started_epoch INTEGER NOT NULL,
        age_seconds INTEGER NOT NULL CHECK(age_seconds>=180),
        owner_confirmed INTEGER NOT NULL CHECK(owner_confirmed=1),
        recovered_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)""")
    for action in ('UPDATE', 'DELETE'):
        con.execute(f"""CREATE TRIGGER IF NOT EXISTS
            aiwack_chief_plan_lease_recovery_immutable_{action.lower()}
            BEFORE {action} ON aiwack_chief_plan_lease_recoveries
            BEGIN SELECT RAISE(ABORT,'총괄 계획 수동 복구 감사 변경 금지'); END""")


def reserve(store, source_task_id: int) -> str:
    """원자적으로 한 Windows 창만 실제 5그룹 총괄 GGUF를 호출하게 한다."""
    store.require_permission('company:manage')
    store.require_permission('agents:manage')
    if type(source_task_id) is not int or source_task_id <= 0:
        raise ValueError('총괄 계획 잠금의 원본 업무 번호 오류')
    token = uuid4().hex
    with store._connect() as con:
        con.execute('BEGIN IMMEDIATE')
        initialize(con)
        if stopped(con):
            raise PermissionError('비상 정지 중 실제 총괄 계획 모델 호출 금지')
        wide._source(store, con, source_task_id)
        chief, _model, _groups = wide._staff_roster(con)
        if con.execute("""SELECT 1 FROM aiwack_wide_campaigns
            WHERE source_task_id=? AND state IN ('draft','approved')""",
            (source_task_id,)).fetchone():
            raise ValueError('이미 진행 중인 회사 전체 협업이 있습니다.')
        if con.execute("""SELECT 1 FROM aiwack_chief_plan_leases
            WHERE source_task_id=?""", (source_task_id,)).fetchone():
            raise RuntimeError('다른 Windows 창의 실제 총괄 계획이 실행 중이거나 중단됐습니다. 관리자 수동 확인이 필요합니다.')
        con.execute("""INSERT INTO aiwack_chief_plan_leases
            (source_task_id,chief_employee_id,owner_token,started_epoch)
            VALUES(?,?,?,?)""", (source_task_id,chief,token,int(time.time())))
    return token


def release(store, source_task_id: int, token: str) -> None:
    """정상 종료된 동일 호출 소유 토큰의 잠금만 제거한다."""
    if (type(source_task_id) is not int or source_task_id <= 0
            or type(token) is not str or len(token) != 32):
        raise ValueError('총괄 계획 잠금 해제 인수 오류')
    with store._connect() as con:
        con.execute('BEGIN IMMEDIATE')
        initialize(con)
        con.execute("""DELETE FROM aiwack_chief_plan_leases
            WHERE source_task_id=? AND owner_token=?""", (source_task_id,token))


def snapshot(store, limit: int = 100) -> list[dict]:
    store.require_permission('company:manage')
    if type(limit) is not int or not 1 <= limit <= 100:
        raise ValueError('총괄 계획 잠금 조회는 1~100건입니다.')
    with store._connect() as con:
        initialize(con)
        rows = con.execute("""SELECT l.source_task_id,l.chief_employee_id,
            l.started_epoch,EXISTS(
                SELECT 1 FROM aiwack_wide_campaigns c
                WHERE c.source_task_id=l.source_task_id
                  AND c.state IN ('draft','approved')),
            (SELECT COUNT(*) FROM ai_model_call_history h
             WHERE h.employee_id=l.chief_employee_id AND h.status='running')
            FROM aiwack_chief_plan_leases l
            ORDER BY l.started_epoch,l.source_task_id LIMIT ?""",(limit,)).fetchall()
    now=int(time.time())
    return [dict(source_task_id=int(source),chief_employee_id=int(chief),
                 age_seconds=max(0,now-int(start)),draft_or_approved_exists=bool(saved),
                 sqlite_chief_model_calls_running=int(running),
                 process_state='unknown',owner_process_inspection_required=True)
            for source,chief,start,saved,running in rows]


def clear_after_owner_inspection(store, source_task_id: int, *,
                                 owner_confirmed: bool = False) -> dict:
    store.require_permission('company:manage')
    store.require_permission('agents:manage')
    if type(source_task_id) is not int or source_task_id <= 0:
        raise ValueError('총괄 계획 복구 대상 업무 번호 오류')
    if owner_confirmed is not True:
        raise PermissionError('다른 Windows 창과 실제 모델 프로세스 종료를 직접 확인해야 합니다.')
    with store._connect() as con:
        con.execute('BEGIN IMMEDIATE')
        initialize(con)
        row=con.execute("""SELECT chief_employee_id,started_epoch
            FROM aiwack_chief_plan_leases WHERE source_task_id=?""",
            (source_task_id,)).fetchone()
        if row is None:
            raise ValueError('해제할 총괄 계획 잠금이 없습니다.')
        chief,started=int(row[0]),int(row[1])
        age=int(time.time())-started
        if age < 180:
            raise ValueError('총괄 계획 잠금 생성 후 3분이 지나지 않았습니다.')
        if con.execute("""SELECT 1 FROM ai_model_call_history
            WHERE employee_id=? AND status='running' LIMIT 1""",
            (chief,)).fetchone():
            raise RuntimeError('총괄 모델 실행 중 기록이 있습니다. 실제 중단 모델 감사부터 확인하세요.')
        if con.execute("""SELECT 1 FROM aiwack_wide_campaigns
            WHERE source_task_id=? AND state IN ('draft','approved')""",
            (source_task_id,)).fetchone():
            raise RuntimeError('이미 저장된 총괄 계획이 있습니다. 중단 잠금을 임의로 해제하지 않습니다.')
        if con.execute("""DELETE FROM aiwack_chief_plan_leases
            WHERE source_task_id=? AND started_epoch=?""",
            (source_task_id,started)).rowcount != 1:
            raise RuntimeError('총괄 계획 잠금이 동시에 변경됐습니다.')
        con.execute("""INSERT INTO aiwack_chief_plan_lease_recoveries
            (source_task_id,chief_employee_id,lease_started_epoch,
             age_seconds,owner_confirmed) VALUES(?,?,?,?,1)""",
            (source_task_id,chief,started,age))
    return {'source_task_id':source_task_id,'chief_employee_id':chief,
            'age_seconds':age,'owner_confirmed':True,'lease_cleared':True,
            'model_reinvoked':False,'actual_process_termination_proven':False}


def recovery_history(store, limit: int = 30) -> list[dict]:
    store.require_permission('company:manage')
    if type(limit) is not int or not 1 <= limit <= 100:
        raise ValueError('총괄 계획 잠금 복구 감사 조회는 1~100건입니다.')
    with store._connect() as con:
        initialize(con)
        rows=con.execute("""SELECT id,source_task_id,chief_employee_id,
            age_seconds,recovered_at FROM aiwack_chief_plan_lease_recoveries
            ORDER BY id DESC LIMIT ?""",(limit,)).fetchall()
    return [dict(id=int(rid),source_task_id=int(source),
                 chief_employee_id=int(chief),age_seconds=int(age),
                 recovered_at=created,owner_confirmed=True,
                 actual_process_termination_proven=False)
            for rid,source,chief,age,created in rows]
