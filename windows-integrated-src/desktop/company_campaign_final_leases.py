"""30업무 총괄 최종보고 모델의 Windows 창 간 중복 호출 방지와 수동 복구.

SQLite 잠금은 프로세스가 실제 살아 있는지 증명하지 않는다. 시간이 오래됐다는
이유만으로 잠금을 해제하지 않으며, 관리자의 별도 프로세스 확인이 필요하다.
기존 보고/모델 감사/관리자 결정 원본을 변경하지 않는다.
"""
from __future__ import annotations

import time
from uuid import uuid4

from desktop.stage87_90_management import stopped


def initialize(con) -> None:
    con.execute('''CREATE TABLE IF NOT EXISTS aiwack_campaign_final_leases(
        campaign_id INTEGER PRIMARY KEY REFERENCES aiwack_wide_campaigns(id),
        chief_employee_id INTEGER NOT NULL REFERENCES ai_employee_profiles(id),
        owner_token TEXT NOT NULL CHECK(length(owner_token)=32),
        started_epoch INTEGER NOT NULL CHECK(started_epoch>0),
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)''')
    con.execute('''CREATE TABLE IF NOT EXISTS aiwack_campaign_final_lease_recoveries(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        campaign_id INTEGER NOT NULL,
        chief_employee_id INTEGER NOT NULL,
        lease_started_epoch INTEGER NOT NULL,
        age_seconds INTEGER NOT NULL CHECK(age_seconds>=180),
        owner_confirmed INTEGER NOT NULL CHECK(owner_confirmed=1),
        recovered_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)''')
    for action in ('UPDATE','DELETE'):
        con.execute(f'''CREATE TRIGGER IF NOT EXISTS
            aiwack_campaign_final_lease_recoveries_immutable_{action.lower()}
            BEFORE {action} ON aiwack_campaign_final_lease_recoveries
            BEGIN SELECT RAISE(ABORT,'최종 보고 중단 복구 감사 변경 금지'); END''')


def reserve(store, campaign_id: int) -> str:
    """원격 창의 실모델 호출 전에 단 하나의 예약을 원자적으로 확보한다."""
    store.require_permission('company:manage')
    store.require_permission('agents:manage')
    if type(campaign_id) is not int or campaign_id <= 0:
        raise ValueError('최종 보고 협업 번호 오류')
    token=uuid4().hex
    with store._connect() as con:
        con.execute('BEGIN IMMEDIATE')
        initialize(con)
        if stopped(con):
            raise PermissionError('비상 정지 중 최종 보고 모델 호출 금지')
        plan=con.execute('''SELECT chief_employee_id,state
            FROM aiwack_wide_campaigns WHERE id=?''',(campaign_id,)).fetchone()
        if plan is None or plan[1]!='approved':
            raise ValueError('관리자 승인된 30업무 원본 협업만 최종 보고 가능')
        if con.execute('''SELECT 1 FROM aiwack_campaign_final_reports
            WHERE campaign_id=?''',(campaign_id,)).fetchone():
            raise ValueError('이미 총괄 최종 보고가 저장되어 있습니다.')
        if con.execute('''SELECT 1 FROM aiwack_campaign_final_leases
            WHERE campaign_id=?''',(campaign_id,)).fetchone():
            raise RuntimeError('다른 Windows 창에서 최종 보고 실행 중이거나 중단된 잠금이 있습니다. 관리자 수동 확인이 필요합니다.')
        con.execute('''INSERT INTO aiwack_campaign_final_leases
            (campaign_id,chief_employee_id,owner_token,started_epoch)
            VALUES(?,?,?,?)''',(campaign_id,int(plan[0]),token,int(time.time())))
    return token


def release(store, campaign_id: int, token: str) -> None:
    """실제 예약 소유 토큰만 정상 종료 잠금을 해제한다."""
    if (type(campaign_id) is not int or campaign_id <= 0
            or type(token) is not str or len(token)!=32):
        raise ValueError('최종 보고 잠금 해제 인수 오류')
    with store._connect() as con:
        con.execute('BEGIN IMMEDIATE')
        initialize(con)
        con.execute('''DELETE FROM aiwack_campaign_final_leases
            WHERE campaign_id=? AND owner_token=?''',(campaign_id,token))


