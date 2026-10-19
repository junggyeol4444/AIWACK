"""Stage34: conservative, deterministic offline analysis of pending task proposals.

These assessments are decision support, never proof a model can execute a task.
Only trusted source identifiers, statuses, counts and owner-assigned priority enter
rules. Free-text descriptions (including model output) are never instructions.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3

from desktop.autonomous_task_proposals import is_source_eligible


SOURCE_PRIORITY_LABELS = {'low': '낮음', 'normal': '보통', 'high': '높음', 'urgent': '긴급'}


def _source_analysis(con: sqlite3.Connection, kind: str, source_id: int) -> tuple[str, str, int, str, dict[str, object]]:
    """Return feasibility, recommended priority, score, trusted reason, inputs."""
    if kind == 'blocked_task':
        row = con.execute('''SELECT COALESCE(p.priority,'normal') FROM company_tasks t
            LEFT JOIN company_task_priorities p ON p.task_id=t.id WHERE t.id=?''',
            (source_id,)).fetchone()
        source_priority = str(row[0]) if row else 'normal'
        mapping = {'urgent': ('urgent', 95), 'high': ('high', 80),
                   'normal': ('high', 65), 'low': ('normal', 50)}
        priority, score = mapping[source_priority]
        reason = ('기존 업무가 차단되어 즉시 실행할 수 없습니다. 원인을 확인하고 '
                  f'관리자가 해결 여부를 판단해야 합니다. 원본 우선순위: {SOURCE_PRIORITY_LABELS[source_priority]}.')
        return 'needs_unblocking', priority, score, reason, {'source_priority': source_priority}
    if kind == 'ready_plan':
        steps = int(con.execute('''SELECT COUNT(*) FROM company_work_plan_steps
            WHERE plan_id=?''', (source_id,)).fetchone()[0])
        complex_plan = steps > 5
        reason = (f'준비 완료 계획의 단계가 {steps}개이며 연결된 실행 업무가 없습니다. '
                  '담당자·모델·의존성 검토가 필요합니다.' +
                  (' 작업을 더 작은 단위로 나누는 검토도 필요합니다.' if complex_plan else ''))
        return ('needs_breakdown' if complex_plan else 'needs_assignment',
                'normal', 48 if complex_plan else 58, reason, {'step_count': steps})
    if kind == 'active_goal':
        return ('needs_plan', 'low', 35,
                '활성 목표에 유효한 업무 계획이 없습니다. 계획과 자원을 정하기 전 실행 가능성을 판단할 수 없습니다.',
                {'has_plan': False})
    raise ValueError('알 수 없는 업무 제안 출처입니다.')


def assess_pending(con: sqlite3.Connection, limit: int = 100) -> dict[str, int]:
    """Call inside BEGIN IMMEDIATE; idempotent and atomic with proposal state.

    Append history only when trusted inputs or draft text change. A stale source
    is marked stale, never assessed as feasible. Does not create or run tasks.
    """
    rows = con.execute('''SELECT id,source_kind,source_id,origin,title,description
        FROM company_task_proposals WHERE status='pending' ORDER BY id LIMIT ?''',
        (limit,)).fetchall()
    result = {'evaluated': 0, 'unchanged': 0, 'stale': 0}
    for proposal_id, kind, source_id, origin, title, description in rows:
        if not is_source_eligible(con, kind, int(source_id)):
            con.execute('''UPDATE company_task_proposals
                SET status='stale',decided_at=CURRENT_TIMESTAMP
                WHERE id=? AND status='pending' ''', (proposal_id,))
            result['stale'] += 1
            continue
        feasibility, priority, score, reason, inputs = _source_analysis(con, kind, int(source_id))
        payload = {'kind': kind, 'source_id': source_id, 'origin': origin,
                   'title': title, 'description': description, 'inputs': inputs,
                   'rule_version': 1}
        signature = hashlib.sha256(json.dumps(payload, ensure_ascii=False,
                                              sort_keys=True).encode('utf-8')).hexdigest()
        previous = con.execute('''SELECT fingerprint FROM company_task_assessments
            WHERE proposal_id=? ORDER BY id DESC LIMIT 1''', (proposal_id,)).fetchone()
        if previous is not None and previous[0] == signature:
            result['unchanged'] += 1
            continue
        con.execute('''INSERT INTO company_task_assessments
            (proposal_id,fingerprint,feasibility,recommended_priority,score,reason)
            VALUES(?,?,?,?,?,?)''', (proposal_id, signature, feasibility, priority, score, reason))
        result['evaluated'] += 1
    return result
