"""Stage35: deterministic, local breakdown of existing complex work plans.

This module treats work-plan text as *data*, never executable instructions.
A draft is not a task. Owner approval in LocalStore is the only path that
materializes tasks, and even that never starts an AI/model/process.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3

MIN_COMPLEX_STEPS = 6
MAX_STEPS = 30
RULE_VERSION = 1


def source_snapshot(con: sqlite3.Connection, plan_id: int) -> tuple[str, list[str]] | None:
    """Read one eligible plan and its ordered steps from the current transaction."""
    row = con.execute('''SELECT p.title,p.description,p.status,g.status
        FROM company_work_plans p JOIN company_goals g ON g.id=p.goal_id
        WHERE p.id=?''', (plan_id,)).fetchone()
    if row is None or row[2] != 'ready' or row[3] != 'active':
        return None
    # Never generate or apply a second task set over existing plan tasks,
    # including cancelled tasks (auditability and duplicate prevention).
    if con.execute('SELECT 1 FROM company_tasks WHERE plan_id=? LIMIT 1', (plan_id,)).fetchone():
        return None
    steps = [str(r[0]) for r in con.execute('''SELECT instruction
        FROM company_work_plan_steps WHERE plan_id=? ORDER BY position''', (plan_id,))]
    if not MIN_COMPLEX_STEPS <= len(steps) <= MAX_STEPS:
        return None
    payload = {'version': RULE_VERSION, 'plan_id': plan_id,
               'title': row[0], 'description': row[1], 'status': row[2],
               'goal_status': row[3], 'steps': steps}
    fingerprint = hashlib.sha256(json.dumps(payload, ensure_ascii=False,
                                             sort_keys=True).encode('utf-8')).hexdigest()
    return fingerprint, steps


def detail_items(steps: list[str]) -> list[tuple[int, str, str, int | None]]:
    """One bounded reviewable task per source step, sequential dependency proposal.

    This is structural decomposition, not semantic AI planning or proof that the
    order/acceptance criteria are appropriate for real-world execution.
    """
    if not MIN_COMPLEX_STEPS <= len(steps) <= MAX_STEPS:
        raise ValueError('복합 계획은 6~30개의 실행 단계가 필요합니다.')
    items = []
    for position, raw in enumerate(steps, 1):
        instruction = raw.strip()
        if not instruction or len(instruction) > 200:
            raise ValueError('실행 단계는 1~200자여야 합니다.')
        title = f'{position:02d}단계 · {instruction}'[:120]
        detail = (f'원본 계획 단계 {position}/{len(steps)}: {instruction}\n'
                  '완료 기준(관리자 확인 필요): 해당 단계의 산출물·완료 여부 검토.\n'
                  '순서 및 선행 조건은 실제 실행 전에 관리자가 검토해야 합니다.')
        items.append((position, title, detail, position - 1 if position > 1 else None))
    return items
