"""Native Windows-subprocess staff integration test. The executable is synthetic,
not a real GGUF inference model. Records task, audit and approval correctly.
"""
import tempfile
import sys
from pathlib import Path
from desktop.model_runtime import ModelConfig
from desktop.storage import LocalStore, AuthenticationError
from desktop import company_operations as office

def run(stub):
    assert stub.is_file() and stub.name.lower() == 'aiwack-modelstub.exe'
    with tempfile.TemporaryDirectory(prefix='aiwack-native-win-') as directory:
        database=Path(directory)/'company.sqlite3'
        owner=LocalStore(database)
        owner.setup_owner('acceptance_owner','local-acceptance-password-2026')
        worker=owner.add_employee_draft('win_worker','Windows 실제 모델 호출 경로')
        model=office.connect_employee_model(owner,worker,ModelConfig(
            'Windows synthetic model runner','llamafile',str(stub),'',32))
        assert owner.read_employee_model(worker)['model_id']==model
        response=office.probe_employee_model(owner,worker)
        assert response.startswith('AIWACK_WINDOWS_NATIVE_CLI')
        calls=owner.list_employee_model_calls(worker)
        assert len(calls)==1 and calls[0]['status']=='success'
        task=office.create_task(owner,'Windows synthetic native subprocess task',
            'Local integration test only, not a customer deliverable')
        assert office.assign_task(owner,task)['employee_id']==worker
        result=office.execute_task(owner,task)
        assert result['status']=='awaiting_owner_review'
        assert 'AIWACK_WINDOWS_NATIVE_CLI' in result['response']
        artifact=result['artifact_id']
        assert owner.read_task_artifact(artifact)['review_status']=='pending'
        assert owner.read_task(task)['status']=='in_progress'
        assert owner.list_task_runs(task)[0]['status']=='success'
        owner.logout()
        locked=LocalStore(database)
        try:
            office.company_snapshot(locked)
        except AuthenticationError:
            pass
        else:
            raise AssertionError('Unauthenticated company access succeeded')
        locked.login('acceptance_owner','local-acceptance-password-2026')
        assert locked.read_task_artifact(artifact)['review_status']=='pending'
        locked.review_task_artifact(artifact,'approved')
        assert locked.read_task_artifact(artifact)['review_status']=='approved'
        assert locked.read_task(task)['status']!='done'
        assert office.company_snapshot(locked)['actual_sales_verified'] is False
        print('WINDOWS_SYNTHETIC_NATIVE_WORKER_TO_REVIEW_PASS',
              {'task_id':task,'artifact_id':artifact,
               'actual_gguf_inference':False,'real_sales':False},flush=True)

if __name__=='__main__':
    if len(sys.argv)!=2:raise SystemExit('Usage: script NATIVE_STUB_EXE')
    run(Path(sys.argv[1]).resolve())
