"""Real Windows-native subprocess-to-task-to-artifact acceptance test.

The supplied exe is a deterministic SYNTHETIC test binary, never a GGUF model.
This validates subprocess plumbing, SQLite review state and restart durability.
No real AI capability or business work is claimed by passing this test.
"""
from __future__ import annotations
import tempfile
import sys
from pathlib import Path

from desktop.model_runtime import ModelConfig
from desktop.storage import LocalStore, AuthenticationError
from desktop import company_operations as office


def run(stub: Path) -> None:
    assert stub.is_file() and stub.name.lower() == 'aiwack-modelstub.exe'
    with tempfile.TemporaryDirectory(prefix='aiwack-win-stub-') as directory:
        database = Path(directory) / 'company.sqlite3'
        owner = LocalStore(database)
        owner.setup_owner('acceptance_owner', 'local-acceptance-password-2026')
        worker = owner.add_employee_draft('win_worker', 'Windows 실제 모델 호출 경로')
        model = office.connect_employee_model(owner, worker,
            ModelConfig('Windows synthetic native test runner', 'llamafile', str(stub), '', 32))
        assert owner.read_employee_model(worker)['model_id'] == model
        text = office.probe_employee_model(owner, worker)
        assert text.startswith('AIWACK_WINDOWS_NATIVE_CLI')
        calls = owner.list_employee_model_calls(worker)
        assert len(calls) == 1 and calls[0]['status'] == 'success'
        task_id = office.create_task(owner, 'Windows real executable integration test',
                                     'This task is a synthetic test, not a customer deliverable')
        assigned = office.assign_task(owner, task_id)
        assert assigned['employee_id'] == worker
        result = office.execute_task(owner, task_id)
        assert result['status'] == 'awaiting_owner_review'
        assert 'AIWACK_WINDOWS_NATIVE_CLI' in result['response']
        artifact_id = result['artifact_id']
        record = owner.read_task_artifact(artifact_id)
        assert record['review_status'] == 'pending'
        assert owner.read_task(task_id)['status'] == 'in_progress'
        assert owner.list_task_runs(task_id)[0]['status'] == 'success'
        owner.logout()
        locked = LocalStore(database)
        try:
            office.company_snapshot(locked)
        except AuthenticationError:
            pass
        else:
            raise AssertionError('Owner-only company snapshot accessible without login')
        locked.login('acceptance_owner', 'local-acceptance-password-2026')
        assert locked.read_task_artifact(artifact_id)['review_status'] == 'pending'
        locked.review_task_artifact(artifact_id, 'approved')
        assert locked.read_task_artifact(artifact_id)['review_status'] == 'approved'
        assert locked.read_task(task_id)['status'] != 'done'
        assert office.finalize_approved_artifact(locked, artifact_id)==task_id
        assert locked.read_task(task_id)['status']=='done'
        assert not office.company_snapshot(locked)['actual_sales_verified']
        print('WINDOWS_SYNTHETIC_NATIVE_WORKER_SUBPROCESS_TO_REVIEW_PASS',
              {'model_id': model, 'task_id': task_id, 'artifact_id': artifact_id,
               'actual_gguf_inference': False, 'real_sales': False}, flush=True)


if __name__ == '__main__':
    if len(sys.argv) != 2:
        raise SystemExit('Provide actual Windows-native synthetic executable path')
    run(Path(sys.argv[1]).resolve())
