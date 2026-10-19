"""Stage60 local tool audit, failure workflow and access control."""
import sqlite3
import socket
from unittest.mock import patch

import pytest

from desktop.storage import LocalStore, AuthenticationError
from desktop.tool_use_audit import classify, record, history, failure_action


def owner(tmp_path):
    store = LocalStore(tmp_path / 'owner.sqlite3')
    store.setup_owner('owner60', 'stage60-owner-long-password')
    return store


def test_unauthenticated_history_and_review_denied(tmp_path):
    store = owner(tmp_path)
    store.logout()
    with pytest.raises((PermissionError, AuthenticationError)):
        store.tool_use_history()
    with pytest.raises((PermissionError, AuthenticationError)):
        store.review_tool_failure(1, 'acknowledged')


def test_media_inspection_failure_is_redacted_and_logged(tmp_path):
    store = owner(tmp_path)
    private_path = str(tmp_path / 'secret-token-value.png')
    with pytest.raises((ValueError, OSError)):
        store.inspect_media_file(private_path, 'image_png')
    row = store.tool_use_history()[0]
    assert row['operation'] == 'media_inspect' and row['outcome'] == 'failure'
    assert row['error_code'] in ('validation', 'filesystem')
    assert 'secret-token-value' not in str(row)
    assert row['review_state'] == 'unreviewed'
    assert row['retry_executed'] is False


def test_media_success_and_reference(tmp_path):
    store = owner(tmp_path)
    path = tmp_path / 'safe.png'
    # Header with IHDR and IEND for the preexisting PNG adapter.
    import struct
    from desktop.media_tool_adapters import inspect_local
    path.write_bytes(b'\x89PNG\r\n\x1a\n' + struct.pack('>I',13) + b'IHDR' +
                     struct.pack('>IIBBBBB',1,1,8,2,0,0,0) + b'\x00'*4 +
                     b'\x00\x00\x00\x00IEND\xaeB`\x82')
    inspect_local(str(path), 'image_png')
    result = store.inspect_media_file(str(path), 'image_png')
    row = store.tool_use_history()[0]
    assert row['outcome'] == 'success' and row['reference_id'] == result['id']


def test_service_draft_success_and_failed_review(tmp_path):
    store = owner(tmp_path)
    prepared = store.prepare_service_draft('email', 'user@example.com', 'Local title', 'Local body')
    assert store.tool_use_history()[0]['reference_id'] == prepared['id']
    with pytest.raises(ValueError):
        store.review_service_draft(999, True)
    rows = store.tool_use_history()
    assert rows[0]['operation'] == 'service_draft_review'
    assert rows[0]['error_code'] == 'validation'
    assert rows[1]['outcome'] == 'success'
    assert store.service_draft_detail(prepared['id'])['state'] == 'prepared'


def test_failure_workflow_no_retry_and_immutable(tmp_path):
    store = owner(tmp_path)
    with pytest.raises(ValueError):
        store.prepare_service_draft('bad', 'x', 'x', 'x')
    event_id = store.tool_use_history()[0]['id']
    with pytest.raises(ValueError):
        store.review_tool_failure(event_id, 'resolved')
    a = store.review_tool_failure(event_id, 'acknowledged')
    assert not a['retry_executed']
    with pytest.raises(ValueError):
        store.review_tool_failure(event_id, 'acknowledged')
    store.review_tool_failure(event_id, 'resolved')
    assert store.tool_use_history()[0]['review_state'] == 'resolved'
    with pytest.raises(ValueError):
        store.review_tool_failure(event_id, 'acknowledged')
    with store._connect() as con:
        with pytest.raises(sqlite3.DatabaseError):
            con.execute('UPDATE tool_use_events SET summary=? WHERE id=?', ('changed',event_id))
        with pytest.raises(sqlite3.DatabaseError):
            con.execute('DELETE FROM tool_failure_actions WHERE event_id=?', (event_id,))


@pytest.mark.parametrize('note', ['password=secret', 'api_key:secret', 'x\nline', 'x'*161])
def test_secret_or_invalid_failure_notes_denied(tmp_path,note):
    store=owner(tmp_path)
    with pytest.raises(ValueError):
        store.prepare_service_draft('bad','x','x','x')
    with pytest.raises(ValueError):
        store.review_tool_failure(store.tool_use_history()[0]['id'],'acknowledged',note)


def test_no_network_on_success_failure_and_review(tmp_path):
    store=owner(tmp_path)
    def forbidden(*args, **kwargs):
        raise AssertionError('network is forbidden')
    with patch.object(socket, 'socket', side_effect=forbidden), patch.object(socket,'getaddrinfo',side_effect=forbidden):
        store.prepare_service_draft('post','@test','Test','Local body')
        with pytest.raises(ValueError):
            store.prepare_service_draft('bad','x','x','x')
        event_id=store.tool_use_history()[0]['id']
        store.review_tool_failure(event_id,'acknowledged')
        store.tool_use_history()


def test_record_validation_and_exception_classification(tmp_path):
    store=owner(tmp_path)
    with store._connect() as con:
        for args in [('not_registered','success'),('media_inspect','unknown'),('media_inspect','success','validation')]:
            with pytest.raises(ValueError):
                record(con,*args)
        with pytest.raises(ValueError):
            record(con,'media_inspect','success',reference_id=True)
        with pytest.raises(ValueError):
            history(con,0)
        with pytest.raises(ValueError):
            failure_action(con,0,'acknowledged')
    assert classify(ValueError())=='validation'
    assert classify(PermissionError())=='permission'
    assert classify(OSError())=='filesystem'
    assert classify(RuntimeError())=='internal'


def test_restart_history_persists(tmp_path):
    path=tmp_path/'owner.sqlite3'
    store=owner(tmp_path)
    with pytest.raises(ValueError):
        store.prepare_service_draft('bad','x','x','x')
    event_id=store.tool_use_history()[0]['id']
    store.review_tool_failure(event_id,'acknowledged')
    store.logout()
    other=LocalStore(path)
    other.login('owner60','stage60-owner-long-password')
    assert other.tool_use_history()[0]['review_state']=='acknowledged'
