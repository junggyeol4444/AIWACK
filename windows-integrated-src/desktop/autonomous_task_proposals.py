"""Stage 33: bounded offline rule-driven task *drafts* from local company signals.

No model inference, network, external side effects or autonomous task execution.
An authenticated owner must explicitly approve each proposal before it becomes
an ordinary unassigned todo task. The rules use numeric IDs, not untrusted text.
"""
from __future__ import annotations

import sqlite3

SOURCE_KINDS = frozenset({'active_goal', 'ready_plan', 'blocked_task'})


def is_source_eligible(con: sqlite3.Connection, kind: str, source_id: int) -> bool:
    if kind == 'active_goal':
        sql = '''SELECT 1 FROM company_goals g WHERE g.id=? AND g.status='active'
                 AND NOT EXISTS (SELECT 1 FROM company_work_plans p
                     WHERE p.goal_id=g.id AND p.status!='archived')'''
    elif kind == 'ready_plan':
        sql = '''SELECT 1 FROM company_work_plans p
                 JOIN company_goals g ON g.id=p.goal_id
                 WHERE p.id=? AND p.status='ready' AND g.status='active'
                 AND NOT EXISTS (SELECT 1 FROM company_tasks t
                     WHERE t.plan_id=p.id AND t.status!='cancelled')'''
    elif kind == 'blocked_task':
        sql = '''SELECT 1 FROM company_tasks t WHERE t.id=? AND t.status='blocked'
                 AND NOT EXISTS (SELECT 1 FROM company_task_proposals p
                     WHERE p.approved_task_id=t.id)'''
    else:
        return False
    return con.execute(sql, (source_id,)).fetchone() is not None


def source_candidates(con: sqlite3.Connection, limit: int) -> list[tuple[str, int]]:
    """Prioritize blocked work, then ready plans, then unplanned goals.

    Exclude already proposed source identities *even after rejection*, avoiding
    infinite proposal churn across restarts or periodic scans.
    """
    queries = (
        ('blocked_task', '''SELECT t.id FROM company_tasks t WHERE t.status='blocked'
            AND NOT EXISTS (SELECT 1 FROM company_task_proposals p
                WHERE p.approved_task_id=t.id)
            AND NOT EXISTS (SELECT 1 FROM company_task_proposals p
                WHERE p.source_kind='blocked_task' AND p.source_id=t.id)
            ORDER BY t.id LIMIT ?'''),
        ('ready_plan', '''SELECT p.id FROM company_work_plans p
            JOIN company_goals g ON g.id=p.goal_id
            WHERE p.status='ready' AND g.status='active'
            AND NOT EXISTS (SELECT 1 FROM company_tasks t
                WHERE t.plan_id=p.id AND t.status!='cancelled')
            AND NOT EXISTS (SELECT 1 FROM company_task_proposals q
                WHERE q.source_kind='ready_plan' AND q.source_id=p.id)
            ORDER BY p.id LIMIT ?'''),
        ('active_goal', '''SELECT g.id FROM company_goals g WHERE g.status='active'
            AND NOT EXISTS (SELECT 1 FROM company_work_plans p
                WHERE p.goal_id=g.id AND p.status!='archived')
            AND NOT EXISTS (SELECT 1 FROM company_task_proposals q
                WHERE q.source_kind='active_goal' AND q.source_id=g.id)
            ORDER BY g.id LIMIT ?'''),
    )
    found: list[tuple[str, int]] = []
    for kind, sql in queries:
        found.extend((kind, int(row[0])) for row in con.execute(sql, (limit - len(found),)))
        if len(found) >= limit:
            break
    return found


def proposal_text(kind: str, source_id: int) -> tuple[str, str]:
    if kind not in SOURCE_KINDS or type(source_id) is not int or source_id <= 0:
        raise ValueError('유효하지 않은 업무 제안 출처입니다.')
    templates = {
        'active_goal': ('활성 목표 #{id} 계획 수립 검토',
                        '로컬 활성 목표 #{id}에 진행 계획이 없습니다. 관리자가 계획 수립 필요성을 확인하세요.'),
        'ready_plan': ('준비 계획 #{id} 첫 실행 업무 검토',
                       '로컬 준비 완료 계획 #{id}에 실행 업무가 없습니다. 작업 범위와 선행 조건을 검토하세요.'),
        'blocked_task': ('차단 업무 #{id} 원인 확인',
                         '로컬 업무 #{id}가 차단 상태입니다. 원인을 확인하고 해결 방법을 검토하세요.'),
    }
    title, description = templates[kind]
    return title.format(id=source_id), description.format(id=source_id)
