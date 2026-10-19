"""Stage 28: explicit owner save, immutable review, persistence and isolation."""
import hashlib
import sqlite3
import threading

import pytest

from desktop.storage import AuthenticationError, LocalStore
from desktop.task_runtime import invoke_task_execution
from desktop.model_runtime import ModelConfig


@pytest.fixture
def prepared(tmp_path, monkeypatch):
    store = LocalStore(tmp_path / 'stage28.sqlite3')
    store.setup_owner('owner28', 'secure-local-passphrase-2026')
    employee = store.add_employee_draft('artifact_staff_28', 'AI 직원')
    task = store.add_task('원고 작성', '오프라인 초안')
    assert store.auto_assign_task(task)['employee_id'] == employee
    executable = tmp_path / ('fake-local-exe.exe' if __import__('os').name == 'nt' else 'fake-local-exe')
    executable.write_bytes(b'LOCAL')
    gguf = tmp_path / 'fake.gguf'
    gguf.write_bytes(b'GGUF\x03\x00\x00\x00')
    model_id = store.add_local_model(ModelConfig('artifact-test', 'llama_cpp',
                                                 str(executable), str(gguf), 10))
    store.set_employee_model(employee, model_id)
    monkeypatch.setattr('desktop.task_runtime.run_local_model', lambda *a, **kw: 'LOCAL_DRAFT_28')
    assert invoke_task_execution(store, task) == 'LOCAL_DRAFT_28'
    run = store.list_task_runs(task)[0]
    assert run['status'] == 'success'
    return store, task, run['id']


def test_explicit_save_and_approval_preserve_task_status(prepared):
    store, task, run = prepared
    assert store.list_task_artifacts(task) == []  # no automatic persistence
    artifact = store.save_task_artifact(task, run, '검토할 초안', 'LOCAL_DRAFT_28')
    row = store.read_task_artifact(artifact)
    assert row['body'] == 'LOCAL_DRAFT_28'
    assert row['sha256'] == hashlib.sha256(b'LOCAL_DRAFT_28').hexdigest()
    assert row['review_status'] == 'pending'
    assert 'body' not in store.list_task_artifacts(task)[0]
    assert store.read_task(task)['status'] == 'in_progress'
    store.review_task_artifact(artifact, 'approved', '검토 완료')
    assert store.read_task_artifact(artifact)['review_status'] == 'approved'
    assert store.list_task_artifact_reviews(artifact)[0]['note'] == '검토 완료'
    assert store.read_task(task)['status'] == 'in_progress'  # human marks done separately
    with pytest.raises(ValueError, match='이미 검수'):
        store.review_task_artifact(artifact, 'rejected', '다시')
    with pytest.raises(ValueError, match='이미 저장'):
        store.save_task_artifact(task, run, '다른 제목', '내용 변경')
    assert store.read_task_artifact(artifact)['body'] == 'LOCAL_DRAFT_28'


@pytest.mark.parametrize('body', ['', '   ', '\x00bad', 'X'*20001, None, 42])
def test_invalid_text_never_saved(prepared, body):
    store, task, run = prepared
    with pytest.raises(ValueError):
        store.save_task_artifact(task, run, '제목', body)
    assert store.list_task_artifacts(task) == []


def test_reject_other_run_and_invalid_decisions(prepared):
    store, task, run = prepared
    other = store.add_task('다른 업무')
    with pytest.raises(ValueError, match='성공한'):
        store.save_task_artifact(other, run, '제목', '본문')
    with pytest.raises(ValueError):
        store.save_task_artifact(task, run + 1000, '제목', '본문')
    artifact = store.save_task_artifact(task, run, '제목', '본문')
    for decision, note in [('changes_requested',''),('rejected',''),('pending','메모'),('', '메모')]:
        with pytest.raises(ValueError):
            store.review_task_artifact(artifact, decision, note)
    assert store.list_task_artifact_reviews(artifact) == []
    store.review_task_artifact(artifact, 'changes_requested', '보강하세요')
    assert store.list_task_artifact_reviews(artifact)[0]['new_status'] == 'changes_requested'


def test_reopen_auth_persistence_and_legacy_migration(prepared):
    store, task, run = prepared
    artifact = store.save_task_artifact(task, run, '제목', '한국어 초안')
    store.logout()
    for action in (lambda: store.list_task_artifacts(),
                   lambda: store.read_task_artifact(artifact),
                   lambda: store.review_task_artifact(artifact, 'approved'),
                   lambda: store.save_task_artifact(task, run, '제목', '내용')):
        with pytest.raises(AuthenticationError):
            action()
    reopened = LocalStore(store.path)
    reopened.login('owner28', 'secure-local-passphrase-2026')
    assert reopened.read_task_artifact(artifact)['body'] == '한국어 초안'
    reopened.review_task_artifact(artifact, 'rejected', '요건 부족')
    again = LocalStore(store.path)
    again.login('owner28', 'secure-local-passphrase-2026')
    assert again.read_task_artifact(artifact)['review_status'] == 'rejected'
    assert again.list_task_artifact_reviews(artifact)[0]['note'] == '요건 부족'
    with sqlite3.connect(store.path) as con:
        assert con.execute('PRAGMA foreign_key_check').fetchall() == []


def test_no_external_side_effects_when_storing_and_reviewing(prepared, monkeypatch):
    store, task, run = prepared
    monkeypatch.setattr('socket.socket', lambda *a, **kw: (_ for _ in ()).throw(AssertionError('network')))
    artifact = store.save_task_artifact(task, run, '오프라인', '텍스트')
    store.review_task_artifact(artifact, 'approved')
    assert store.read_task_artifact(artifact)['body'] == '텍스트'
