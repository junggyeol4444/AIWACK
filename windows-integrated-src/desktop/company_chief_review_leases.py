"""Durable SQLite single-owner leases for native chief-model reviews.

A model process cannot be identified reliably from a different Windows login
session. Never infer that a lease is dead from age alone. Recovery is an
explicit owner action after checking that no subprocess is still running.
"""
from __future__ import annotations

import time
from uuid import uuid4


def initialize(con) -> None:
    con.execute('''CREATE TABLE IF NOT EXISTS aiwack_chief_review_leases(
        artifact_id INTEGER PRIMARY KEY REFERENCES company_task_artifacts(id),
        owner_token TEXT NOT NULL CHECK(length(owner_token)=32),
        started_epoch INTEGER NOT NULL,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)''')


def reserve(store, artifact_id: int) -> str:
    """Atomically exclude a second chief invocation for one saved artifact."""
    store.require_permission('company:manage')
    store.require_permission('agents:manage')
    if type(artifact_id) is not int or artifact_id < 1:
        raise ValueError('총괄 검토 결과물 번호가 올바르지 않습니다.')
    token = uuid4().hex
    with store._connect() as con:
        con.execute('BEGIN IMMEDIATE')
        initialize(con)
        from desktop.stage87_90_management import stopped
        if stopped(con):
            raise PermissionError('비상 정지 상태에서는 총괄 AI 검토를 시작할 수 없습니다.')
        eligible = con.execute('''SELECT 1 FROM company_task_artifacts a
            JOIN company_chief_task_dispatches d ON d.run_id=a.run_id
            JOIN company_task_runs r ON r.id=a.run_id AND r.task_id=a.task_id
            JOIN ai_model_call_history h ON h.id=r.model_call_id AND h.status='success'
            WHERE a.id=? AND r.status='success' ''', (artifact_id,)).fetchone()
        if not eligible:
            raise ValueError('승인된 총괄 AI 지시에서 성공한 직원 실행의 결과물만 회수할 수 있습니다.')
        if con.execute('SELECT 1 FROM company_chief_task_reports WHERE artifact_id=?',
                       (artifact_id,)).fetchone():
            raise ValueError('이미 저장된 총괄 검토 보고서가 있습니다.')
        if con.execute('SELECT 1 FROM aiwack_chief_review_leases WHERE artifact_id=?',
                       (artifact_id,)).fetchone():
            raise RuntimeError('다른 Windows 창에서 총괄 AI 검토 중이거나 중단된 잠금이 있습니다. 복구 화면에서 확인하세요.')
        con.execute('''INSERT INTO aiwack_chief_review_leases(
            artifact_id,owner_token,started_epoch) VALUES(?,?,?)''',
            (artifact_id, token, int(time.time())))
    return token


def release(store, artifact_id: int, token: str) -> None:
    """A different session can never release a live lease by guessing its ID."""
    if type(artifact_id) is not int or artifact_id < 1 or type(token) is not str:
        raise ValueError('총괄 검토 잠금 해제 인수가 올바르지 않습니다.')
    with store._connect() as con:
        con.execute('BEGIN IMMEDIATE')
        initialize(con)
        con.execute('''DELETE FROM aiwack_chief_review_leases
            WHERE artifact_id=? AND owner_token=?''', (artifact_id, token))


def snapshot(store, limit: int = 100) -> list[dict]:
    """Owner-only, read-only lease status; not a live-process assertion."""
    store.require_permission('company:manage')
    if type(limit) is not int or not 1 <= limit <= 100:
        raise ValueError('총괄 검토 잠금 조회는 1~100건입니다.')
    with store._connect() as con:
        initialize(con)
        rows = con.execute('''SELECT l.artifact_id,a.task_id,l.started_epoch,
            EXISTS(SELECT 1 FROM company_chief_task_reports r
                   WHERE r.artifact_id=l.artifact_id)
            FROM aiwack_chief_review_leases l
            JOIN company_task_artifacts a ON a.id=l.artifact_id
            ORDER BY l.started_epoch,l.artifact_id LIMIT ?''', (limit,)).fetchall()
    now = int(time.time())
    return [dict(artifact_id=int(aid), task_id=int(tid),
                 age_seconds=max(0, now-int(started)), report_exists=bool(report),
                 process_state='unknown', owner_confirmation_required=True)
            for aid,tid,started,report in rows]


def clear_after_owner_inspection(store, artifact_id: int, *,
                                 owner_confirmed: bool = False) -> None:
    """Clear an orphaned lease ONLY after physical owner verifies no live run.

    An age threshold prevents an accidental click from clearing a recently
    started review; age does not prove the subprocess is dead.
    """
    store.require_permission('company:manage')
    store.require_permission('agents:manage')
    if type(artifact_id) is not int or artifact_id < 1:
        raise ValueError('잠금 해제할 결과물 번호가 올바르지 않습니다.')
    if owner_confirmed is not True:
        raise PermissionError('실행 중인 모델 프로세스가 없음을 관리자가 직접 확인해야 합니다.')
    with store._connect() as con:
        con.execute('BEGIN IMMEDIATE')
        initialize(con)
        row=con.execute('''SELECT started_epoch FROM aiwack_chief_review_leases
            WHERE artifact_id=?''',(artifact_id,)).fetchone()
        if row is None:
            raise ValueError('해제할 총괄 검토 잠금이 없습니다.')
        if int(time.time())-int(row[0]) < 180:
            raise ValueError('잠금 생성 후 3분이 지나지 않았습니다. 진행 중인 모델을 보호합니다.')
        con.execute('DELETE FROM aiwack_chief_review_leases WHERE artifact_id=?',
                    (artifact_id,))
