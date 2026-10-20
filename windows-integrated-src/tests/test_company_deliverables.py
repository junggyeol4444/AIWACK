"""Actual owner-reviewed artifact export, file safety and deterministic QA."""
import hashlib
import pytest
import sys
from desktop.storage import LocalStore
from desktop.model_runtime import ModelConfig
from desktop import company_operations as ops
from desktop import company_deliverables as dl


@pytest.fixture
def artifact(tmp_path,monkeypatch):
    store=LocalStore(tmp_path/'deliverables.sqlite3')
    store.setup_owner('deliver_owner','deliver-owner-password-2026')
    chief=store.add_employee_draft('deliver_chief','Chief')
    staff=store.add_employee_draft('deliver_staff','Staff')
    store.assign_reporting_line(chief,'ceo')
    model=store.add_local_model(ModelConfig('SyntheticWork','llamafile',sys.executable,'',32))
    store.set_employee_model(chief,model)
    store.set_employee_model(staff,model)
    task=ops.create_task(store,'Owner reviewed deliverable')
    ops.assign_task(store,task)
    monkeypatch.setattr('desktop.task_runtime.run_local_model',lambda *a,**k:'SYNTHETIC VERIFIED TEXT '*10)
    aid=int(ops.execute_task(store,task)['artifact_id'])
    return store,task,aid,tmp_path/'outputs'


def test_quality_never_auto_approves_and_detects_placeholder(artifact):
    store,task,aid,folder=artifact
    q=dl.check_quality(store,aid)
    assert q['integrity_ok'] and q['machine_checks_only']
    assert not q['automatically_approved']
    assert store.read_task_artifact(aid)['review_status']=='pending'


def test_unapproved_artifact_never_written(artifact):
    store,task,aid,folder=artifact
    with pytest.raises(PermissionError):
        dl.export_approved(store,aid,root=folder)
    assert not (folder/'approved_deliverables').exists()


def test_real_approved_markdown_written_once_and_reopen_verified(artifact):
    store,task,aid,folder=artifact
    store.review_task_artifact(aid,'approved')
    result=dl.export_approved(store,aid,root=folder)
    assert result['owner_approved'] and not result['published_externally']
    path=result['path']
    assert (folder/'approved_deliverables').exists()
    from pathlib import Path
    assert dl.verify_exports(store,root=folder)==[
        {'artifact_id':aid,'file_name':Path(path).name,'integrity_ok':True}]
    again=dl.export_approved(store,aid,root=folder)
    assert again['path']==path
    store.logout()
    reopened=LocalStore(store.path)
    reopened.login('deliver_owner','deliver-owner-password-2026')
    assert dl.verify_exports(reopened,root=folder)[0]['integrity_ok']


def test_export_never_overwrites_owner_modified_file(artifact):
    store,task,aid,folder=artifact
    store.review_task_artifact(aid,'approved')
    result=dl.export_approved(store,aid,root=folder)
    from pathlib import Path
    p=Path(result['path'])
    p.write_text('OWNER CHANGED THIS FILE',encoding='utf-8')
    with pytest.raises(FileExistsError):
        dl.export_approved(store,aid,root=folder)
    assert dl.verify_exports(store,root=folder)[0]['integrity_ok'] is False


def test_invalid_id_and_outside_symlink_refused(artifact):
    store,task,aid,folder=artifact
    with pytest.raises(ValueError):dl.export_approved(store,True,root=folder)
    store.review_task_artifact(aid,'approved')
    folder.mkdir()
    external=folder.parent/'outside'
    external.mkdir()
    try:
        (folder/'approved_deliverables').symlink_to(external,target_is_directory=True)
    except OSError as exc:
        # Some Windows runners deny creation of symlinks without privilege.
        # The Linux test and Windows filesystem integration still verify the guard.
        pytest.skip(f'OS denied creating a test-only symlink: {exc}')
    with pytest.raises(PermissionError):dl.export_approved(store,aid,root=folder)