def snapshot(store, limit: int = 100) -> list[dict]:
    """읽기 전용 잠금 관측: 오래된 잠금도 사망한 프로세스라고 단정하지 않는다."""
    store.require_permission('company:manage')
    if type(limit) is not int or not 1 <= limit <= 100:
        raise ValueError('최종 보고 잠금 조회는 1~100건입니다.')
    with store._connect() as con:
        initialize(con)
        rows=con.execute('''SELECT l.campaign_id,l.chief_employee_id,
            l.started_epoch,EXISTS(
              SELECT 1 FROM aiwack_campaign_final_reports r
              WHERE r.campaign_id=l.campaign_id)
            FROM aiwack_campaign_final_leases l
            ORDER BY l.started_epoch,l.campaign_id LIMIT ?''',(limit,)).fetchall()
    now=int(time.time())
    return [dict(campaign_id=int(cid),chief_employee_id=int(chief),
                 age_seconds=max(0,now-int(started)),report_exists=bool(report),
                 process_state='unknown',owner_process_inspection_required=True)
            for cid,chief,started,report in rows]


def clear_after_owner_inspection(store, campaign_id: int, *,
                                 owner_confirmed: bool = False) -> dict:
    """3분 이상 잠금, 관리자 실프로세스 직접 확인 후에만 재개 가능하게 한다.

    어떤 모델을 강제 종료하거나 기존 성공 호출을 재실행·승인하지 않는다.
    """
    store.require_permission('company:manage')
    store.require_permission('agents:manage')
    if type(campaign_id) is not int or campaign_id <= 0:
        raise ValueError('잠금 해제 대상 협업 번호 오류')
    if owner_confirmed is not True:
        raise PermissionError('다른 Windows 창과 실제 모델 프로세스 종료를 관리자가 직접 확인해야 합니다.')
    with store._connect() as con:
        con.execute('BEGIN IMMEDIATE')
        initialize(con)
        row=con.execute('''SELECT chief_employee_id,started_epoch
            FROM aiwack_campaign_final_leases WHERE campaign_id=?''',
            (campaign_id,)).fetchone()
        if row is None:
            raise ValueError('해제할 총괄 최종보고 잠금이 없습니다.')
        chief,started=int(row[0]),int(row[1])
        age=int(time.time())-started
        if age < 180:
            raise ValueError('최종 보고 잠금 생성 후 3분이 지나지 않았습니다.')
        if con.execute('''DELETE FROM aiwack_campaign_final_leases
            WHERE campaign_id=? AND started_epoch=?''',(campaign_id,started)).rowcount!=1:
            raise RuntimeError('총괄 최종보고 잠금이 동시에 변경됐습니다.')
        con.execute('''INSERT INTO aiwack_campaign_final_lease_recoveries
            (campaign_id,chief_employee_id,lease_started_epoch,age_seconds,
             owner_confirmed) VALUES(?,?,?,?,1)''',(campaign_id,chief,started,age))
    return {'campaign_id':campaign_id,'chief_employee_id':chief,
            'age_seconds':age,'owner_confirmed':True,
            'lease_cleared':True,'model_reinvoked':False,
            'report_approved':False,'actual_process_termination_proven':False}


def recovery_history(store, limit: int = 30) -> list[dict]:
    """관리자 직접 잠금 해제 영구 감사만 조회한다."""
    store.require_permission('company:manage')
    if type(limit) is not int or not 1 <= limit <= 100:
        raise ValueError('최종보고 수동 복구 감사 조회는 1~100건입니다.')
    with store._connect() as con:
        initialize(con)
        rows=con.execute('''SELECT id,campaign_id,chief_employee_id,
            age_seconds,recovered_at
            FROM aiwack_campaign_final_lease_recoveries
            ORDER BY id DESC LIMIT ?''',(limit,)).fetchall()
    return [dict(id=int(rid),campaign_id=int(cid),chief_employee_id=int(chief),
                 age_seconds=int(age),recovered_at=created,
                 owner_confirmed=True,actual_process_termination_proven=False)
            for rid,cid,chief,age,created in rows]
