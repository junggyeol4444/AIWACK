"""Stage 32: deterministic, local-only issue and *candidate* opportunity signals.

A signal is not an independently researched market opportunity.  Opportunity
rules only identify unplanned owner-authored goals and ready plans without
active tasks. Never read goal/task titles or model outputs; no AI or networking.
The caller provides a consistent SQLite snapshot.
"""
from __future__ import annotations

import sqlite3

from desktop.health_monitor import evaluate_company_health

# Fixed labels: never use user-authored text in an alert or saved history.
PROBLEM_RULES = (
    ('stale_runs', '오래 남은 실행 기록', 'critical'),
    ('urgent_blocked', '긴급 우선순위 차단 업무', 'critical'),
    ('blocked_tasks', '차단된 업무', 'attention'),
    ('unassigned_tasks', '담당자 없는 미완료 업무', 'attention'),
    ('recent_failures', '최근 24시간 실패 실행', 'attention'),
    ('pending_artifacts', '검수 대기 결과물', 'attention'),
    ('pending_chief_reports', '관리자 검토 대기 총괄 보고서', 'attention'),
)
OPPORTUNITY_RULES = (
    ('unplanned_active_goals', '활성 목표 중 진행 계획이 없는 내부 사업 검토 후보'),
    ('ready_plans_without_tasks', '실행 업무가 없는 준비 완료 계획'),
)
SAMPLE_LIMIT = 20


def _count_and_sample(con: sqlite3.Connection, from_where: str, id_column: str) -> tuple[int, list[int]]:
    """Count all matching rows, but bound displayed numeric identifiers."""
    count = int(con.execute('SELECT COUNT(*) ' + from_where).fetchone()[0])
    ids = [int(row[0]) for row in con.execute(
        'SELECT ' + id_column + ' ' + from_where + ' ORDER BY ' + id_column + ' LIMIT ?', (SAMPLE_LIMIT,)
    )]
    return count, ids


def detect_company_signals(con: sqlite3.Connection) -> dict[str, object]:
    """Read-only evaluation, independent of whether a health check was saved."""
    health = evaluate_company_health(con)
    metrics = health['metrics']
    urgent_blocked = con.execute('''
        SELECT COUNT(*) FROM company_tasks t
        JOIN company_task_priorities p ON p.task_id=t.id
        WHERE t.status='blocked' AND p.priority='urgent'
    ''').fetchone()[0]
    problem_counts = {**metrics, 'urgent_blocked': int(urgent_blocked)}
    signals: list[dict[str, object]] = []
    for code, label, severity in PROBLEM_RULES:
        count = int(problem_counts[code])
        if count:
            signals.append({'kind': 'problem', 'code': code, 'severity': severity,
                            'count': count, 'label': label, 'sample_ids': []})

    # Owner-authored, ACTIVE goals only. Archived plans do not count as active
    # planning. No market, competition, financial or revenue claim is inferred.
    unplanned_count, goal_ids = _count_and_sample(con, '''
        FROM company_goals g WHERE g.status='active'
          AND NOT EXISTS (SELECT 1 FROM company_work_plans p
                          WHERE p.goal_id=g.id AND p.status!='archived')
    ''', 'g.id')
    # A ready plan is actionable only when its goal is active. Cancelled tasks
    # do not count as actionable; other task statuses do.
    ready_count, plan_ids = _count_and_sample(con, '''
        FROM company_work_plans p JOIN company_goals g ON g.id=p.goal_id
        WHERE g.status='active' AND p.status='ready'
          AND NOT EXISTS (SELECT 1 FROM company_tasks t
                          WHERE t.plan_id=p.id AND t.status!='cancelled')
    ''', 'p.id')
    for (code, label), count, ids in zip(
        OPPORTUNITY_RULES, (unplanned_count, ready_count), (goal_ids, plan_ids)
    ):
        if count:
            signals.append({'kind': 'opportunity', 'code': code,
                            'severity': 'candidate', 'count': count,
                            'label': label, 'sample_ids': ids})
    return {
        'severity': ('critical' if any(s['severity'] == 'critical' for s in signals)
                     else 'attention' if any(s['kind'] == 'problem' for s in signals)
                     else 'ok'),
        'problem_types': sum(s['kind'] == 'problem' for s in signals),
        'opportunity_types': sum(s['kind'] == 'opportunity' for s in signals),
        'signals': signals,
        'disclaimer': '내부 데이터 기반 후보입니다. 시장 수요·수익성·실행 가능성은 검증되지 않았습니다.',
    }
