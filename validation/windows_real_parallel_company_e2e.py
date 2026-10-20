"""Genuine two-staff concurrent GGUF + sequential CEO review acceptance on Windows.

Uses the existing native company modules, no stubs or mocked model responses.
This exercises the real backend. The separately existing packaged-EXE GUI job
verifies physical mouse operations; do not confuse these two test scopes.
"""
from __future__ import annotations
import json
import os
from pathlib import Path
import sqlite3
import sys
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'windows-integrated-src'))
from desktop import company_operations as ops
from desktop.model_runtime import ModelConfig
from desktop.storage import LocalStore


def verify(cli: Path, gguf: Path, evidence: Path) -> dict:
    if os.name != 'nt':
        raise OSError('Real Windows GGUF acceptance must run on Windows')
    cli, gguf = cli.resolve(strict=True), gguf.resolve(strict=True)
    if cli.name.lower() not in ('llama-cli.exe', 'llama-completion.exe'):
        raise ValueError('Must use the preflight verified official llama.cpp runner')
    with gguf.open('rb') as stream:
        if stream.read(4) != b'GGUF':
            raise ValueError('Real GGUF header missing')
    evidence.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix='aiwack-parallel-gguf-') as temp:
        db = Path(temp) / 'company.sqlite3'
        store = LocalStore(db)
        store.setup_owner('parallel_e2e_owner', 'parallel-temporary-gguf-e2e-password-2026')
        chief = store.add_employee_draft('real_parallel_ceo', '실제 총괄 AI')
        staff = [store.add_employee_draft(f'real_parallel_staff_{i}', f'실제 직원 AI {i}')
                 for i in range(2)]
        store.assign_reporting_line(chief, 'ceo')
        model_id = store.add_local_model(ModelConfig(
            'Verified actual parallel Windows GGUF', 'llama_cpp', str(cli), str(gguf), 32))
        for employee_id in [chief] + staff:
            store.set_employee_model(employee_id, model_id)
        ids = []
        for i in range(2):
            tid = ops.create_task(store, f'승인된 실제 GGUF 독립 업무 {i + 1}',
                                  '외부 접속·결제 없이 짧은 한국어 검토 메모 작성')
            assigned = ops.assign_task(store, tid)
            assert assigned['employee_id'] == staff[i], assigned
            ops.approve_chief_order(store, tid, f'한국어로 핵심 문제 한 가지 설명. 업무 {i + 1}')
            ids.append(tid)
        expected = tuple(ids)
        employees = tuple(staff)
        ready = ops.list_approved_parallel_candidates(store)
        assert tuple(x['task_id'] for x in ready) == expected
        assert tuple(x['employee_id'] for x in ready) == employees
        result = ops.execute_approved_parallel_cycle(
            store, expected_task_ids=expected, expected_employee_ids=employees)
        assert result['staff_execution_parallel'] is True
        assert result['staff_executions'] == result['chief_reviews'] == 2
        assert result['auto_approved'] is False and result['tasks_finalized'] is False
        counts = {}
        for employee_id in [chief] + staff:
            calls = store.list_employee_model_calls(employee_id)
            needed = 2 if employee_id == chief else 1
            assert len(calls) == needed, (employee_id, calls)
            assert all(c['status'] == 'success' and c['output_chars'] > 0 for c in calls)
            counts[str(employee_id)] = needed
        for tid in expected:
            assert store.read_task(tid)['status'] == 'in_progress'
            assert store.list_task_runs(tid)[0]['status'] == 'success'
            artifact = store.list_task_artifacts(tid)[0]
            assert artifact['review_status'] == 'pending'
            assert store.find_chief_task_report(artifact['id'])['owner_decision'] == 'pending'
        with sqlite3.connect(db) as con:
            assert con.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
            assert con.execute('PRAGMA foreign_key_check').fetchall() == []
        store.logout()
        restarted = LocalStore(db)
        restarted.login('parallel_e2e_owner', 'parallel-temporary-gguf-e2e-password-2026')
        for tid in expected:
            artifact_id = restarted.list_task_artifacts(tid)[0]['id']
            assert restarted.find_chief_task_report(artifact_id)['owner_decision'] == 'pending'
            assert restarted.read_task(tid)['status'] == 'in_progress'
        report = dict(platform='Windows', actual_gguf=True, actual_parallel_staff=2,
                      sequential_real_chief_reviews=2, real_model_calls=sum(counts.values()),
                      sqlite_integrity='ok', owner_review_status='pending',
                      auto_approved=False, tasks_finalized=False)
        (evidence / 'real-parallel-gguf-audit-metadata.json').write_text(
            json.dumps(report, indent=2), encoding='utf-8')
        print('REAL_WINDOWS_TWO_STAFF_PARALLEL_GGUF_AND_CHIEF_RESTART_PASS', flush=True)
        return report


if __name__ == '__main__':
    if len(sys.argv) != 4:
        raise SystemExit('Usage: windows_real_parallel_company_e2e.py CLI GGUF EVIDENCE_DIRECTORY')
    verify(*(Path(v) for v in sys.argv[1:]))
