"""Stage 31: deterministic, read-only company-health evaluation.

Only aggregate local SQLite metadata is inspected.  No LLM, model process,
network, task creation, task state mutation, or background OS service.
The GUI controls when the evaluator runs; it can optionally persist a summary.
"""
from __future__ import annotations

import sqlite3

# Stable codes; no user-entered task text, prompts, or artifact bodies in alerts.
HEALTH_LABELS = {
    'blocked_tasks': '차단된 업무',
    'unassigned_tasks': '담당자 없는 미완료 업무',
    'pending_artifacts': '검수 대기 결과물',
    'pending_chief_reports': '관리자 검토 대기 총괄 보고서',
    'stale_runs': '1시간 넘게 실행 중으로 남은 기록',
    'stale_chief_review_leases': '3분 넘은 총괄 검토 잠금(프로세스 생존 여부 수동 확인)',
    'recent_failures': '최근 24시간 실패·시간초과·중단 실행',
}
CRITICAL_CODES = frozenset({'stale_runs', 'stale_chief_review_leases'})


def evaluate_company_health(con: sqlite3.Connection) -> dict[str, object]:
    """Evaluate one SQLite snapshot without changing business records.

    Caller holds a read or immediate transaction. Running jobs under one hour
    are normal, and old failures outside the 24h window are not counted.
    """
    task_counts = dict(con.execute(
        "SELECT status,COUNT(*) FROM company_tasks GROUP BY status"))
    metrics = {
        'tasks_total': sum(task_counts.values()),
        'todo': task_counts.get('todo', 0),
        'in_progress': task_counts.get('in_progress', 0),
        'blocked_tasks': task_counts.get('blocked', 0),
        'done': task_counts.get('done', 0),
        'unassigned_tasks': con.execute("""
            SELECT COUNT(*) FROM company_tasks t
            LEFT JOIN company_task_assignments a ON a.task_id=t.id
            WHERE t.status IN ('todo','in_progress','blocked') AND a.task_id IS NULL
        """).fetchone()[0],
        'pending_artifacts': con.execute("""
            SELECT COUNT(*) FROM company_task_artifacts WHERE review_status='pending'
        """).fetchone()[0],
        'pending_chief_reports': con.execute("""
            SELECT COUNT(*) FROM company_chief_task_reports WHERE owner_decision='pending'
        """).fetchone()[0],
        'stale_runs': con.execute("""
            SELECT COUNT(*) FROM company_task_runs
            WHERE status='running' AND started_at < datetime('now','-1 hour')
        """).fetchone()[0],
        'recent_failures': con.execute("""
            SELECT COUNT(*) FROM company_task_runs
            WHERE status IN ('failure','timeout','interrupted')
              AND started_at >= datetime('now','-24 hours')
        """).fetchone()[0],
    }
    lease_table_exists=con.execute("SELECT 1 FROM sqlite_master WHERE type='table' "
                                   "AND name='aiwack_chief_review_leases'").fetchone()
    metrics['stale_chief_review_leases']=(con.execute(
        "SELECT COUNT(*) FROM aiwack_chief_review_leases "
        "WHERE started_epoch < CAST(strftime('%s','now') AS INTEGER)-180"
    ).fetchone()[0] if lease_table_exists else 0)
    issues = [{'code': code, 'count': int(metrics[code]), 'label': label}
              for code, label in HEALTH_LABELS.items() if metrics[code] > 0]
    severity = ('critical' if any(x['code'] in CRITICAL_CODES for x in issues)
                else 'attention' if issues else 'ok')
    return {'severity': severity, 'metrics': metrics, 'issues': issues}
